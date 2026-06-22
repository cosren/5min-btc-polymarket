#!/usr/bin/env python3
"""订单簿不平衡度(Order Book Imbalance)计算模块

OBI是衡量买卖力量对比的重要指标
OBI = (BidVolume - AskVolume) / (BidVolume + AskVolume)
"""
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    bids: List[Tuple[float, float]]  # [(price, quantity), ...]
    asks: List[Tuple[float, float]]
    timestamp: float


class OrderBookImbalance:
    """订单簿不平衡度计算器
    
    核心逻辑:
    - OBI > 0.35: 买方力量明显占优
    - OBI < -0.35: 卖方力量明显占优
    - OBI 接近 0: 买卖力量均衡
    
    使用示例:
        calculator = OrderBookImbalance()
        obi = calculator.calculate(orderbook, levels=10)
        if obi > 0.35:
            print("买方力量强，考虑做多")
    """
    
    def __init__(self, default_levels: int = 10):
        self.default_levels = default_levels
        self._history: List[float] = []
        self._max_history = 100
    
    def calculate(
        self,
        orderbook: OrderBookSnapshot,
        levels: Optional[int] = None
    ) -> float:
        """计算订单簿不平衡度
        
        Args:
            orderbook: 订单簿快照
            levels: 使用前N档数据，默认使用default_levels
        
        Returns:
            OBI值，范围[-1, 1]
        """
        n = levels if levels is not None else self.default_levels
        
        bid_volume = sum(qty for _, qty in orderbook.bids[:n])
        ask_volume = sum(qty for _, qty in orderbook.asks[:n])
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
        
        obi = (bid_volume - ask_volume) / total_volume
        
        # 记录历史
        self._history.append(obi)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        return obi
    
    def calculate_weighted(
        self,
        orderbook: OrderBookSnapshot,
        levels: Optional[int] = None
    ) -> float:
        """计算加权OBI
        
        距离中间价越近的档位权重越高
        使用指数衰减权重: weight = exp(-distance * decay_factor)
        
        Args:
            orderbook: 订单簿快照
            levels: 使用前N档数据
        
        Returns:
            加权OBI值
        """
        n = levels if levels is not None else self.default_levels
        decay_factor = 0.1
        
        # 计算中间价
        if not orderbook.bids or not orderbook.asks:
            return 0.0
        
        mid_price = (orderbook.bids[0][0] + orderbook.asks[0][0]) / 2
        
        weighted_bid_volume = 0.0
        weighted_ask_volume = 0.0
        
        for price, qty in orderbook.bids[:n]:
            distance = abs(price - mid_price) / mid_price
            weight = pow(2.71828, -distance / decay_factor)
            weighted_bid_volume += qty * weight
        
        for price, qty in orderbook.asks[:n]:
            distance = abs(price - mid_price) / mid_price
            weight = pow(2.71828, -distance / decay_factor)
            weighted_ask_volume += qty * weight
        
        total = weighted_bid_volume + weighted_ask_volume
        if total == 0:
            return 0.0
        
        return (weighted_bid_volume - weighted_ask_volume) / total
    
    def get_obi_trend(self, window: int = 20) -> float:
        """获取OBI趋势
        
        计算最近window个OBI值的移动平均
        
        Args:
            window: 窗口大小
        
        Returns:
            OBI移动平均值
        """
        if not self._history:
            return 0.0
        
        recent = self._history[-window:]
        return sum(recent) / len(recent)
    
    def is_extreme_imbalance(
        self,
        threshold: float = 0.7
    ) -> bool:
        """检查是否出现极端不平衡
        
        用于Sniper模式判断
        
        Args:
            threshold: 阈值，默认0.7
        
        Returns:
            True表示出现极端不平衡
        """
        if not self._history:
            return False
        
        return abs(self._history[-1]) > threshold
    
    def check_signal_strength(
        self,
        obi: float,
        threshold: float = 0.35
    ) -> dict:
        """检查OBI信号强度
        
        Args:
            obi: 当前OBI值
            threshold: 信号阈值
        
        Returns:
            包含信号方向、强度等信息的字典
        """
        strength = abs(obi)
        
        if obi > threshold:
            direction = 'bullish'
        elif obi < -threshold:
            direction = 'bearish'
        else:
            direction = 'neutral'
        
        return {
            'obi': obi,
            'direction': direction,
            'strength': strength,
            'passes_threshold': strength > threshold,
            'threshold': threshold
        }