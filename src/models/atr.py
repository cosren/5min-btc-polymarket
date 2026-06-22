#!/usr/bin/env python3
"""ATR(真实波幅均值)动态波动率阈值计算模块

将进场阈值从静态值改为动态ATR，适应市场波动变化
动态进场阈值 = α × 当前5分钟线的ATR
"""
import math
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """K线数据"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class DynamicThreshold:
    """动态波动率阈值计算器
    
    使用ATR(真实波幅均值)来动态调整进场阈值
    避免在低波动市场使用过高阈值，或在高波动市场使用过低阈值
    
    使用示例:
        calculator = DynamicThreshold(period=14, alpha=1.5)
        threshold = calculator.get_entry_threshold(candles)
    """
    
    def __init__(
        self,
        period: int = 14,
        alpha: float = 1.5
    ):
        """初始化
        
        Args:
            period: ATR计算周期，默认14
            alpha: 阈值系数，默认1.5
        """
        self.period = period
        self.alpha = alpha
        self._atr_history: List[float] = []
        self._current_atr: float = 0.0
    
    def calculate_true_range(self, candle: Candle, prev_close: float) -> float:
        """计算真实波幅(True Range)
        
        TR = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
        
        Args:
            candle: 当前K线
            prev_close: 前一根K线收盘价
        
        Returns:
            真实波幅
        """
        high_low = candle.high - candle.low
        high_close = abs(candle.high - prev_close)
        low_close = abs(candle.low - prev_close)
        
        return max(high_low, high_close, low_close)
    
    def calculate_atr(self, candles: List[Candle]) -> float:
        """计算ATR(真实波幅均值)
        
        Args:
            candles: K线数据列表
        
        Returns:
            ATR值
        """
        if len(candles) < 2:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(candles)):
            tr = self.calculate_true_range(candles[i], candles[i-1].close)
            true_ranges.append(tr)
        
        if len(true_ranges) < self.period:
            # 数据不足时使用简单平均
            self._current_atr = sum(true_ranges) / len(true_ranges)
        else:
            # 使用Wilder平滑法
            recent_tr = true_ranges[-self.period:]
            self._current_atr = sum(recent_tr) / self.period
        
        self._atr_history.append(self._current_atr)
        if len(self._atr_history) > 100:
            self._atr_history = self._atr_history[-100:]
        
        return self._current_atr
    
    def get_entry_threshold(
        self,
        candles: List[Candle],
        alpha: Optional[float] = None
    ) -> float:
        """计算动态进场阈值
        
        动态进场阈值 = α × ATR
        
        Args:
            candles: K线数据
            alpha: 阈值系数(覆盖默认值)
        
        Returns:
            进场阈值(美元)
        """
        atr = self.calculate_atr(candles)
        a = alpha if alpha is not None else self.alpha
        return a * atr
    
    def get_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[float, float, float]:
        """计算布林带
        
        Args:
            prices: 价格序列
            period: 周期
            std_dev: 标准差倍数
        
        Returns:
            (上轨, 中轨, 下轨)
        """
        if len(prices) < period:
            return (0.0, 0.0, 0.0)
        
        recent = prices[-period:]
        middle = sum(recent) / period
        
        variance = sum((p - middle) ** 2 for p in recent) / period
        std = math.sqrt(variance)
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return (upper, middle, lower)
    
    def get_volatility_regime(self) -> str:
        """判断当前波动率状态
        
        Returns:
            'high': 高波动
            'normal': 正常波动
            'low': 低波动
        """
        if len(self._atr_history) < 10:
            return 'normal'
        
        recent_atr = self._atr_history[-1]
        avg_atr = sum(self._atr_history[-10:]) / 10
        
        ratio = recent_atr / avg_atr if avg_atr > 0 else 1.0
        
        if ratio > 1.5:
            return 'high'
        elif ratio < 0.5:
            return 'low'
        else:
            return 'normal'
    
    @property
    def current_atr(self) -> float:
        """获取当前ATR值"""
        return self._current_atr
    
    def should_trade(self, price_move: float) -> bool:
        """判断当前价格波动是否达到进场条件
        
        Args:
            price_move: 当前价格波动幅度
        
        Returns:
            True表示可以进场
        """
        threshold = self.alpha * self._current_atr
        return price_move >= threshold