#!/usr/bin/env python3
"""市场数据模拟器

生成逼真的市场数据用于测试和开发
"""
import time
import random
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """订单簿层级"""
    price: float
    quantity: float


@dataclass
class OrderBook:
    """订单簿数据"""
    symbol: str
    timestamp: float
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)


class MarketSimulator:
    """市场数据模拟器
    
    功能:
    - 基于GBM生成BTC价格
    - 生成L2订单簿数据
    - 生成主动买卖流
    - 支持多种市场场景
    """
    
    def __init__(
        self,
        initial_price: float = 65000.0,
        scene: str = 'normal'
    ):
        self.initial_price = initial_price
        self.current_price = initial_price
        self.scene = scene
        
        # 场景参数
        self.scene_params = self._get_scene_params(scene)
        
        # 价格历史
        self.price_history: List[float] = [initial_price]
        self.last_update_time: float = time.time()
    
    def _get_scene_params(self, scene: str) -> Dict:
        """获取场景参数"""
        scenes = {
            'normal': {
                'mu': 0.0,           # 无趋势
                'sigma': 0.02,       # 2%波动率
                'trend': 0.0
            },
            'trending': {
                'mu': 0.001,         # 上涨趋势
                'sigma': 0.015,
                'trend': 0.0005
            },
            'volatile': {
                'mu': 0.0,
                'sigma': 0.05,       # 5%高波动
                'trend': 0.0
            },
            'crash': {
                'mu': -0.002,        # 下跌趋势
                'sigma': 0.08,       # 8%极高波动
                'trend': -0.001
            },
            'pump': {
                'mu': 0.002,         # 上涨趋势
                'sigma': 0.06,       # 6%高波动
                'trend': 0.001
            }
        }
        return scenes.get(scene, scenes['normal'])
    
    def update_price(self, dt: float = 1.0) -> float:
        """更新价格（基于GBM）
        
        Args:
            dt: 时间步长（秒）
        
        Returns:
            新价格
        """
        mu = self.scene_params['mu']
        sigma = self.scene_params['sigma']
        trend = self.scene_params['trend']
        
        # GBM公式: dS = mu*S*dt + sigma*S*dW
        dt_years = dt / (365.25 * 24 * 3600)  # 转换为年
        dW = random.gauss(0, 1) * (dt_years ** 0.5)
        
        # 添加趋势
        drift = (mu + trend) * dt_years
        diffusion = sigma * dW
        
        # 更新价格
        price_change = self.current_price * (drift + diffusion)
        self.current_price = max(1000, self.current_price + price_change)
        
        self.price_history.append(self.current_price)
        self.last_update_time = time.time()
        
        return self.current_price
    
    def generate_orderbook(self, levels: int = 10) -> OrderBook:
        """生成订单簿数据
        
        Args:
            levels: 订单簿层级数
        
        Returns:
            订单簿对象
        """
        bids = []
        asks = []
        
        # 生成买单
        for i in range(levels):
            price = self.current_price * (1 - 0.0001 * (i + 1))
            quantity = random.uniform(0.1, 2.0)
            bids.append(OrderBookLevel(price=price, quantity=quantity))
        
        # 生成卖单
        for i in range(levels):
            price = self.current_price * (1 + 0.0001 * (i + 1))
            quantity = random.uniform(0.1, 2.0)
            asks.append(OrderBookLevel(price=price, quantity=quantity))
        
        return OrderBook(
            symbol='BTCUSDT',
            timestamp=time.time(),
            bids=bids,
            asks=asks
        )
    
    def calculate_obi(self, orderbook: OrderBook) -> float:
        """计算订单簿不平衡度"""
        if not orderbook.bids or not orderbook.asks:
            return 0.0
        
        bid_volume = sum(level.quantity for level in orderbook.bids)
        ask_volume = sum(level.quantity for level in orderbook.asks)
        
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        
        return (bid_volume - ask_volume) / total
    
    def get_volatility(self, window: int = 100) -> float:
        """计算历史波动率"""
        if len(self.price_history) < 2:
            return 0.0
        
        recent = self.price_history[-window:]
        returns = [
            (recent[i] - recent[i-1]) / recent[i-1]
            for i in range(1, len(recent))
        ]
        
        if not returns:
            return 0.0
        
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        
        return variance ** 0.5