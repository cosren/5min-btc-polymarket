#!/usr/bin/env python3
"""熔断风控系统(Circuit Breaker)模块

提供多层级风险控制:
- 每日亏损熔断
- 连续亏损熔断
- 单笔仓位上限
- 最大回撤控制
"""
import time
import logging
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """交易记录"""
    timestamp: float
    pnl: float
    side: str
    market: str


@dataclass
class CircuitBreakerState:
    """熔断器状态"""
    is_active: bool = False
    reason: str = ''
    triggered_at: float = 0.0
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    max_drawdown: float = 0.0


class CircuitBreaker:
    """熔断风控系统
    
    多层级风控机制:
    1. 每日亏损熔断: 亏损达到账户资金的X%时停止交易
    2. 连续亏损熔断: 连续亏损N笔后停止交易
    3. 单笔仓位上限: 单笔下注不超过总资金的X%
    4. 最大回撤控制: 从最高点回撤X%时停止交易
    
    使用示例:
        cb = CircuitBreaker(
            daily_max_loss_pct=10.0,
            max_consecutive_losses=3,
            max_position_size_pct=5.0,
            max_drawdown_pct=15.0
        )
        
        if cb.should_stop_trading(equity=1000, daily_pnl=-150):
            print("触发熔断，停止交易")
    """
    
    def __init__(
        self,
        daily_max_loss_pct: float = 10.0,
        max_consecutive_losses: int = 3,
        max_position_size_pct: float = 5.0,
        max_drawdown_pct: float = 15.0
    ):
        """初始化
        
        Args:
            daily_max_loss_pct: 每日最大亏损比例(%)
            max_consecutive_losses: 最大连续亏损次数
            max_position_size_pct: 单笔最大仓位比例(%)
            max_drawdown_pct: 最大回撤比例(%)
        """
        self.daily_max_loss_pct = daily_max_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_position_size_pct = max_position_size_pct
        self.max_drawdown_pct = max_drawdown_pct
        
        self._state = CircuitBreakerState()
        self._trade_history: List[TradeRecord] = []
        self._peak_equity: float = 0.0
        self._daily_start_equity: float = 0.0
    
    def reset_daily(self, current_equity: float):
        """每日重置
        
        在每天开始交易前调用
        
        Args:
            current_equity: 当前账户资金
        """
        self._daily_start_equity = current_equity
        self._peak_equity = current_equity
        self._state.daily_pnl = 0.0
        self._state.consecutive_losses = 0
        self._state.is_active = False
        self._state.reason = ''
        logger.info(f"Circuit breaker reset for new day, equity={current_equity}")
    
    def check_daily_loss(
        self,
        current_equity: float,
        daily_pnl: float
    ) -> bool:
        """检查每日亏损熔断
        
        Args:
            current_equity: 当前账户资金
            daily_pnl: 当日盈亏
        
        Returns:
            True表示触发熔断
        """
        if daily_pnl >= 0:
            return False
        
        loss_pct = abs(daily_pnl) / current_equity * 100
        
        if loss_pct >= self.daily_max_loss_pct:
            self._state.is_active = True
            self._state.reason = f'daily_loss_limit: {loss_pct:.2f}% >= {self.daily_max_loss_pct}%'
            self._state.triggered_at = time.time()
            self._state.daily_pnl = daily_pnl
            
            logger.error(
                f"DAILY LOSS CIRCUIT BREAKER TRIGGERED: "
                f"loss={loss_pct:.2f}%, limit={self.daily_max_loss_pct}%"
            )
            return True
        
        return False
    
    def check_consecutive_losses(self, loss_count: int) -> bool:
        """检查连续亏损熔断
        
        Args:
            loss_count: 连续亏损次数
        
        Returns:
            True表示触发熔断
        """
        if loss_count >= self.max_consecutive_losses:
            self._state.is_active = True
            self._state.reason = f'consecutive_losses: {loss_count} >= {self.max_consecutive_losses}'
            self._state.triggered_at = time.time()
            self._state.consecutive_losses = loss_count
            
            logger.error(
                f"CONSECUTIVE LOSS CIRCUIT BREAKER TRIGGERED: "
                f"losses={loss_count}, limit={self.max_consecutive_losses}"
            )
            return True
        
        return False
    
    def check_position_size(
        self,
        position_usd: float,
        equity: float
    ) -> bool:
        """检查单笔仓位上限
        
        Args:
            position_usd: 单笔下注金额
            equity: 账户总资金
        
        Returns:
            True表示超过限制
        """
        if equity <= 0:
            return True
        
        position_pct = position_usd / equity * 100
        
        if position_pct > self.max_position_size_pct:
            logger.warning(
                f"POSITION SIZE LIMIT EXCEEDED: "
                f"{position_pct:.2f}% > {self.max_position_size_pct}%"
            )
            return True
        
        return False
    
    def check_drawdown(
        self,
        current_equity: float,
        peak_equity: float
    ) -> bool:
        """检查最大回撤
        
        Args:
            current_equity: 当前账户资金
            peak_equity: 历史最高资金
        
        Returns:
            True表示触发熔断
        """
        if peak_equity <= 0:
            return False
        
        drawdown_pct = (peak_equity - current_equity) / peak_equity * 100
        
        if drawdown_pct >= self.max_drawdown_pct:
            self._state.is_active = True
            self._state.reason = f'max_drawdown: {drawdown_pct:.2f}% >= {self.max_drawdown_pct}%'
            self._state.triggered_at = time.time()
            self._state.max_drawdown = drawdown_pct
            
            logger.error(
                f"DRAWDOWN CIRCUIT BREAKER TRIGGERED: "
                f"drawdown={drawdown_pct:.2f}%, limit={self.max_drawdown_pct}%"
            )
            return True
        
        return False
    
    def should_stop_trading(
        self,
        equity: float,
        daily_pnl: float,
        consecutive_losses: int = 0
    ) -> bool:
        """综合判断是否应该停止交易
        
        Args:
            equity: 当前账户资金
            daily_pnl: 当日盈亏
            consecutive_losses: 连续亏损次数
        
        Returns:
            True表示应该停止交易
        """
        # 检查各项熔断条件
        if self.check_daily_loss(equity, daily_pnl):
            return True
        
        if self.check_consecutive_losses(consecutive_losses):
            return True
        
        if self.check_drawdown(equity, self._peak_equity or equity):
            return True
        
        return False
    
    def record_trade(self, trade: TradeRecord):
        """记录交易
        
        Args:
            trade: 交易记录
        """
        self._trade_history.append(trade)
        
        # 更新连续亏损计数
        if trade.pnl < 0:
            self._state.consecutive_losses += 1
        else:
            self._state.consecutive_losses = 0
        
        # 更新峰值
        if trade.pnl > 0:
            current = self._daily_start_equity + sum(t.pnl for t in self._trade_history)
            self._peak_equity = max(self._peak_equity, current)
    
    def get_state(self) -> CircuitBreakerState:
        """获取当前熔断器状态"""
        return self._state
    
    def reset(self):
        """重置熔断器"""
        self._state = CircuitBreakerState()
        logger.info("Circuit breaker manually reset")
    
    def get_risk_summary(self, equity: float) -> dict:
        """获取风险状态摘要
        
        Args:
            equity: 当前账户资金
        
        Returns:
            风险状态字典
        """
        daily_pnl = self._state.daily_pnl
        daily_loss_pct = abs(daily_pnl) / equity * 100 if daily_pnl < 0 else 0
        
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity * 100
        
        return {
            'is_active': self._state.is_active,
            'reason': self._state.reason,
            'daily_pnl': daily_pnl,
            'daily_loss_pct': daily_loss_pct,
            'daily_loss_limit_pct': self.daily_max_loss_pct,
            'consecutive_losses': self._state.consecutive_losses,
            'consecutive_loss_limit': self.max_consecutive_losses,
            'current_drawdown_pct': drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_position_size_pct': self.max_position_size_pct,
            'total_trades': len(self._trade_history)
        }