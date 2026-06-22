#!/usr/bin/env python3
"""延迟优化模块

测量和优化API延迟，确保交易执行速度
"""
import time
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass, field

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


@dataclass
class LatencyMeasurement:
    """延迟测量结果"""
    endpoint: str
    latency_ms: float
    timestamp: float
    success: bool


class LatencyOptimizer:
    """延迟优化器
    
    功能:
    - 测量各API端点延迟
    - 动态调整Gas费
    - 提供延迟监控和告警
    
    使用示例:
        optimizer = LatencyOptimizer()
        latency = optimizer.measure_api_latency('https://clob.polymarket.com')
        gas_config = optimizer.optimize_gas_fees('high')
    """
    
    def __init__(
        self,
        latency_threshold_ms: float = 100.0,
        alert_threshold_ms: float = 200.0
    ):
        """初始化
        
        Args:
            latency_threshold_ms: 延迟阈值(毫秒)
            alert_threshold_ms: 告警阈值(毫秒)
        """
        self.latency_threshold_ms = latency_threshold_ms
        self.alert_threshold_ms = alert_threshold_ms
        
        self._measurements: List[LatencyMeasurement] = []
        self._endpoint_stats: Dict[str, List[float]] = {}
    
    def measure_api_latency(
        self,
        endpoint: str,
        timeout: float = 5.0
    ) -> float:
        """测量API延迟
        
        Args:
            endpoint: API端点URL
            timeout: 超时时间(秒)
        
        Returns:
            延迟(毫秒)
        """
        if requests is None:
            logger.warning("requests not installed, cannot measure latency")
            return -1.0
        
        try:
            start = time.time()
            response = requests.get(endpoint, timeout=timeout)
            latency_ms = (time.time() - start) * 1000
            
            measurement = LatencyMeasurement(
                endpoint=endpoint,
                latency_ms=latency_ms,
                timestamp=time.time(),
                success=response.status_code == 200
            )
            
            self._measurements.append(measurement)
            
            if endpoint not in self._endpoint_stats:
                self._endpoint_stats[endpoint] = []
            self._endpoint_stats[endpoint].append(latency_ms)
            
            # 保留最近100次测量
            if len(self._endpoint_stats[endpoint]) > 100:
                self._endpoint_stats[endpoint] = self._endpoint_stats[endpoint][-100:]
            
            # 检查是否超过告警阈值
            if latency_ms > self.alert_threshold_ms:
                logger.warning(
                    f"High latency detected: {endpoint} = {latency_ms:.0f}ms "
                    f"(threshold: {self.alert_threshold_ms}ms)"
                )
            
            return latency_ms
            
        except Exception as e:
            logger.error(f"Failed to measure latency for {endpoint}: {e}")
            
            measurement = LatencyMeasurement(
                endpoint=endpoint,
                latency_ms=-1.0,
                timestamp=time.time(),
                success=False
            )
            self._measurements.append(measurement)
            
            return -1.0
    
    def get_average_latency(self, endpoint: str) -> float:
        """获取平均延迟
        
        Args:
            endpoint: API端点
        
        Returns:
            平均延迟(毫秒)
        """
        if endpoint not in self._endpoint_stats:
            return -1.0
        
        stats = self._endpoint_stats[endpoint]
        if not stats:
            return -1.0
        
        return sum(stats) / len(stats)
    
    def optimize_gas_fees(self, urgency: str = 'normal') -> Dict[str, str]:
        """根据紧急程度优化Gas费
        
        Args:
            urgency: 紧急程度 ('high', 'normal', 'low')
        
        Returns:
            Gas配置
        """
        gas_profiles = {
            'high': {
                'priority_fee': '50 gwei',
                'max_fee': '100 gwei'
            },
            'normal': {
                'priority_fee': '20 gwei',
                'max_fee': '50 gwei'
            },
            'low': {
                'priority_fee': '10 gwei',
                'max_fee': '30 gwei'
            }
        }
        
        return gas_profiles.get(urgency, gas_profiles['normal'])
    
    def should_trade_based_on_latency(
        self,
        endpoint: str
    ) -> bool:
        """根据延迟判断是否应该交易
        
        Args:
            endpoint: API端点
        
        Returns:
            True表示延迟在可接受范围内
        """
        avg_latency = self.get_average_latency(endpoint)
        
        if avg_latency < 0:
            return False
        
        return avg_latency <= self.latency_threshold_ms
    
    def get_latency_report(self) -> Dict[str, Dict[str, float]]:
        """获取延迟报告
        
        Returns:
            各端点的延迟统计
        """
        report = {}
        
        for endpoint, latencies in self._endpoint_stats.items():
            if not latencies:
                continue
            
            report[endpoint] = {
                'avg_ms': sum(latencies) / len(latencies),
                'min_ms': min(latencies),
                'max_ms': max(latencies),
                'p50_ms': sorted(latencies)[len(latencies) // 2],
                'p95_ms': sorted(latencies)[int(len(latencies) * 0.95)],
                'measurements': len(latencies)
            }
        
        return report