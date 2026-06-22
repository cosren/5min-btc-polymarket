#!/usr/bin/env python3
"""凯利公式和熔断器单元测试"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.risk.kelly_criterion import KellyCriterion
from src.risk.circuit_breaker import CircuitBreaker, TradeRecord


class TestKellyCriterion(unittest.TestCase):
    """测试凯利公式"""
    
    def setUp(self):
        self.kelly = KellyCriterion(max_position_pct=5.0, kelly_fraction_type='quarter')
    
    def test_positive_kelly_fraction(self):
        """测试正凯利值"""
        # 75%胜率，0.5赔率
        f = self.kelly.calculate_kelly_fraction(p_win=0.75, payout_ratio=0.5)
        self.assertGreater(f, 0)
    
    def test_negative_kelly_fraction(self):
        """测试负凯利值(不应下注)"""
        # 40%胜率，0.5赔率
        f = self.kelly.calculate_kelly_fraction(p_win=0.40, payout_ratio=0.5)
        self.assertLessEqual(f, 0)
    
    def test_conservative_fraction(self):
        """测试保守分数"""
        # 使用更大的max_position_pct避免限制
        kelly = KellyCriterion(max_position_pct=20.0, kelly_fraction_type='quarter')
        
        f_star = 0.2  # 20%凯利值
        quarter = kelly.get_conservative_fraction(f_star, 'quarter')
        half = kelly.get_conservative_fraction(f_star, 'half')
        full = kelly.get_conservative_fraction(f_star, 'full')
        
        self.assertAlmostEqual(quarter, 0.05)  # 0.2 * 0.25
        self.assertAlmostEqual(half, 0.10)     # 0.2 * 0.5
        self.assertAlmostEqual(full, 0.20)     # 0.2 * 1.0
    
    def test_position_size(self):
        """测试仓位计算"""
        size = self.kelly.calculate_position_size(
            equity=1000,
            p_win=0.75,
            payout_ratio=0.5
        )
        self.assertGreater(size, 0)
        self.assertLessEqual(size, 50)  # 最大5% = $50
    
    def test_should_bet(self):
        """测试是否应该下注"""
        self.assertTrue(self.kelly.should_bet(p_win=0.75, payout_ratio=0.5))
        self.assertFalse(self.kelly.should_bet(p_win=0.40, payout_ratio=0.5))


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


if __name__ == '__main__':
    unittest.main()