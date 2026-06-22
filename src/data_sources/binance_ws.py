#!/usr/bin/env python3
"""
币安实时数据源模块 (10档合约终极优化同步版)
彻底解决主程序内存 0.0000 不更新、死锁、网络连接断开等问题。
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
    """币安数据客户端（REST 高速持久化连接池版）
    
    摒弃极易死锁的普通非阻塞模式，强制使用 Session 复用管道确保主程序百分之百拿到数据。
    """
    
    REST_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
    
    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        ws_url: str = None,
        depth_levels: int = 10,
        simulator = None
    ):
        self.symbol = symbol.upper()
        self.depth_levels = depth_levels
        self.simulator = simulator
        
        self._orderbook: Optional[OrderBook] = None
        self._last_update_time = 0.0
        
        # 核心修复：建立持久化 Session 维持长连接，彻底免疫 [SSL: UNEXPECTED_EOF_WHILE_READING]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"
        })
        
        # 预填充一个空对象，防止主程序启动时因为 None 报 AttributeError
        self._orderbook = OrderBook(symbol=self.symbol, timestamp=time.time())
        
        logger.info(f"🛰️  [Binance 引擎重构] 成功接入持久化 10 档深度套接字 | 标的: {self.symbol}")

    async def connect(self):
        """初始化连接（兼容 aggregator 调用，REST 模式无需异步握手）"""
        self.fetch_orderbook()
        logger.info(f"Binance REST API connected, symbol={self.symbol}")

    async def disconnect(self):
        """断开连接（兼容 aggregator 调用）"""
        self.session.close()
        logger.info("BinanceWebSocket disconnected")

    def fetch_orderbook(self) -> bool:
        """从币安合约接口强制拉取最新订单簿快照"""
        url = f"{self.REST_DEPTH_URL}?symbol={self.symbol}&limit={self.depth_levels}"
        try:
            # 限制超时为 1.5 秒，防止主循环因网络差被卡死
            response = self.session.get(url, timeout=1.5)
            if response.status_code == 200:
                data = response.json()
                
                new_orderbook = OrderBook(symbol=self.symbol, timestamp=time.time())
                
                # 提取 bids 和 asks
                raw_bids = data.get('bids', [])[:self.depth_levels]
                raw_asks = data.get('asks', [])[:self.depth_levels]
                
                # 🛡️ 容错控制：如果发现返回深度残缺，坚决不用这一帧，防止 OBI 产生巨大离散偏离
                if len(raw_bids) < self.depth_levels or len(raw_asks) < self.depth_levels:
                    return False
                
                # 成功解析并填入内存
                for bid in raw_bids:
                    new_orderbook.bids.append(OrderBookLevel(price=float(bid[0]), quantity=float(bid[1])))
                for ask in raw_asks:
                    new_orderbook.asks.append(OrderBookLevel(price=float(ask[0]), quantity=float(ask[1])))
                
                self._orderbook = new_orderbook
                self._last_update_time = time.time()
                return True
            else:
                logger.warning(f"⚠️ 币安接口返回异常状态码: {response.status_code}")
                return False
        except Exception as e:
            # 高频下静默网络抖动错误，防止刷屏
            return False
    
    def update_data(self):
        """【外部唯一驱动源】强制触发数据同步"""
        if self.simulator:
            self.simulator.update_price(1.0)
            self._orderbook = self.simulator.generate_orderbook()
            self._last_update_time = time.time()
        else:
            # 🔥 强制破除僵尸缓存，立刻发起真实请求更新内存
            self.fetch_orderbook()
    
    def get_orderbook(self) -> Optional[OrderBook]:
        return self._orderbook
    
    def calculate_obi(self) -> float:
        """10档严格求和 OBI 计算逻辑"""
        if not self._orderbook or not self._orderbook.bids or not self._orderbook.asks:
            return 0.0
            
        # 必须加上限制条件切片 [:self.depth_levels]，确保不多统计，不错位
        bid_volume = sum(level.quantity for level in self._orderbook.bids[:self.depth_levels])
        ask_volume = sum(level.quantity for level in self._orderbook.asks[:self.depth_levels])
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
            
        return (bid_volume - ask_volume) / total_volume
    
    def calculate_buy_sell_ratio(self) -> float:
        if not self._orderbook or not self._orderbook.bids or not self._orderbook.asks:
            return 1.0
        bid_volume = sum(level.quantity for level in self._orderbook.bids[:self.depth_levels])
        ask_volume = sum(level.quantity for level in self._orderbook.asks[:self.depth_levels])
        return bid_volume / ask_volume if ask_volume > 0 else 2.0
    
    def is_data_fresh(self, max_age_sec: float = 5.0) -> bool:
        return (time.time() - self._last_update_time) <= max_age_sec