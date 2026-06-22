#!/usr/bin/env python3
"""Hyperliquid永续合约数据源模块

作为备用数据源，提供BTC永续合约价格和订单簿数据
"""
import time
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class HyperliquidWebSocket:
    """Hyperliquid WebSocket客户端（模拟模式）
    
    功能:
    - 订阅BTC永续合约价格
    - 获取订单簿数据
    - 计算OBI作为备用信号
    """
    
    def __init__(
        self,
        coin: str = 'BTC',
        ws_url: str = 'wss://api.hyperliquid.xyz/ws'
    ):
        self.coin = coin
        self.ws_url = ws_url
        
        # 数据存储
        self._price: float = 0.0
        self._last_update_time: float = 0
        self._obi: float = 0.0
    
    async def connect(self):
        """建立WebSocket连接（模拟模式直接返回）"""
        logger.info(f"HyperliquidWebSocket initialized (simulator mode)")
    
    async def disconnect(self):
        """断开WebSocket连接"""
        logger.info("HyperliquidWebSocket disconnected")
    
    def update_data(self):
        """更新模拟数据"""
        import random
        self._obi = random.uniform(-0.5, 0.5)
        self._last_update_time = time.time()
    
    def calculate_obi(self) -> float:
        """计算订单簿不平衡度"""
        return self._obi
    
    def get_price(self) -> float:
        """获取当前价格"""
        return self._price
    
    def is_data_fresh(self, max_age_sec: float = 5.0) -> bool:
        """检查数据是否新鲜"""
        if self._last_update_time == 0:
            return False
        return (time.time() - self._last_update_time) < max_age_sec