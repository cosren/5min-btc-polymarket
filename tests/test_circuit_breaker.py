#!/usr/bin/env python3
"""熔断器单元测试"""
import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.risk.circuit_breaker import CircuitBreaker, TradeRecord


class TestCircuitBreaker(unittest.TestCase):
    """测试熔断器"""
    
    def setUp(self):
        self.cb = CircuitBreaker(
            daily_max_loss_pct=10.0,
            max_consecutive_losses=3,
            max_position_size_pct=5.0,
            max_drawdown_pct=15.0
        )
    
    def test_daily_loss_circuit_breaker(self):
        """测试每日亏损熔断"""
        # 亏损10%应该触发
        self.assertTrue(self.cb.check_daily_loss(current_equity=1000, daily_pnl=-100))
        
        # 亏损5%不应该触发
        self.assertFalse(self.cb.check_daily_loss(current_equity=1000, daily_pnl=-50))
    
    def test_consecutive_losses_circuit_breaker(self):
        """测试连续亏损熔断"""
        self.assertTrue(self.cb.check_consecutive_losses(3))
        self.assertFalse(self.cb.check_consecutive_losses(2))
    
    def test_position_size_limit(self):
        """测试仓位上限"""
        # $60仓位在$1000资金中占6%，超过5%限制
        self.assertTrue(self.cb.check_position_size(position_usd=60, equity=1000))
        
        # $40仓位占4%，未超过
        self.assertFalse(self.cb.check_position_size(position_usd=40, equity=1000))
    
    def test_drawdown_circuit_breaker(self):
        """测试回撤熔断"""
        # 15%回撤应该触发
        self.assertTrue(self.cb.check_drawdown(current_equity=850, peak_equity=1000))
        
        # 10%回撤不应该触发
        self.assertFalse(self.cb.check_drawdown(current_equity=900, peak_equity=1000))
    
    def test_record_trade(self):
        """测试记录交易"""
        self.cb.record_trade(TradeRecord(
            timestamp=1000, pnl=-10, side='UP', market='test'
        ))
        self.assertEqual(self.cb._state.consecutive_losses, 1)
        
        self.cb.record_trade(TradeRecord(
            timestamp=1001, pnl=5, side='UP', market='test'
        ))
        self.assertEqual(self.cb._state.consecutive_losses, 0)
    
    def test_reset(self):
        """测试重置"""
        self.cb._state.is_active = True
        self.cb.reset()
        self.assertFalse(self.cb._state.is_active)
    
    def test_should_stop_trading(self):
        """测试综合停止交易判断"""
        # 正常情况不应该停止
        self.assertFalse(self.cb.should_stop_trading(
            equity=1000,
            daily_pnl=-50,
            consecutive_losses=1
        ))
        
        # 连续亏损3次应该停止
        self.assertTrue(self.cb.should_stop_trading(
            equity=1000,
            daily_pnl=-50,
            consecutive_losses=3
        ))
    
    def test_get_risk_summary(self):
        """测试获取风险摘要"""
        summary = self.cb.get_risk_summary(equity=1000)
        
        self.assertIn('is_active', summary)
        self.assertIn('daily_loss_pct', summary)
        self.assertIn('consecutive_losses', summary)
        self.assertIn('max_drawdown_pct', summary)


if __name__ == '__main__':
    unittest.main()