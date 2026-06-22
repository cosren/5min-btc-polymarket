#!/usr/bin/env python3
"""币安WebSocket实时数据源模块

提供L2订单簿深度和主动买卖流(aggTrade)数据
"""
import asyncio
import json
import time
import logging
from typing import Optional, Callable, Dict, List, Any
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


class BinanceWebSocket:
    """币安WebSocket客户端（模拟模式）
    
    功能:
    - L2订单簿深度数据(10档)
    - 主动买卖流(aggTrade)
    - 订单簿不平衡度(OBI)计算
    - 买卖比例统计
    """
    
    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        ws_url: str = 'wss://fstream.binance.com/ws',
        depth_levels: int = 10
    ):
        self.symbol = symbol.lower()
        self.ws_url = ws_url
        self.depth_levels = depth_levels
        
        # 数据存储
        self._orderbook: Optional[OrderBook] = None
        self._last_update_time: float = 0
        
        # 买卖流统计
        self._buy_volume: float = 0.0
        self._sell_volume: float = 0.0
        
        # 模拟器（用于模拟模式）
        self.simulator = None
    
    async def connect(self):
        """建立WebSocket连接（模拟模式直接返回）"""
        logger.info(f"BinanceWebSocket initialized (simulator mode)")
    
    async def disconnect(self):
        """断开WebSocket连接"""
        logger.info("BinanceWebSocket disconnected")
    
    def update_data(self):
        """更新模拟数据"""
        if self.simulator:
            self.simulator.update_price(1.0)
            self._orderbook = self.simulator.generate_orderbook()
            self._last_update_time = time.time()
    
    def get_orderbook(self) -> Optional[OrderBook]:
        """获取当前订单簿"""
        return self._orderbook
    
    def calculate_obi(self) -> float:
        """计算订单簿不平衡度"""
        if not self._orderbook or not self._orderbook.bids or not self._orderbook.asks:
            return 0.0
        
        bid_volume = sum(level.quantity for level in self._orderbook.bids)
        ask_volume = sum(level.quantity for level in self._orderbook.asks)
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
        
        return (bid_volume - ask_volume) / total_volume
    
    def calculate_buy_sell_ratio(self) -> float:
        """计算买卖比例"""
        total = self._buy_volume + self._sell_volume
        if total == 0:
            return 1.0
        
        return self._buy_volume / self._sell_volume if self._sell_volume > 0 else 2.0
    
    def is_data_fresh(self, max_age_sec: float = 5.0) -> bool:
        """检查数据是否新鲜"""
        if self._last_update_time == 0:
            return False
        return (time.time() - self._last_update_time) < max_age_sec
    
    def reset_volume_stats(self):
        """重置成交量统计"""
        self._buy_volume = 0.0
        self._sell_volume = 0.0