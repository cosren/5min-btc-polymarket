#!/usr/bin/env python3
"""纸面交易（Paper Trading）模块

模拟真实交易流程，使用真实市场数据但不执行真实交易
用于验证策略效果和计算盈亏
"""
import time
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PositionStatus(Enum):
    """仓位状态"""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class PaperPosition:
    """纸面交易仓位"""
    position_id: str
    market_id: str
    market_slug: str
    side: str  # UP or DOWN
    entry_price: float  # 入场价格（Polymarket价格）
    entry_time: float
    stake_usd: float  # 投入金额
    shares: float  # 购买份额
    status: PositionStatus = PositionStatus.OPEN
    
    # 出场数据
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    
    # 市场结算数据
    settlement_price: Optional[float] = None  # 最终结算价格（0或1）
    is_win: Optional[bool] = None


class PaperTradingEngine:
    """纸面交易引擎
    
    功能:
    - 模拟买入操作
    - 跟踪仓位状态
    - 计算盈亏
    - 生成交易报告
    """
    
    def __init__(self, initial_equity: float = 1000.0):
        """初始化
        
        Args:
            initial_equity: 初始资金
        """
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.peak_equity = initial_equity
        
        # 交易记录
        self.positions: List[PaperPosition] = []
        self.closed_positions: List[PaperPosition] = []
        
        # 统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.max_consecutive_losses = 0
        self.current_consecutive_losses = 0
        
        # 每日统计
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.last_reset_date = time.strftime('%Y-%m-%d')
    
    def buy(
        self,
        market_id: str,
        market_slug: str,
        side: str,
        entry_price: float,
        stake_usd: float
    ) -> Optional[PaperPosition]:
        """模拟买入
        
        Args:
            market_id: 市场ID
            market_slug: 市场slug
            side: 方向 (UP/DOWN)
            entry_price: 入场价格
            stake_usd: 投入金额
        
        Returns:
            仓位对象，失败返回None
        """
        # 检查资金
        if stake_usd > self.current_equity:
            logger.warning(f"Insufficient equity: {self.current_equity:.2f} < {stake_usd:.2f}")
            return None
        
        # 检查仓位限制
        if stake_usd <= 0:
            logger.warning(f"Invalid stake: {stake_usd:.2f}")
            return None
        
        # 计算购买份额
        shares = stake_usd / entry_price if entry_price > 0 else 0
        
        # 创建仓位
        position = PaperPosition(
            position_id=f"pos_{int(time.time() * 1000)}",
            market_id=market_id,
            market_slug=market_slug,
            side=side,
            entry_price=entry_price,
            entry_time=time.time(),
            stake_usd=stake_usd,
            shares=shares
        )
        
        # 扣除资金
        self.current_equity -= stake_usd
        
        # 记录
        self.positions.append(position)
        self.total_trades += 1
        self.daily_trades += 1
        
        logger.info(
            f"📝 PAPER BUY: {side} | "
            f"Price: {entry_price:.3f} | "
            f"Stake: ${stake_usd:.2f} | "
            f"Shares: {shares:.2f}"
        )
        
        return position
    
    def settle_position(
        self,
        position_id: str,
        settlement_price: float,
        market_result: str
    ) -> Optional[PaperPosition]:
        """结算仓位
        
        Args:
            position_id: 仓位ID
            settlement_price: 结算价格（1.0=赢，0.0=输）
            market_result: 市场结果描述
        
        Returns:
            更新后的仓位对象
        """
        # 查找仓位
        position = None
        for pos in self.positions:
            if pos.position_id == position_id:
                position = pos
                break
        
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return None
        
        # 计算盈亏
        if position.side == market_result:
            # 赢了
            position.is_win = True
            payout = position.shares * 1.0  # 每份额支付$1
            position.pnl_usd = payout - position.stake_usd
            position.pnl_pct = (position.pnl_usd / position.stake_usd) * 100
            
            self.winning_trades += 1
            self.current_consecutive_losses = 0
        else:
            # 输了
            position.is_win = False
            position.pnl_usd = -position.stake_usd
            position.pnl_pct = -100.0
            
            self.losing_trades += 1
            self.current_consecutive_losses += 1
            self.max_consecutive_losses = max(
                self.max_consecutive_losses,
                self.current_consecutive_losses
            )
        
        # 更新状态
        position.status = PositionStatus.EXPIRED
        position.settlement_price = settlement_price
        position.exit_time = time.time()
        
        # 更新资金
        if position.is_win:
            payout = position.stake_usd + position.pnl_usd
            self.current_equity += payout
        else:
            # 亏损已经扣除
            pass
        
        # 更新统计
        self.total_pnl += position.pnl_usd
        self.daily_pnl += position.pnl_usd
        
        # 移动到已关闭列表
        self.positions.remove(position)
        self.closed_positions.append(position)
        
        # 检查峰值
        self.peak_equity = max(self.peak_equity, self.current_equity)
        
        logger.info(
            f"{'✅' if position.is_win else '❌'} PAPER SETTLE: "
            f"{'WIN' if position.is_win else 'LOSS'} | "
            f"PnL: ${position.pnl_usd:.2f} ({position.pnl_pct:.1f}%) | "
            f"Equity: ${self.current_equity:.2f}"
        )
        
        return position
    
    def auto_settle_market(
        self,
        market_slug: str,
        result_side: str,
        settlement_price: float = 1.0
    ):
        """自动结算到期的市场
        
        Args:
            market_slug: 市场slug
            result_side: 结果方向 (UP/DOWN)
            settlement_price: 结算价格
        """
        # 查找该市场的未平仓仓位
        positions_to_settle = [
            pos for pos in self.positions
            if pos.market_slug == market_slug
        ]
        
        for position in positions_to_settle:
            self.settle_position(
                position.position_id,
                settlement_price,
                result_side
            )
    
    def reset_daily_stats(self):
        """重置每日统计"""
        today = time.strftime('%Y-%m-%d')
        if today != self.last_reset_date:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset_date = today
            logger.info("Daily stats reset")
    
    def get_equity_curve(self) -> List[Dict]:
        """获取权益曲线"""
        curve = []
        running_equity = self.initial_equity
        
        for pos in self.closed_positions:
            running_equity += pos.stake_usd + pos.pnl_usd
            curve.append({
                'position_id': pos.position_id,
                'time': pos.exit_time,
                'equity': running_equity,
                'pnl': pos.pnl_usd
            })
        
        return curve
    
    def get_performance_summary(self) -> Dict:
        """获取绩效摘要"""
        total_closed = len(self.closed_positions)
        win_rate = self.winning_trades / total_closed if total_closed > 0 else 0
        
        # 计算平均盈亏
        avg_pnl = self.total_pnl / total_closed if total_closed > 0 else 0
        
        # 计算最大回撤
        max_drawdown = 0
        peak = self.initial_equity
        running_equity = self.initial_equity
        
        for pos in self.closed_positions:
            running_equity += pos.stake_usd + pos.pnl_usd
            peak = max(peak, running_equity)
            drawdown = (peak - running_equity) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            'initial_equity': self.initial_equity,
            'current_equity': self.current_equity,
            'total_pnl': self.total_pnl,
            'total_pnl_pct': (self.total_pnl / self.initial_equity) * 100,
            'total_trades': total_closed,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'max_consecutive_losses': self.max_consecutive_losses,
            'max_drawdown_pct': max_drawdown * 100,
            'current_consecutive_losses': self.current_consecutive_losses,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades
        }
    
    def print_summary(self):
        """打印绩效摘要"""
        summary = self.get_performance_summary()
        
        print("\n" + "=" * 60)
        print("  📊 Paper Trading Performance Summary")
        print("=" * 60)
        print(f"  Initial Equity:    ${summary['initial_equity']:,.2f}")
        print(f"  Current Equity:    ${summary['current_equity']:,.2f}")
        print(f"  Total PnL:         ${summary['total_pnl']:+,.2f} ({summary['total_pnl_pct']:+.2f}%)")
        print(f"  Total Trades:      {summary['total_trades']}")
        print(f"  Win Rate:          {summary['win_rate']:.1%}")
        print(f"  Avg PnL/Trade:     ${summary['avg_pnl']:+.2f}")
        print(f"  Max Drawdown:      {summary['max_drawdown_pct']:.1f}%")
        print(f"  Max Consec Losses: {summary['max_consecutive_losses']}")
        print("=" * 60)