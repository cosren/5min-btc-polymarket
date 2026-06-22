#!/usr/bin/env python3
"""回测引擎模块

用于验证策略参数和优化模型
"""
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """回测交易记录"""
    timestamp: float
    side: str
    entry_price: float
    exit_price: float
    stake: float
    pnl: float
    win: bool
    obi: float
    gbm_prob: float
    ev: float


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)


class BacktestEngine:
    """回测引擎
    
    功能:
    - 使用历史数据运行回测
    - 计算关键指标(胜率、夏普比率、最大回撤等)
    - 生成回测报告
    
    使用示例:
        engine = BacktestEngine(historical_data)
        result = engine.run_backtest({
            'threshold': 0.70,
            'stake_usd': 5.0,
            'obi_threshold': 0.35,
            'min_ev': 0.05
        })
        print(f"Win Rate: {result.win_rate:.2f}%")
        print(f"Sharpe: {result.sharpe_ratio:.2f}")
    """
    
    def __init__(self, historical_data: List[Dict[str, Any]]):
        """初始化
        
        Args:
            historical_data: 历史数据列表
        """
        self.historical_data = historical_data
        self.results: List[BacktestResult] = []
    
    def run_backtest(self, strategy_params: Dict[str, Any]) -> BacktestResult:
        """运行回测
        
        Args:
            strategy_params: 策略参数
        
        Returns:
            回测结果
        """
        result = BacktestResult()
        equity = 1000.0  # 初始资金
        peak_equity = equity
        
        for data_point in self.historical_data:
            # 检查是否满足进场条件
            if not self._should_enter(data_point, strategy_params):
                continue
            
            # 模拟交易
            trade = self._simulate_trade(data_point, strategy_params, equity)
            
            if trade:
                result.trades.append(trade)
                equity += trade.pnl
                peak_equity = max(peak_equity, equity)
                
                # 计算回撤
                drawdown = (peak_equity - equity) / peak_equity * 100
                result.max_drawdown = max(result.max_drawdown, drawdown)
        
        # 计算统计指标
        self._calculate_statistics(result)
        
        self.results.append(result)
        
        return result
    
    def _should_enter(
        self,
        data_point: Dict[str, Any],
        params: Dict[str, Any]
    ) -> bool:
        """判断是否应该进场
        
        Args:
            data_point: 数据点
            params: 策略参数
        
        Returns:
            True表示应该进场
        """
        # OBI过滤
        obi_threshold = params.get('obi_threshold', 0.35)
        if abs(data_point.get('obi', 0)) < obi_threshold:
            return False
        
        # EV过滤
        min_ev = params.get('min_ev', 0.05)
        if data_point.get('ev', 0) < min_ev:
            return False
        
        # 胜率过滤
        min_win_prob = params.get('min_win_prob', 0.6)
        if data_point.get('gbm_win_prob', 0) < min_win_prob:
            return False
        
        return True
    
    def _simulate_trade(
        self,
        data_point: Dict[str, Any],
        params: Dict[str, Any],
        equity: float
    ) -> Optional[BacktestTrade]:
        """模拟交易
        
        Args:
            data_point: 数据点
            params: 策略参数
            equity: 当前资金
        
        Returns:
            交易记录
        """
        stake = min(params.get('stake_usd', 5.0), equity * 0.05)
        
        entry_price = data_point.get('entry_price', 0.5)
        exit_price = data_point.get('exit_price', entry_price)
        
        # 计算盈亏
        if data_point.get('side') == 'UP':
            pnl = stake * (exit_price - entry_price) / entry_price
        else:
            pnl = stake * (entry_price - exit_price) / entry_price
        
        win = pnl > 0
        
        return BacktestTrade(
            timestamp=data_point.get('timestamp', time.time()),
            side=data_point.get('side', 'UP'),
            entry_price=entry_price,
            exit_price=exit_price,
            stake=stake,
            pnl=pnl,
            win=win,
            obi=data_point.get('obi', 0),
            gbm_prob=data_point.get('gbm_win_prob', 0),
            ev=data_point.get('ev', 0)
        )
    
    def _calculate_statistics(self, result: BacktestResult):
        """计算统计指标
        
        Args:
            result: 回测结果
        """
        trades = result.trades
        if not trades:
            return
        
        result.total_trades = len(trades)
        result.wins = sum(1 for t in trades if t.win)
        result.losses = result.total_trades - result.wins
        result.win_rate = result.wins / result.total_trades * 100
        
        result.total_pnl = sum(t.pnl for t in trades)
        result.avg_pnl = result.total_pnl / result.total_trades
        
        # 利润因子
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 夏普比率(简化版)
        if len(trades) > 1:
            pnls = [t.pnl for t in trades]
            avg_pnl = sum(pnls) / len(pnls)
            variance = sum((p - avg_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
            std_dev = variance ** 0.5
            result.sharpe_ratio = avg_pnl / std_dev if std_dev > 0 else 0
    
    def generate_report(self, result: Optional[BacktestResult] = None) -> Dict[str, Any]:
        """生成回测报告
        
        Args:
            result: 回测结果(如不提供则使用最新结果)
        
        Returns:
            报告字典
        """
        if result is None:
            if not self.results:
                return {'error': 'No backtest results available'}
            result = self.results[-1]
        
        return {
            'total_trades': result.total_trades,
            'wins': result.wins,
            'losses': result.losses,
            'win_rate': result.win_rate,
            'total_pnl': result.total_pnl,
            'avg_pnl': result.avg_pnl,
            'max_drawdown': result.max_drawdown,
            'sharpe_ratio': result.sharpe_ratio,
            'profit_factor': result.profit_factor
        }