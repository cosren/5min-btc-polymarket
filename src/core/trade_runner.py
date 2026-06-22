#!/usr/bin/env python3
"""核心交易运行器

整合多源数据、数学模型、风控系统和执行策略的完整交易引擎
"""
import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import argparse
import datetime as dt
import json
import time
import logging
from typing import Any, Optional, Dict
from pathlib import Path

import requests
from fastapi import FastAPI
import uvicorn

# Polymarket API (可选，仅在需要真实交易时)
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import POLYGON
    from py_clob_client.clob_types import ApiCreds
    POLYMARKET_AVAILABLE = True
except ImportError:
    POLYMARKET_AVAILABLE = False
    ClobClient = None
    POLYGON = None
    ApiCreds = None

# 导入新模块
from src.data_sources.aggregator import MarketDataAggregator
from src.models.gbm import GeometricBrownianMotion
from src.models.obi import OrderBookImbalance
from src.models.atr import DynamicThreshold
from src.models.ev_calculator import ExpectedValueCalculator
from src.risk.kelly_criterion import KellyCriterion
from src.risk.circuit_breaker import CircuitBreaker, TradeRecord
from src.execution.sniper import SniperMode
from src.execution.paper_trading import PaperTradingEngine
from src.monitoring.notifier import TelegramNotifier
from src.monitoring.data_logger import DataLogger
from src.monitoring.dashboard import TradingDashboard

from collections import deque

UTC = dt.timezone.utc

logger = logging.getLogger(__name__)


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def ts_utc() -> str:
    return now_utc().isoformat().replace('+00:00', 'Z')


def load_config(config_path: str) -> dict:
    """加载YAML配置文件"""
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


