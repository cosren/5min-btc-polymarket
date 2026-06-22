#!/usr/bin/env python3
"""Deribit期权数据源模块

提供BTC期权隐含波动率(IV)数据
"""
import time
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class DeribitWebSocket:
    """Deribit WebSocket客户端（模拟模式）
    
    功能:
    - 订阅BTC期权数据
    - 获取最近到期日的隐含波动率(IV)
    - IV-RV比率计算
    """
    
    def __init__(
        self,
        currency: str = 'BTC',
        ws_url: str = 'wss://www.deribit.com/ws/api/v2'
    ):
        self.currency = currency
        self.ws_url = ws_url
        
        # 数据存储
        self._iv_data: Dict[str, float] = {}
        self._last_update_time: float = 0
        self._current_iv: float = 0.60  # 默认60% IV
    
    async def connect(self):
        """建立WebSocket连接（模拟模式直接返回）"""
        logger.info(f"DeribitWebSocket initialized (simulator mode)")
    
    async def disconnect(self):
        """断开WebSocket连接"""
        logger.info("DeribitWebSocket disconnected")
    
    def update_data(self):
        """更新模拟数据"""
        import random
        # IV随机波动
        self._current_iv = max(0.30, min(1.0, self._current_iv + random.gauss(0, 0.02)))
        self._last_update_time = time.time()
    
    def get_nearest_expiry_iv(self) -> Optional[float]:
        """获取最近到期日的隐含波动率"""
        return self._current_iv
    
    def calculate_iv_rv_ratio(self, realized_vol: float) -> Optional[float]:
        """计算IV-RV比率"""
        if realized_vol <= 0:
            return None
        return self._current_iv / realized_vol
    
    def is_data_fresh(self, max_age_sec: float = 5.0) -> bool:
        """检查数据是否新鲜"""
        if self._last_update_time == 0:
            return False
        return (time.time() - self._last_update_time) < max_age_sec