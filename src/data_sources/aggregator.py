#!/usr/bin/env python3
"""数据聚合器模块

统一管理多源数据输入，提供标准化接口
"""
import asyncio
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AggregatedMarketData:
    """聚合后的市场数据"""
    timestamp: float
    
    # Polymarket数据
    poly_up_price: float = 0.0
    poly_down_price: float = 0.0
    poly_spread: float = 0.0
    
    # 币安数据
    binance_obi: float = 0.0
    binance_buy_sell_ratio: float = 1.0
    binance_mid_price: float = 0.0
    
    # Deribit数据
    deribit_iv: Optional[float] = None
    deribit_iv_rv_ratio: Optional[float] = None
    
    # 计算指标
    combined_signal_strength: float = 0.0
    data_quality_score: float = 1.0
    
    # 状态
    is_data_fresh: bool = False
    sources_active: int = 0


class MarketDataAggregator:
    """市场数据聚合器
    
    功能:
    - 统一多源数据接口
    - 毫秒级时间戳对齐
    - 数据质量检查
    - 计算综合信号强度
    
    使用示例:
        aggregator = MarketDataAggregator()
        await aggregator.initialize_sources()
        data = await aggregator.get_aggregated_data()
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 数据源
        self.binance_ws = None
        self.deribit_ws = None
        self.hyperliquid_ws = None
        
        # 数据新鲜度阈值
        self.max_data_age_sec = self.config.get('max_data_age_sec', 5.0)
        
        # 数据源状态
        self._sources_status: Dict[str, bool] = {
            'binance': False,
            'deribit': False,
            'hyperliquid': False
        }
    
    async def initialize_sources(self):
        """初始化所有数据源
        
        根据配置启用相应的数据源
        """
        data_sources_config = self.config.get('data_sources', {})
        
        # 初始化币安
        if data_sources_config.get('binance', {}).get('enabled', True):
            try:
                from src.data_sources.binance_ws import BinanceWebSocket
                binance_config = data_sources_config['binance']
                self.binance_ws = BinanceWebSocket(
                    symbol=binance_config.get('symbols', ['BTCUSDT'])[0],
                    ws_url=binance_config.get('ws_url', 'wss://fstream.binance.com/ws'),
                    depth_levels=binance_config.get('depth_levels', 10)
                )
                await self.binance_ws.connect()
                self._sources_status['binance'] = True
                logger.info("Binance WebSocket initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Binance: {e}")
        
        # 初始化Deribit
        if data_sources_config.get('deribit', {}).get('enabled', True):
            try:
                from src.data_sources.deribit_ws import DeribitWebSocket
                deribit_config = data_sources_config['deribit']
                self.deribit_ws = DeribitWebSocket(
                    currency=deribit_config.get('currency', 'BTC'),
                    ws_url=deribit_config.get('ws_url', 'wss://www.deribit.com/ws/api/v2')
                )
                await self.deribit_ws.connect()
                self._sources_status['deribit'] = True
                logger.info("Deribit WebSocket initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Deribit: {e}")
        
        # 初始化Hyperliquid
        if data_sources_config.get('hyperliquid', {}).get('enabled', False):
            try:
                from src.data_sources.hyperliquid_ws import HyperliquidWebSocket
                hyperliquid_config = data_sources_config['hyperliquid']
                self.hyperliquid_ws = HyperliquidWebSocket(
                    coin=hyperliquid_config.get('coin', 'BTC'),
                    ws_url=hyperliquid_config.get('ws_url', 'wss://api.hyperliquid.xyz/ws')
                )
                await self.hyperliquid_ws.connect()
                self._sources_status['hyperliquid'] = True
                logger.info("Hyperliquid WebSocket initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Hyperliquid: {e}")
    
    def get_aggregated_data(
        self,
        poly_data: Optional[Dict[str, Any]] = None
    ) -> AggregatedMarketData:
        """获取聚合后的市场数据
        
        Args:
            poly_data: Polymarket市场数据
        
        Returns:
            聚合后的市场数据
        """
        data = AggregatedMarketData(timestamp=time.time())
        
        # 填充Polymarket数据
        if poly_data:
            data.poly_up_price = poly_data.get('up_price', 0.0)
            data.poly_down_price = poly_data.get('down_price', 0.0)
            data.poly_spread = poly_data.get('spread', 0.0)
        
        # 填充币安数据
        if self.binance_ws and self._sources_status['binance']:
            try:
                data.binance_obi = self.binance_ws.calculate_obi()
                data.binance_buy_sell_ratio = self.binance_ws.calculate_buy_sell_ratio()
                
                orderbook = self.binance_ws.get_orderbook()
                if orderbook and orderbook.bids and orderbook.asks:
                    data.binance_mid_price = (
                        orderbook.bids[0].price + orderbook.asks[0].price
                    ) / 2
                
                if self.binance_ws.is_data_fresh(self.max_data_age_sec):
                    data.sources_active += 1
            except Exception as e:
                logger.error(f"Error getting Binance data: {e}")
        
        # 填充Deribit数据
        if self.deribit_ws and self._sources_status['deribit']:
            try:
                data.deribit_iv = self.deribit_ws.get_nearest_expiry_iv()
                
                if self.deribit_ws.is_data_fresh(self.max_data_age_sec):
                    data.sources_active += 1
            except Exception as e:
                logger.error(f"Error getting Deribit data: {e}")
        
        # 填充Hyperliquid数据
        if self.hyperliquid_ws and self._sources_status['hyperliquid']:
            try:
                hyperliquid_obi = self.hyperliquid_ws.calculate_obi()
                
                if self.hyperliquid_ws.is_data_fresh(self.max_data_age_sec):
                    data.sources_active += 1
            except Exception as e:
                logger.error(f"Error getting Hyperliquid data: {e}")
        
        # 计算数据质量分数
        data.data_quality_score = data.sources_active / 3.0
        # Polymarket 数据可用时也算活跃，纸面交易模式下只需 Polymarket 即可
        has_poly_data = poly_data is not None and poly_data.get('up_price', 0) > 0
        data.is_data_fresh = data.sources_active >= 2 or has_poly_data
        
        # 计算综合信号强度
        data.combined_signal_strength = self._calculate_combined_signal(data)
        
        return data
    
    def _calculate_combined_signal(self, data: AggregatedMarketData) -> float:
        """计算综合信号强度
        
        结合OBI、买卖比、IV等多个指标
        
        Args:
            data: 聚合数据
        
        Returns:
            信号强度 [-1, 1]
        """
        signal = 0.0
        weight_sum = 0.0
        
        # OBI信号 (权重40%)
        if data.binance_obi != 0:
            signal += data.binance_obi * 0.4
            weight_sum += 0.4
        
        # 买卖比信号 (权重30%)
        if data.binance_buy_sell_ratio != 1.0:
            ratio_signal = (data.binance_buy_sell_ratio - 1.0) / data.binance_buy_sell_ratio
            signal += ratio_signal * 0.3
            weight_sum += 0.3
        
        # IV-RV比率信号 (权重30%)
        if data.deribit_iv_rv_ratio is not None:
            # IV/RV < 1 表示实际波动高于预期，利好动量策略
            iv_signal = 1.0 - data.deribit_iv_rv_ratio
            signal += iv_signal * 0.3
            weight_sum += 0.3
        
        # 归一化
        if weight_sum > 0:
            signal /= weight_sum
        
        return signal
    
    def should_trade(
        self,
        data: AggregatedMarketData,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """判断是否应该交易
        
        Args:
            data: 聚合数据
            filters: 过滤规则配置
        
        Returns:
            (是否可以交易, 原因)
        """
        filters = filters or self.config.get('filters', {})
        
        # 检查数据质量
        if not data.is_data_fresh:
            return False, "data_not_fresh"
        
        # OBI过滤
        obi_config = filters.get('obi', {})
        if obi_config.get('enabled', True):
            obi_threshold = obi_config.get('threshold', 0.35)
            if abs(data.binance_obi) < obi_threshold:
                return False, f"obi_below_threshold:{data.binance_obi:.3f}"
        
        # 成交量比率过滤
        volume_config = filters.get('volume_ratio', {})
        if volume_config.get('enabled', True):
            min_ratio = volume_config.get('buy_sell_ratio_min', 1.2)
            if data.binance_buy_sell_ratio < min_ratio:
                return False, f"volume_ratio_low:{data.binance_buy_sell_ratio:.2f}"
        
        # IV-RV比率过滤
        iv_config = filters.get('iv_rv', {})
        if iv_config.get('enabled', True) and data.deribit_iv_rv_ratio is not None:
            max_ratio = iv_config.get('iv_rv_ratio_max', 1.5)
            if data.deribit_iv_rv_ratio > max_ratio:
                if iv_config.get('pause_strategy_when_elevated', True):
                    return False, f"iv_elevated:{data.deribit_iv_rv_ratio:.2f}"
        
        return True, "all_filters_passed"
    
    async def close(self):
        """关闭所有数据源"""
        if self.binance_ws:
            await self.binance_ws.disconnect()
        if self.deribit_ws:
            await self.deribit_ws.disconnect()
        if self.hyperliquid_ws:
            await self.hyperliquid_ws.disconnect()
        
        logger.info("All data sources closed")
    
    def get_sources_status(self) -> Dict[str, bool]:
        """获取数据源状态"""
        return self._sources_status.copy()