class InstitutionalTradeRunner:
    """机构级交易运行器
    
    整合所有优化模块:
    - 多源数据聚合 (Binance + Deribit + Hyperliquid)
    - 数学模型 (GBM + OBI + ATR + EV)
    - 凯利公式仓位管理
    - 熔断风控系统
    - 狙击模式执行
    - Telegram通知
    - CSV数据记录
    """
    
    def __init__(self, config: dict, profile: str = 'conservative'):
        """初始化
        
        Args:
            config: 完整配置字典
            profile: 配置文件名
        """
        self.config = config
        self.profile = profile
        self.profile_config = config.get('profiles', {}).get(profile, {})
        
        # 初始化数据聚合器
        self.aggregator = MarketDataAggregator(config)
        
        # 初始化数学模型
        gbm_config = config.get('models', {}).get('gbm', {})
        self.gbm = GeometricBrownianMotion(
            mu=gbm_config.get('default_mu', 0.001),
            sigma=gbm_config.get('default_sigma', 0.02)
        )
        
        self.obi_calculator = OrderBookImbalance()
        
        atr_config = config.get('models', {}).get('atr', {})
        self.atr_calculator = DynamicThreshold(
            period=atr_config.get('period', 14),
            alpha=atr_config.get('alpha', 1.5)
        )
        
        ev_config = config.get('models', {}).get('ev', {})
        self.ev_calculator = ExpectedValueCalculator(
            min_ev=ev_config.get('min_ev', 0.05)
        )
        
        # 初始化风控系统
        sizing_config = self.profile_config.get('sizing', {})
        self.kelly = KellyCriterion(
            max_position_pct=sizing_config.get('max_position_pct', 5.0),
            kelly_fraction_type=sizing_config.get('kelly_fraction_type', 'quarter')
        )
        
        cb_config = self.profile_config.get('circuit_breaker', {})
        self.circuit_breaker = CircuitBreaker(
            daily_max_loss_pct=cb_config.get('daily_max_loss_pct', 10.0),
            max_consecutive_losses=cb_config.get('max_consecutive_losses', 3),
            max_position_size_pct=sizing_config.get('max_position_pct', 5.0),
            max_drawdown_pct=cb_config.get('max_drawdown_pct', 15.0)
        )
        
        # 初始化狙击模式
        sniper_config = config.get('sniper_mode', {})
        self.sniper = SniperMode(
            window_start=sniper_config.get('window_start_sec', 5),
            window_end=sniper_config.get('window_end_sec', 2),
            min_win_prob=sniper_config.get('min_win_probability', 0.98),
            min_obi=sniper_config.get('min_obi', 0.7),
            max_stake_usd=sniper_config.get('max_stake_usd', 10.0)
        )
        
        # 初始化监控
        telegram_config = config.get('monitoring', {}).get('telegram', {})
        if telegram_config.get('enabled', False):
            self.notifier = TelegramNotifier(
                bot_token=telegram_config.get('bot_token', ''),
                chat_id=telegram_config.get('chat_id', '')
            )
        else:
            self.notifier = None
        
        logging_config = config.get('monitoring', {}).get('data_logging', {})
        self.data_logger = DataLogger(
            log_dir=logging_config.get('log_dir', './data/logs')
        )
        
        # 初始化纸面交易引擎
        self.paper_trading = PaperTradingEngine(
            initial_equity=1000.0
        )
        
        # 交易状态
        self.equity = 1000.0  # 初始资金
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.trades_today = 0

        # 初始化熔断器每日状态
        self.circuit_breaker.reset_daily(self.equity)
    
    def evaluate_trade_opportunity(
        self,
        poly_data: dict,
        current_price: float,
        target_price: float,
        time_to_expiry: float,
        effective_equity: Optional[float] = None
    ) -> dict:
        """评估交易机会
        
        完整的决策流程:
        1. 数据聚合和过滤
        2. GBM胜率计算
        3. EV校验
        4. 凯利公式仓位计算
        5. 风控检查
        
        Args:
            poly_data: Polymarket数据
            current_price: 当前BTC价格
            target_price: 目标价格
            time_to_expiry: 距离到期时间(秒)
        
        Returns:
            评估结果字典
        """
        equity = effective_equity if effective_equity is not None else self.equity

        result = {
            'timestamp': ts_utc(),
            'should_trade': False,
            'reason': '',
            'side': None,
            'stake_usd': 0.0,
            'metrics': {}
        }
        
        # 1. 检查熔断器
        if self.circuit_breaker.should_stop_trading(
            equity, self.daily_pnl, self.consecutive_losses
        ):
            result['reason'] = 'circuit_breaker_active'
            return result
        
        # 2. 获取聚合数据
        aggregated_data = self.aggregator.get_aggregated_data(poly_data)

        # 如果 WS 数据不可用，从 Polymarket 价格推导 OBI
        paper_mode = False
        if aggregated_data.binance_obi == 0.0:
            up_p = poly_data.get('up_price', 0.5)
            down_p = poly_data.get('down_price', 0.5)
            aggregated_data.binance_obi = (up_p - 0.5) * 2
            if down_p > 0:
                aggregated_data.binance_buy_sell_ratio = up_p / down_p
            paper_mode = True
        
        # 3. 数据过滤
        filters = self.config.get('filters', {})
        if paper_mode:
            filters = {k: v for k, v in filters.items() if k == 'obi'}
        should_trade, filter_reason = self.aggregator.should_trade(
            aggregated_data, filters
        )
        result['metrics'] = {'obi': aggregated_data.binance_obi, 'paper_mode': paper_mode}
        if not should_trade:
            result['reason'] = f'filter_failed:{filter_reason}'
            return result

        # 3.5 方向感知 OBI 检查
        obi = aggregated_data.binance_obi
        side = poly_data.get('side')
        if not side:
            up_p = poly_data.get('up_price', 0.5)
            down_p = poly_data.get('down_price', 0.5)
            if up_p == down_p:
                side = 'UP' if obi >= 0 else 'DOWN'
            else:
                side = 'UP' if up_p > down_p else 'DOWN'

        obi_threshold = filters.get('obi', {}).get('threshold', 0.15)
        if side == 'UP' and obi < obi_threshold:
            result['reason'] = f'obi_direction:UP_needs_OBI>={obi_threshold:.2f}_got_{obi:.3f}'
            return result
        elif side == 'DOWN' and obi > -obi_threshold:
            result['reason'] = f'obi_direction:DOWN_needs_OBI<=-{obi_threshold:.2f}_got_{obi:.3f}'
            return result

        # 4. GBM胜率计算
        gbm_win_prob = self.gbm.calculate_win_probability(
            current_price, target_price, time_to_expiry
        )
        result['metrics']['gbm_win_prob'] = gbm_win_prob
        
        min_win_prob = self.config.get('models', {}).get('gbm', {}).get('min_win_probability', 0.65)
        if gbm_win_prob < min_win_prob:
            result['reason'] = f'gbm_prob_too_low:{gbm_win_prob:.3f}'
            return result
        
        # 5. EV校验
        poly_price = poly_data.get('up_price', 0.5) if poly_data.get('side') == 'UP' else poly_data.get('down_price', 0.5)
        ev = self.ev_calculator.calculate_ev(gbm_win_prob, poly_price)
        result['metrics']['ev'] = ev
        
        if not self.ev_calculator.should_trade(ev):
            result['reason'] = f'ev_too_low:{ev:.3f}'
            return result
        
        # 6. 凯利公式计算仓位
        payout_ratio = (1.0 / poly_price) - 1.0 if poly_price > 0 else 0
        kelly_fraction = self.kelly.calculate_kelly_fraction(gbm_win_prob, payout_ratio)
        stake_usd = self.kelly.calculate_position_size(
            equity, gbm_win_prob, payout_ratio
        )
        
        if stake_usd <= 0:
            result['reason'] = 'kelly_fraction_negative'
            return result
        
        # 7. 检查每日交易次数限制
        max_trades = self.profile_config.get('sizing', {}).get('max_trades_per_day', 12)
        if self.trades_today >= max_trades:
            result['reason'] = 'max_trades_per_day_reached'
            return result
        
        # 所有检查通过
        side = poly_data.get('side', 'UP')
        result.update({
            'should_trade': True,
            'reason': 'all_checks_passed',
            'side': side,
            'stake_usd': stake_usd,
            'metrics': {
                'obi': aggregated_data.binance_obi,
                'gbm_win_prob': gbm_win_prob,
                'ev': ev,
                'kelly_fraction': kelly_fraction,
                'payout_ratio': payout_ratio,
                'signal_strength': aggregated_data.combined_signal_strength
            }
        })
        
        return result
    
    def check_sniper_opportunity(
        self,
        poly_data: dict,
        current_price: float,
        target_price: float,
        time_to_expiry: float
    ) -> dict:
        """检查狙击机会
        
        Args:
            poly_data: Polymarket数据
            current_price: 当前BTC价格
            target_price: 目标价格
            time_to_expiry: 距离到期时间(秒)
        
        Returns:
            狙击评估结果
        """
        result = {
            'should_snipe': False,
            'reason': '',
            'stake_usd': 0.0
        }
        
        # 检查狙击模式是否启用
        if not self.config.get('sniper_mode', {}).get('enabled', True):
            result['reason'] = 'sniper_disabled'
            return result
        
        # 获取聚合数据
        aggregated_data = self.aggregator.get_aggregated_data(poly_data)
        
        # GBM胜率
        gbm_win_prob = self.gbm.calculate_win_probability(
            current_price, target_price, time_to_expiry
        )
        
        # 评估狙击信号
        signal = self.sniper.evaluate(
            time_to_expiry=time_to_expiry,
            obi=aggregated_data.binance_obi,
            win_probability=gbm_win_prob,
            current_price=current_price,
            target_price=target_price
        )
        
        if signal.should_snipe:
            stake = self.sniper.calculate_stake(
                self.paper_trading.current_equity if hasattr(self, 'paper_trading') else self.equity,
                signal.confidence
            )
            result.update({
                'should_snipe': True,
                'reason': 'sniper_signal_valid',
                'stake_usd': stake,
                'side': signal.side,
                'confidence': signal.confidence
            })
        else:
            result['reason'] = 'no_sniper_signal'
        
        return result
    
    def record_trade_result(
        self,
        trade_data: dict,
        pnl: float,
        result: str
    ):
        """记录交易结果
        
        Args:
            trade_data: 交易数据
            pnl: 盈亏
            result: 结果 (win/loss)
        """
        # 更新状态
        self.daily_pnl += pnl
        self.equity += pnl
        self.trades_today += 1
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # 记录到熔断器
        self.circuit_breaker.record_trade(TradeRecord(
            timestamp=time.time(),
            pnl=pnl,
            side=trade_data.get('side', ''),
            market=trade_data.get('market_slug', '')
        ))
        
        # 记录到CSV
        self.data_logger.log_trade_attempt(
            timestamp=trade_data.get('timestamp', ts_utc()),
            market_slug=trade_data.get('market_slug', ''),
            side=trade_data.get('side', ''),
            obi=trade_data.get('metrics', {}).get('obi', 0),
            gbm_win_prob=trade_data.get('metrics', {}).get('gbm_win_prob', 0),
            ev=trade_data.get('metrics', {}).get('ev', 0),
            kelly_fraction=trade_data.get('metrics', {}).get('kelly_fraction', 0),
            stake_usd=trade_data.get('stake_usd', 0),
            entry_price=trade_data.get('entry_price', 0),
            exit_price=trade_data.get('exit_price'),
            pnl=pnl,
            result=result,
            slippage=trade_data.get('slippage', 0),
            latency_ms=trade_data.get('latency_ms', 0),
            time_to_expiry=trade_data.get('time_to_expiry', 0),
            is_sniper=trade_data.get('is_sniper', False),
            circuit_breaker_active=self.circuit_breaker.get_state().is_active
        )
        
        # 发送通知
        if self.notifier:
            self.notifier.send_trade_alert({
                'side': trade_data.get('side'),
                'market': trade_data.get('market_slug'),
                'stake': trade_data.get('stake_usd'),
                'pnl': pnl,
                'result': result
            })


