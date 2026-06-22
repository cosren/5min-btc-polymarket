#!/usr/bin/env python3
"""狙击模式(Sniper Mode)执行策略模块

在最后5秒到2秒之间，如果满足极端条件，执行高频狙击交易
适用于胜率高达98%的确定性机会
"""
import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SniperSignal:
    """狙击信号"""
    timestamp: float
    time_to_expiry: float
    obi: float
    win_probability: float
    side: str  # 'UP' or 'DOWN'
    confidence: float
    should_snipe: bool


class SniperMode:
    """狙击模式执行器
    
    核心逻辑:
    - 在最后5秒到2秒之间监控
    - 需要极端OBI(>0.7)和高胜率(>98%)
    - 使用高Gas费抢跑
    - 虽然利润低(2-3%)，但胜率极高
    
    使用示例:
        sniper = SniperMode(
            window_start=5,
            window_end=2,
            min_win_prob=0.98,
            min_obi=0.7
        )
        
        signal = sniper.evaluate(
            time_to_expiry=3.5,
            obi=0.85,
            win_probability=0.99,
            current_price=65000
        )
        
        if signal.should_snipe:
            sniper.execute(signal)
    """
    
    def __init__(
        self,
        window_start: float = 5.0,
        window_end: float = 2.0,
        min_win_prob: float = 0.98,
        min_obi: float = 0.7,
        max_stake_usd: float = 10.0
    ):
        """初始化
        
        Args:
            window_start: 狙击窗口开始(秒)
            window_end: 狙击窗口结束(秒)
            min_win_prob: 最小胜率要求
            min_obi: 最小OBI要求
            max_stake_usd: 最大下注金额
        """
        self.window_start = window_start
        self.window_end = window_end
        self.min_win_prob = min_win_prob
        self.min_obi = min_obi
        self.max_stake_usd = max_stake_usd
        
        self._signal_history: list = []
        self._execution_count = 0
    
    def is_in_sniper_window(self, time_to_expiry: float) -> bool:
        """检查是否在狙击窗口内
        
        Args:
            time_to_expiry: 距离到期的时间(秒)
        
        Returns:
            True表示在窗口内
        """
        return self.window_end <= time_to_expiry <= self.window_start
    
    def evaluate(
        self,
        time_to_expiry: float,
        obi: float,
        win_probability: float,
        current_price: float,
        target_price: float
    ) -> SniperSignal:
        """评估是否触发狙击
        
        Args:
            time_to_expiry: 距离到期的时间(秒)
            obi: 订单簿不平衡度
            win_probability: GBM计算的胜率
            current_price: 当前价格
            target_price: 目标价格
        
        Returns:
            狙击信号
        """
        in_window = self.is_in_sniper_window(time_to_expiry)
        extreme_obi = abs(obi) > self.min_obi
        high_confidence = win_probability >= self.min_win_prob
        
        # 判断方向
        if obi > 0:
            side = 'UP'
        else:
            side = 'DOWN'
        
        # 计算综合置信度
        confidence = (
            win_probability * 0.6 +
            abs(obi) * 0.3 +
            (1.0 if in_window else 0.0) * 0.1
        )
        
        should_snipe = in_window and extreme_obi and high_confidence
        
        signal = SniperSignal(
            timestamp=time.time(),
            time_to_expiry=time_to_expiry,
            obi=obi,
            win_probability=win_probability,
            side=side,
            confidence=confidence,
            should_snipe=should_snipe
        )
        
        self._signal_history.append(signal)
        if len(self._signal_history) > 100:
            self._signal_history = self._signal_history[-100:]
        
        if should_snipe:
            logger.info(
                f"SNIPER SIGNAL: side={side}, obi={obi:.3f}, "
                f"win_prob={win_probability:.3f}, confidence={confidence:.3f}"
            )
        
        return signal
    
    def get_gas_config(self, urgency: str = 'high') -> Dict[str, Any]:
        """获取Gas配置
        
        狙击模式使用高Gas费确保交易优先打包
        
        Args:
            urgency: 紧急程度 ('high', 'normal')
        
        Returns:
            Gas配置字典
        """
        gas_configs = {
            'high': {
                'priority_fee': '50 gwei',
                'max_fee': '100 gwei',
                'order_type': 'FAK',
                'timeout_sec': 2.0
            },
            'normal': {
                'priority_fee': '20 gwei',
                'max_fee': '50 gwei',
                'order_type': 'FAK',
                'timeout_sec': 5.0
            }
        }
        
        return gas_configs.get(urgency, gas_configs['normal'])
    
    def calculate_stake(
        self,
        equity: float,
        confidence: float
    ) -> float:
        """计算狙击模式下注金额
        
        根据置信度动态调整，但不超过max_stake_usd
        
        Args:
            equity: 账户资金
            confidence: 置信度 [0, 1]
        
        Returns:
            下注金额
        """
        # 基础仓位为账户的1%
        base_stake = equity * 0.01
        
        # 根据置信度调整
        adjusted = base_stake * confidence
        
        # 应用上限
        return min(adjusted, self.max_stake_usd)
    
    def execute(self, signal: SniperSignal) -> Dict[str, Any]:
        """执行狙击交易
        
        Args:
            signal: 狙击信号
        
        Returns:
            执行结果
        """
        if not signal.should_snipe:
            return {'success': False, 'reason': 'signal_not_valid'}
        
        self._execution_count += 1
        
        gas_config = self.get_gas_config('high')
        
        result = {
            'success': True,
            'execution_id': self._execution_count,
            'signal': {
                'side': signal.side,
                'confidence': signal.confidence,
                'win_probability': signal.win_probability,
                'obi': signal.obi
            },
            'gas_config': gas_config,
            'timestamp': signal.timestamp
        }
        
        logger.info(f"SNIPER EXECUTED: {result}")
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取狙击模式统计
        
        Returns:
            统计信息
        """
        total_signals = len(self._signal_history)
        valid_signals = sum(1 for s in self._signal_history if s.should_snipe)
        
        return {
            'total_signals': total_signals,
            'valid_signals': valid_signals,
            'execution_count': self._execution_count,
            'signal_rate': valid_signals / total_signals if total_signals > 0 else 0,
            'window': f'{self.window_start}s - {self.window_end}s',
            'min_win_prob': self.min_win_prob,
            'min_obi': self.min_obi
        }