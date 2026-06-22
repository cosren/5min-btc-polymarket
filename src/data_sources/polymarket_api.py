#!/usr/bin/env python3
"""Polymarket公开数据获取模块

使用Polymarket公开API获取真实BTC 5分钟市场数据（无需API密钥）

API调用方式:
- Gamma API /markets?slug=btc-updown-5m-{timestamp}  → 市场基本信息
- Gamma API /markets/{market_id}                      → 市场详情 + 价格
- Gamma API /events?slug=btc-updown-5m-{timestamp}    → 事件信息

价格数据:
- outcomePrices: JSON字符串 '["0.515", "0.485"]' → 需 json.loads()
- clobTokenIds:  JSON字符串 '["token1", "token2"]' → 需 json.loads()
- UP 价格: outcomePrices[0]，DOWN 价格: outcomePrices[1]
"""
import json
import time
import logging
from typing import Optional, Dict, List

import requests

logger = logging.getLogger(__name__)


class PolymarketPublicAPI:
    """Polymarket公开API客户端
    
    功能:
    - 获取BTC 5分钟市场数据
    - 获取市场价格（UP/DOWN价格）
    - 获取市场到期时间
    - 无需API密钥（只读）
    """
    
    GAMMA_URL = "https://gamma-api.polymarket.com"
    CLOB_URL = "https://clob.polymarket.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def _generate_slug(self, timestamp: int = None) -> str:
        """生成BTC 5分钟市场的 slug
        
        Polymarket slug 格式: btc-updown-5m-{timestamp}
        timestamp 对齐到5分钟边界
        """
        if timestamp is None:
            timestamp = int(time.time())
        ts = timestamp - (timestamp % 300)  # 对齐到5分钟
        return f"btc-updown-5m-{ts}"
    
    def _parse_json_field(self, value) -> list:
        """解析可能是JSON字符串的字段"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(value, list):
            return value
        return []
    
    def get_active_btc_5m_market(self, timestamp: int = None) -> Optional[Dict]:
        """获取当前活跃的BTC 5分钟市场数据
        
        Args:
            timestamp: Unix时间戳，为None则使用当前时间
            
        Returns:
            市场数据字典，包含:
            - market_id: 市场ID
            - event_id: 事件ID
            - slug: 市场slug
            - question: 市场问题
            - up_price: UP价格
            - down_price: DOWN价格
            - volume: 成交量
            - liquidity: 流动性
            - end_date: 到期时间
            - clob_token_ids: CLOB Token IDs
            - condition_id: Condition ID
        """
        slug = self._generate_slug(timestamp)
        
        try:
            # 1. 通过 slug 获取市场基本信息
            resp = self.session.get(
                f"{self.GAMMA_URL}/markets",
                params={"slug": slug},
                timeout=10
            )
            resp.raise_for_status()
            markets = resp.json()
            
            if not markets or not isinstance(markets, list):
                logger.warning(f"No market found for slug: {slug}")
                return None
            
            market = markets[0]
            market_id = market.get('id')
            
            # 2. 获取市场详情（含价格）
            resp = self.session.get(
                f"{self.GAMMA_URL}/markets/{market_id}",
                timeout=10
            )
            resp.raise_for_status()
            detail = resp.json()
            
            # 3. 解析 outcomePrices (JSON字符串 → Python列表)
            outcome_prices = self._parse_json_field(detail.get('outcomePrices', '[]'))
            up_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
            down_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
            
            # 4. 解析 clobTokenIds
            clob_token_ids = self._parse_json_field(detail.get('clobTokenIds', '[]'))
            
            # 5. 获取事件数据
            event = None
            try:
                resp = self.session.get(
                    f"{self.GAMMA_URL}/events",
                    params={"slug": slug},
                    timeout=10
                )
                resp.raise_for_status()
                events = resp.json()
                if events and isinstance(events, list):
                    event = events[0]
            except Exception as e:
                logger.debug(f"Event fetch skipped: {e}")
            
            result = {
                'market_id': market_id,
                'event_id': event.get('id') if event else None,
                'slug': slug,
                'question': market.get('question', ''),
                'up_price': up_price,
                'down_price': down_price,
                'side': 'UP',
                'volume': float(event.get('volume', 0)) if event else 0.0,
                'liquidity': float(market.get('liquidity', 0)),
                'end_date': market.get('endDate'),
                'clob_token_ids': clob_token_ids,
                'condition_id': market.get('conditionId'),
            }
            
            logger.info(f"BTC Market: UP={up_price:.3f} DOWN={down_price:.3f} | {slug}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch BTC market for {slug}: {e}")
            return None
    
    def get_market_with_retry(self, max_retries: int = 3, timestamp: int = None) -> Optional[Dict]:
        """获取市场数据（带重试）
        
        Args:
            max_retries: 最大重试次数
            timestamp: Unix时间戳
        """
        for attempt in range(max_retries):
            try:
                market = self.get_active_btc_5m_market(timestamp)
                if market:
                    return market
                logger.warning(f"Attempt {attempt + 1}: No market found, retrying...")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(2)
        
        return None
    
    def get_historical_markets(self, count: int = 5) -> List[Dict]:
        """获取历史BTC 5分钟市场数据
        
        Args:
            count: 获取的历史市场数量
            
        Returns:
            历史市场数据列表
        """
        now = int(time.time())
        results = []
        
        for i in range(count):
            ts = now - (i * 300) - (now % 300)
            try:
                data = self.get_active_btc_5m_market(timestamp=ts)
                if data:
                    results.append(data)
            except Exception:
                pass
        
        return results
    
    def get_clob_price(self, token_id: str) -> Optional[Dict]:
        """获取CLOB订单簿价格
        
        Args:
            token_id: CLOB Token ID
        """
        try:
            resp = self.session.get(
                f"{self.CLOB_URL}/book",
                params={"token_id": token_id},
                timeout=10
            )
            if resp.status_code == 200:
                book = resp.json()
                return {
                    'best_bid': book.get('bids', [{}])[0] if book.get('bids') else None,
                    'best_ask': book.get('asks', [{}])[0] if book.get('asks') else None,
                }
        except Exception as e:
            logger.debug(f"CLOB price fetch failed: {e}")
        
        return None