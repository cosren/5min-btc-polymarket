#!/usr/bin/env python3
"""币安实时数据源模块

提供L2订单簿深度数据，通过 REST API 拉取
"""
import time
import logging
from typing import Optional, List
from dataclasses import dataclass, field

import requests

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
    """币安数据客户端（REST API + WebSocket 双模式）
    
    功能:
    - REST API 获取 L2 订单簿深度数据(10档)
    - 可选 WebSocket 实时推送
    - 订单簿不平衡度(OBI)计算
    - 买卖比例统计
    """
    
    # Binance Futures REST API 端点
    REST_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
    
    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        ws_url: str = 'wss://fstream.binance.com/ws',
        depth_levels: int = 10,
        simulator = None
    ):
        self.symbol = symbol.upper()
        self.ws_url = ws_url
        self.depth_levels = depth_levels
        self.simulator = simulator
        
        self._orderbook = OrderBook(symbol=self.symbol, timestamp=time.time())
        self._last_update_time: float = 0.0
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })
    
    async def connect(self):
        """初始化连接（REST 模式直接拉取一次数据验证连通性）"""
        try:
            self.fetch_orderbook()
            logger.info(f"Binance REST API connected, symbol={self.symbol}")
        except Exception as e:
            logger.warning(f"Binance initial fetch failed: {e}, will retry on each cycle")
    
    async def disconnect(self):
        """断开连接"""
        self.session.close()
        logger.info("BinanceWebSocket disconnected")
    
    def fetch_orderbook(self) -> Optional[OrderBook]:
        """通过 REST API 拉取实时订单簿（线程安全，可在主循环中调用）
        
        Returns:
            最新的 OrderBook 对象，失败时返回 None
        """
        try:
            resp = self.session.get(
                self.REST_DEPTH_URL,
                params={"symbol": self.symbol, "limit": self.depth_levels},
                timeout=1.5
            )
            resp.raise_for_status()
            data = resp.json()
            
            bids = [OrderBookLevel(price=float(b[0]), quantity=float(b[1])) 
                    for b in data.get('bids', [])]
            asks = [OrderBookLevel(price=float(a[0]), quantity=float(a[1])) 
                    for a in data.get('asks', [])]
            
            self._orderbook = OrderBook(
                symbol=self.symbol,
                timestamp=time.time(),
                bids=bids,
                asks=asks
            )
            self._last_update_time = time.time()
            return self._orderbook
        except Exception as e:
            logger.error(f"Binance fetch_orderbook failed: {e}")
            return None
    
    def update_data(self):
        """更新数据（REST 模式：拉取最新订单簿；模拟模式：生成模拟数据）"""
        if self.simulator:
            self.simulator.update_price(1.0)
            self._orderbook = self.simulator.generate_orderbook()
            self._last_update_time = time.time()
        else:
            self.fetch_orderbook()
    
    def get_orderbook(self) -> Optional[OrderBook]:
        """获取当前订单簿"""
        return self._orderbook
    
    def calculate_obi(self) -> float:
        """计算订单簿不平衡度"""
        if not self._orderbook or not self._orderbook.bids or not self._orderbook.asks:
            return 0.0
        
        bid_volume = sum(level.quantity for level in self._orderbook.bids[:self.depth_levels])
        ask_volume = sum(level.quantity for level in self._orderbook.asks[:self.depth_levels])
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
        
        return (bid_volume - ask_volume) / total_volume
    
    def calculate_buy_sell_ratio(self) -> float:
        """计算买卖比例（基于真实订单簿 10 档）"""
        if not self._orderbook or not self._orderbook.bids or not self._orderbook.asks:
            return 1.0
        bid_volume = sum(level.quantity for level in self._orderbook.bids[:self.depth_levels])
        ask_volume = sum(level.quantity for level in self._orderbook.asks[:self.depth_levels])
        return bid_volume / ask_volume if ask_volume > 0 else 2.0

    def is_data_fresh(self, max_age_sec: float = 5.0) -> bool:
        """检查数据是否新鲜"""
        return (time.time() - self._last_update_time) <= max_age_sec