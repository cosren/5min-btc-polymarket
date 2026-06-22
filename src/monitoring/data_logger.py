#!/usr/bin/env python3
"""CSV数据记录模块

记录每次交易尝试到CSV文件，用于回测和验证
"""
import csv
import os
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TradeLogEntry:
    """交易日志条目"""
    timestamp: str
    market_slug: str
    side: str
    obi: float
    gbm_win_prob: float
    ev: float
    kelly_fraction: float
    stake_usd: float
    entry_price: float
    exit_price: Optional[float]
    pnl: Optional[float]
    result: str
    slippage: float
    latency_ms: float
    time_to_expiry: float
    is_sniper: bool
    circuit_breaker_active: bool


class DataLogger:
    """数据记录器
    
    功能:
    - 记录每次交易尝试到CSV
    - 支持dry-run和实盘模式
    - 提供数据查询和统计
    
    使用示例:
        logger = DataLogger(log_dir='./data/logs')
        logger.log_trade_attempt(
            timestamp='2024-01-01T12:00:00Z',
            market_slug='btc-updown-5m-123456',
            side='UP',
            obi=0.45,
            gbm_win_prob=0.75,
            ev=0.08,
            kelly_fraction=0.02,
            stake_usd=5.0,
            entry_price=0.75,
            exit_price=0.80,
            pnl=2.5,
            result='win',
            slippage=0.01,
            latency_ms=50.0,
            time_to_expiry=120.0,
            is_sniper=False,
            circuit_breaker_active=False
        )
    """
    
    def __init__(self, log_dir: str = './data/logs'):
        """初始化
        
        Args:
            log_dir: 日志目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._log_file = self.log_dir / f"trades_{time.strftime('%Y%m%d')}.csv"
        self._entries: List[TradeLogEntry] = []
        
        # 初始化CSV文件
        if not self._log_file.exists():
            self._write_header()
    
    def _write_header(self):
        """写入CSV表头"""
        headers = [
            'timestamp', 'market_slug', 'side', 'obi', 'gbm_win_prob',
            'ev', 'kelly_fraction', 'stake_usd', 'entry_price',
            'exit_price', 'pnl', 'result', 'slippage', 'latency_ms',
            'time_to_expiry', 'is_sniper', 'circuit_breaker_active'
        ]
        
        with open(self._log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    def log_trade_attempt(
        self,
        timestamp: str,
        market_slug: str,
        side: str,
        obi: float,
        gbm_win_prob: float,
        ev: float,
        kelly_fraction: float,
        stake_usd: float,
        entry_price: float,
        exit_price: Optional[float] = None,
        pnl: Optional[float] = None,
        result: str = 'pending',
        slippage: float = 0.0,
        latency_ms: float = 0.0,
        time_to_expiry: float = 0.0,
        is_sniper: bool = False,
        circuit_breaker_active: bool = False
    ):
        """记录交易尝试
        
        Args:
            timestamp: 时间戳
            market_slug: 市场标识
            side: 方向 (UP/DOWN)
            obi: 订单簿不平衡度
            gbm_win_prob: GBM胜率
            ev: 期望值
            kelly_fraction: 凯利分数
            stake_usd: 下注金额
            entry_price: 入场价格
            exit_price: 出场价格
            pnl: 盈亏
            result: 结果 (win/loss/pending)
            slippage: 滑点
            latency_ms: 延迟(毫秒)
            time_to_expiry: 距离到期时间(秒)
            is_sniper: 是否狙击模式
            circuit_breaker_active: 熔断器是否激活
        """
        entry = TradeLogEntry(
            timestamp=timestamp,
            market_slug=market_slug,
            side=side,
            obi=obi,
            gbm_win_prob=gbm_win_prob,
            ev=ev,
            kelly_fraction=kelly_fraction,
            stake_usd=stake_usd,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            result=result,
            slippage=slippage,
            latency_ms=latency_ms,
            time_to_expiry=time_to_expiry,
            is_sniper=is_sniper,
            circuit_breaker_active=circuit_breaker_active
        )
        
        self._entries.append(entry)
        self._write_entry(entry)
        
        logger.debug(f"Logged trade: {side} {market_slug} result={result} pnl={pnl}")
    
    def _write_entry(self, entry: TradeLogEntry):
        """写入单条记录到CSV"""
        with open(self._log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                entry.timestamp,
                entry.market_slug,
                entry.side,
                entry.obi,
                entry.gbm_win_prob,
                entry.ev,
                entry.kelly_fraction,
                entry.stake_usd,
                entry.entry_price,
                entry.exit_price or '',
                entry.pnl or '',
                entry.result,
                entry.slippage,
                entry.latency_ms,
                entry.time_to_expiry,
                entry.is_sniper,
                entry.circuit_breaker_active
            ])
    
    def get_entries(self, limit: int = 100) -> List[TradeLogEntry]:
        """获取最近的交易记录
        
        Args:
            limit: 返回数量限制
        
        Returns:
            交易记录列表
        """
        return self._entries[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计字典
        """
        if not self._entries:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'avg_slippage': 0.0,
                'avg_latency_ms': 0.0
            }
        
        completed = [e for e in self._entries if e.result in ('win', 'loss')]
        wins = [e for e in completed if e.result == 'win']
        
        total_pnl = sum(e.pnl for e in completed if e.pnl is not None)
        avg_pnl = total_pnl / len(completed) if completed else 0.0
        
        return {
            'total_trades': len(self._entries),
            'completed_trades': len(completed),
            'wins': len(wins),
            'losses': len(completed) - len(wins),
            'win_rate': len(wins) / len(completed) * 100 if completed else 0.0,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_slippage': sum(e.slippage for e in self._entries) / len(self._entries),
            'avg_latency_ms': sum(e.latency_ms for e in self._entries) / len(self._entries)
        }
    
    @property
    def log_file(self) -> Path:
        """获取日志文件路径"""
        return self._log_file