def fetch_btc_price() -> float:
    """从 Binance REST API 获取 BTC 实时价格"""
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=5
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception:
        return 0.0

# ============================================================
# FastAPI 应用（用于 Docker/Back4app 部署的健康检查 + Web 服务）
# ============================================================
app = FastAPI(title="BTC 5m Polymarket Bot")


@app.get("/health")
async def health_check():
    """健康检查端点：供 Docker/Back4app 探测服务是否存活"""
    return {"status": "healthy", "msg": "Polymarket Bot is hunting!"}


def setup_logging():
    """容器环境检测：关闭 Rich 富文本标记，防止日志乱码"""
    if os.environ.get("PYTHONUNBUFFERED") == "1":
        os.environ["RICH_DISABLE"] = "1"
        print("[INFO] Production Container detected. Disabling TUI markup for clean logs.")

def main():
    """主函数"""
    ap = argparse.ArgumentParser(description='Institutional BTC 5m Trade Runner')
    ap.add_argument('--config', default='config/btc_5m_profiles.yaml')
    ap.add_argument('--profile', choices=['conservative', 'aggressive'], default='conservative')
    ap.add_argument('--execute', action='store_true', help='执行真实交易')
    ap.add_argument('--dry-run', action='store_true', help='仅观察不执行')
    ap.add_argument('--simulator', action='store_true', help='使用模拟数据模式')
    ap.add_argument('--scene', choices=['normal', 'trending', 'volatile', 'crash', 'pump'],
                   default='normal', help='模拟市场场景')
    ap.add_argument('--paper-trade', action='store_true',
                   help='纸面交易模式：真实数据+模拟交易+盈亏统计')
    ap.add_argument('--real-data', action='store_true',
                   help='真实数据模式：获取Polymarket真实数据但不交易')
    ap.add_argument('--dashboard', action='store_true',
                   help='启用实时终端仪表盘')
    ap.add_argument('--web', action='store_true',
                   help='启用 Web 浏览器仪表盘（自动打开浏览器）')
    ap.add_argument('--web-port', type=int, default=8186,
                   help='Web 仪表盘端口（默认 8186）')

    args = ap.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 模式说明
    if args.paper_trade:
        print("📊 PAPER TRADING MODE: 真实数据 + 模拟交易")
        print("✅ 获取Polymarket真实市场数据")
        print("✅ 运行真实交易逻辑")
        print("✅ 模拟买入和结算")
        print("✅ 跟踪盈亏和权益")
        print("❌ 不执行真实交易")
        use_paper_trade = True
        use_real_data = True
        use_simulator = False
    elif args.real_data:
        print("📡 REAL DATA MODE: 使用Polymarket真实数据")
        print("⚠️  仅获取数据，不执行真实交易")
        use_paper_trade = False
        use_real_data = True
        use_simulator = False
    elif args.simulator:
        print(f"🎮 SIMULATOR MODE: {args.scene} scene")
        use_paper_trade = False
        use_real_data = False
        use_simulator = True
        config.setdefault('data_sources', {})['use_simulator'] = True
        config.setdefault('data_sources', {}).setdefault('simulator', {})['scene'] = args.scene
    else:
        print("🔧 DEFAULT MODE: 使用配置文件")
        use_paper_trade = False
        use_real_data = False
        use_simulator = config.get('data_sources', {}).get('use_simulator', False)
    
    # 初始化运行器
    runner = InstitutionalTradeRunner(config, args.profile)
    
    # 初始化数据源
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(runner.aggregator.initialize_sources())
    
    # 如果使用真实数据，初始化Polymarket API
    poly_api = None
    if use_real_data:
        try:
            from src.data_sources.polymarket_api import PolymarketPublicAPI
            poly_api = PolymarketPublicAPI()
            print("✅ Polymarket API initialized")
        except Exception as e:
            print(f"⚠️  Failed to initialize Polymarket API: {e}")
            print("🔄 Falling back to simulator mode")
            use_real_data = False
            use_simulator = True
    
    print(f"Initialized trade runner with profile: {args.profile}")
    print(f"Execute mode: {args.execute}")
    print(f"Paper trading: {use_paper_trade}")
    print()

    # 仪表盘初始化
    dashboard = None
    web_dashboard = None
    if args.dashboard:
        try:
            dashboard = TradingDashboard()
            dashboard.start_in_thread()
            print("🎛️  Dashboard enabled")
        except ImportError as e:
            print(f"⚠️  Dashboard unavailable: {e}")

    if args.web:
        try:
            from src.monitoring.web_dashboard import WebDashboard
            web_dashboard = WebDashboard(port=args.web_port)
            web_dashboard.start()
        except Exception as e:
            print(f"⚠️  Web Dashboard unavailable: {e}")

    # 主循环
    cycle_count = 0
    active_markets = {}
    btc_price_history = deque(maxlen=60)
    obi_history = deque(maxlen=60)
    gbm_history = deque(maxlen=60)
    poly_price_history = deque(maxlen=60)
    
    while True:
        try:
            cycle_count += 1
            binance_latency = 0.0
            
            # 获取Polymarket市场数据
            poly_data = None
            poly_latency = 0.0
            if use_real_data and poly_api:
                t0 = time.time()
                poly_data = poly_api.get_market_with_retry(max_retries=2)
                poly_latency = (time.time() - t0) * 1000
                if poly_data:
                    print(f"📊 Market: {poly_data['question'][:60]}...")
                    print(f"   UP: {poly_data['up_price']:.3f} | DOWN: {poly_data['down_price']:.3f}")
                else:
                    print("⚠️  No real market data")
            
            # 如果没有真实数据，使用模拟数据
            if not poly_data:
                if use_simulator:
                    runner.aggregator.binance_ws.update_data()
                    runner.aggregator.deribit_ws.update_data()
                    runner.aggregator.hyperliquid_ws.update_data()
                    current_price = runner.aggregator.binance_ws.simulator.current_price
                else:
                    t0 = time.time()
                    current_price = fetch_btc_price()
                    binance_latency = (time.time() - t0) * 1000
                    if current_price <= 0:
                        print("⚠️  Failed to fetch BTC price, skipping cycle")
                        time.sleep(1)
                        continue
                
                poly_data = {
                    'up_price': 0.75,
                    'down_price': 0.25,
                    'side': 'UP',
                    'slug': 'btc-updown-5m-simulated',
                    'market_id': 'simulated-123'
                }
            else:
                t0 = time.time()
                current_price = fetch_btc_price()
                binance_latency = (time.time() - t0) * 1000
                if current_price <= 0:
                    print("⚠️  Failed to fetch BTC price, skipping cycle")
                    time.sleep(1)
                    continue
            
            btc_price_history.append(current_price)
            
            target_price = current_price * 1.001
            if poly_data and poly_data.get('end_date'):
                try:
                    end_dt = dt.datetime.fromisoformat(poly_data['end_date'].replace('Z', '+00:00'))
                    time_to_expiry = max(0.0, (end_dt - now_utc()).total_seconds())
                except Exception:
                    time_to_expiry = 120.0
            else:
                time_to_expiry = 120.0
            
            # 评估交易机会
            effective_equity = runner.paper_trading.current_equity if use_paper_trade else runner.equity
            evaluation = runner.evaluate_trade_opportunity(
                poly_data, current_price, target_price, time_to_expiry,
                effective_equity=effective_equity
            )
            
            # 狙击模式检查（在到期前5秒窗口内高胜率狙击）
            sniper_result = runner.check_sniper_opportunity(
                poly_data, current_price, target_price, time_to_expiry
            )
            if use_paper_trade and sniper_result.get('should_snipe'):
                sniper_side = sniper_result['side']
                sniper_stake = sniper_result['stake_usd']
                sniper_entry = poly_data['up_price'] if sniper_side == 'UP' else poly_data['down_price']
                sniper_pos = runner.paper_trading.buy(
                    market_id=poly_data.get('market_id', ''),
                    market_slug=poly_data.get('slug', ''),
                    side=sniper_side,
                    entry_price=sniper_entry,
                    stake_usd=sniper_stake
                )
                if sniper_pos:
                    active_markets[poly_data['slug']] = sniper_pos
                    print(f"🎯 SNIPER: {sniper_side} ${sniper_stake:.2f} @ {sniper_entry:.3f} "
                          f"(conf={sniper_result.get('confidence', 0):.2f})")

            # 纸面交易逻辑
            if use_paper_trade and evaluation['should_trade']:
                side = evaluation['side']
                stake = evaluation['stake_usd']
                entry_price = poly_data['up_price'] if side == 'UP' else poly_data['down_price']
                
                # 模拟买入
                position = runner.paper_trading.buy(
                    market_id=poly_data.get('market_id', ''),
                    market_slug=poly_data.get('slug', ''),
                    side=side,
                    entry_price=entry_price,
                    stake_usd=stake
                )
                
                if position:
                    active_markets[poly_data['slug']] = position
                    print(f"📝 PAPER BUY: {side} ${stake:.2f} @ {entry_price:.3f}")
            
            # 打印状态
            if cycle_count % 10 == 0:
                print(f"\n{'='*60}")
                print(f"Cycle: {cycle_count} | BTC: ${current_price:,.2f}")
                
                if use_paper_trade:
                    summary = runner.paper_trading.get_performance_summary()
                    print(f"Equity: ${summary['current_equity']:,.2f} | PnL: ${summary['total_pnl']:+,.2f} ({summary['total_pnl_pct']:+.1f}%)")
                    print(f"Trades: {summary['total_trades']} | Win Rate: {summary['win_rate']:.1%}")
                    print(f"Active Positions: {len(active_markets)}")
                else:
                    print(f"Equity: ${runner.equity:,.2f} | Daily PnL: ${runner.daily_pnl:,.2f}")
                
                if evaluation['should_trade']:
                    print(f"✅ SIGNAL: {evaluation['side']} ${evaluation['stake_usd']:.2f}")
                    print(f"   Win Prob: {evaluation['metrics']['gbm_win_prob']:.3f}")
                    print(f"   EV: {evaluation['metrics']['ev']:.3f}")
                else:
                    print(f"❌ No Trade: {evaluation['reason']}")

            # 记录历史数据
            obi = evaluation.get('metrics', {}).get('obi', 0)
            gbm = evaluation.get('metrics', {}).get('gbm_win_prob', 0)
            poly_p = poly_data.get('up_price', 0.5)
            obi_history.append(obi)
            gbm_history.append(gbm)
            poly_price_history.append(poly_p)

            # 更新仪表盘
            if dashboard or web_dashboard:
                summary = runner.paper_trading.get_performance_summary() if use_paper_trade else {}
                btc_arr = list(btc_price_history)
                btc_high = max(btc_arr) if btc_arr else current_price
                btc_low = min(btc_arr) if btc_arr else current_price
                btc_chg = (current_price / btc_arr[0] - 1) * 100 if len(btc_arr) >= 2 else 0
                active_positions = [
                    {'side': p.side, 'stake_usd': p.stake_usd,
                     'entry_price': p.entry_price, 'market_slug': p.market_slug}
                    for p in (runner.paper_trading.positions if use_paper_trade else [])
                ]
                recent_trades = [
                    {'side': p.side, 'stake_usd': p.stake_usd,
                     'pnl_usd': p.pnl_usd, 'pnl_pct': p.pnl_pct,
                     'is_win': p.is_win,
                     'time': time.strftime('%H:%M:%S', time.localtime(p.entry_time))}
                    for p in (runner.paper_trading.closed_positions[-8:] if use_paper_trade else [])
                ]

                common = dict(
                    btc_price=current_price, btc_change_pct=btc_chg,
                    btc_history=btc_price_history,
                    obi_history=obi_history, gbm_history=gbm_history,
                    poly_price_history=poly_price_history,
                    up_price=poly_data.get('up_price', 0),
                    down_price=poly_data.get('down_price', 0),
                    gbm_win_prob=gbm, ev=evaluation.get('metrics', {}).get('ev', 0),
                    obi=obi, kelly_fraction=evaluation.get('metrics', {}).get('kelly_fraction', 0),
                    signal_side=evaluation.get('side', ''),
                    signal_stake=evaluation.get('stake_usd', 0),
                    should_trade=evaluation.get('should_trade', False),
                    filter_reason=evaluation.get('reason', ''),
                    equity=summary.get('current_equity', 1000),
                    total_pnl=summary.get('total_pnl', 0),
                    total_pnl_pct=summary.get('total_pnl_pct', 0),
                    total_trades=summary.get('total_trades', 0),
                    win_rate=summary.get('win_rate', 0),
                    winning_trades=summary.get('winning_trades', 0),
                    losing_trades=summary.get('losing_trades', 0),
                    daily_pnl=summary.get('daily_pnl', 0),
                    active_positions=active_positions, recent_trades=recent_trades,
                    cycle_count=cycle_count,
                    poly_latency_ms=poly_latency, binance_latency_ms=binance_latency,
                    time_to_expiry=time_to_expiry,
                    ws_connected=True, heartbeat="RUNNING",
                )

                if dashboard:
                    dashboard.update(**common,
                        btc_high=btc_high, btc_low=btc_low,
                        market_question=poly_data.get('question', ''),
                        market_slug=poly_data.get('slug', ''),
                        combined_signal=evaluation.get('metrics', {}).get('combined_signal', 0),
                        initial_equity=summary.get('initial_equity', summary.get('current_equity', 1000)),
                    )

                if web_dashboard:
                    web_dashboard.update(**common)

                # 添加日志流
                if evaluation['should_trade']:
                    side = evaluation['side']
                    stake = evaluation['stake_usd']
                    if dashboard:
                        dashboard.add_log("TRADE",
                            f"EV={evaluation.get('metrics',{}).get('ev',0):.3f} | "
                            f"Kelly={evaluation.get('metrics',{}).get('kelly_fraction',0):.1%} | "
                            f"{side} ${stake:.2f} @ {poly_data.get('up_price' if side=='UP' else 'down_price',0):.3f}")
                    if web_dashboard:
                        web_dashboard.add_log("TRADE",
                            f"EV={evaluation.get('metrics',{}).get('ev',0):.3f} | "
                            f"Kelly={evaluation.get('metrics',{}).get('kelly_fraction',0):.1%} | "
                            f"{side} ${stake:.2f} @ {poly_data.get('up_price' if side=='UP' else 'down_price',0):.3f}")
                elif cycle_count % 5 == 0:
                    if dashboard:
                        dashboard.add_log("INFO",
                            f"BTC ${current_price:,.0f} | OBI:{obi:+.3f} | "
                            f"GBM:{gbm:.3f} | {evaluation.get('reason','')}")
                    if web_dashboard:
                        web_dashboard.add_log("INFO",
                            f"BTC ${current_price:,.0f} | OBI:{obi:+.3f} | "
                            f"GBM:{gbm:.3f} | {evaluation.get('reason','')}")

            # 模拟市场结算：基于BTC价格走势判断方向
            if use_paper_trade and cycle_count % 60 == 0:
                for slug, position in list(active_markets.items()):
                    btc_list = list(btc_price_history)
                    prev_price = btc_list[-60] if len(btc_list) >= 60 else btc_list[0]
                    result_side = 'UP' if current_price > prev_price else 'DOWN'
                    
                    settled = runner.paper_trading.settle_position(
                        position.position_id,
                        1.0 if result_side == position.side else 0.0,
                        result_side
                    )

                    if settled:
                        runner.record_trade_result(
                            trade_data={
                                'timestamp': ts_utc(),
                                'market_slug': position.market_slug,
                                'side': position.side,
                                'stake_usd': position.stake_usd,
                                'entry_price': position.entry_price,
                                'metrics': evaluation.get('metrics', {}),
                                'time_to_expiry': time_to_expiry,
                            },
                            pnl=settled.pnl_usd,
                            result='win' if settled.is_win else 'loss'
                        )

                    # 更新 OBI 策略分档统计
                    if dashboard:
                        abs_obi = abs(obi)
                        if abs_obi < 0.15:
                            band = "0.00-0.15"
                        elif abs_obi < 0.25:
                            band = "0.15-0.25"
                        elif abs_obi < 0.35:
                            band = "0.25-0.35"
                        else:
                            band = ">0.35"
                        stats = dashboard.state.obi_strategy_stats
                        if band not in stats:
                            stats[band] = {"trades": 0, "wins": 0, "net_pnl": 0.0, "avg_pnl": 0.0}
                        stats[band]["trades"] += 1
                        if position.is_win:
                            stats[band]["wins"] += 1
                        stats[band]["net_pnl"] += position.pnl_usd
                        if stats[band]["trades"] > 0:
                            stats[band]["avg_pnl"] = stats[band]["net_pnl"] / stats[band]["trades"]
                    
                    del active_markets[slug]
            
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            if use_paper_trade:
                runner.paper_trading.print_summary()
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
    
if __name__ == '__main__':
    import threading

    # 检测是否使用终端仪表盘（本地开发模式）
    use_dashboard = '--dashboard' in sys.argv

    if use_dashboard:
        # 本地模式：直接运行 main()，保持 Rich TUI 体验
        main()
    else:
        # 服务器模式：FastAPI + 交易策略后台线程
        setup_logging()

        @app.on_event("startup")
        async def startup_strategy():
            """FastAPI 启动后，在后台线程启动交易策略"""
            threading.Thread(target=main, daemon=True).start()

        port = int(os.environ.get("PORT", 8080))
        print(f"[SERVER] Starting FastAPI on 0.0.0.0:{port}")
        print(f"[SERVER] Health check: http://localhost:{port}/health")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")