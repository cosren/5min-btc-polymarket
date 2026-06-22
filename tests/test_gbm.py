#!/usr/bin/env python3
"""GBM模型单元测试"""
import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.gbm import GeometricBrownianMotion


class TestGeometricBrownianMotion(unittest.TestCase):
    """测试几何布朗运动模型"""
    
    def setUp(self):
        """测试前准备"""
        self.gbm = GeometricBrownianMotion(mu=0.001, sigma=0.02)
    
    def test_win_probability_above_target(self):
        """测试价格高于目标时的胜率"""
        # 当前价格已经高于目标，胜率应该>0.5
        prob = self.gbm.calculate_win_probability(
            current_price=65000,
            target_price=64900,
            time_to_expiry=120
        )
        self.assertGreater(prob, 0.5)
        self.assertLessEqual(prob, 1.0)
    
    def test_win_probability_below_target(self):
        """测试价格低于目标时的胜率"""
        # 当前价格低于目标，胜率应该<0.5
        prob = self.gbm.calculate_win_probability(
            current_price=64900,
            target_price=65000,
            time_to_expiry=120
        )
        self.assertLess(prob, 0.5)
        self.assertGreaterEqual(prob, 0.0)
    
    def test_win_probability_at_target(self):
        """测试价格等于目标时的胜率"""
        # 价格相等时，胜率应该接近0.5
        prob = self.gbm.calculate_win_probability(
            current_price=65000,
            target_price=65000,
            time_to_expiry=120
        )
        self.assertAlmostEqual(prob, 0.5, delta=0.1)
    
    def test_win_probability_zero_time(self):
        """测试时间为0时的胜率"""
        # 时间为0时，如果当前价格高于目标，胜率应为1
        prob = self.gbm.calculate_win_probability(
            current_price=65000,
            target_price=64900,
            time_to_expiry=0
        )
        self.assertEqual(prob, 1.0)
    
    def test_win_probability_negative_time(self):
        """测试负时间"""
        # 负时间应该当作0处理
        prob = self.gbm.calculate_win_probability(
            current_price=65000,
            target_price=64900,
            time_to_expiry=-10
        )
        self.assertEqual(prob, 1.0)
    
    def test_higher_volatility_reduces_certainty(self):
        """测试高波动率降低确定性"""
        gbm_low_vol = GeometricBrownianMotion(mu=0.001, sigma=0.01)
        gbm_high_vol = GeometricBrownianMotion(mu=0.001, sigma=0.05)
        
        # 使用较小的价格差，避免概率饱和
        prob_low = gbm_low_vol.calculate_win_probability(65000, 64990, 120)
        prob_high = gbm_high_vol.calculate_win_probability(65000, 64990, 120)
        
        # 低波动率应该有更高的确定性
        self.assertGreater(prob_low, prob_high)
    
    def test_longer_time_reduces_certainty(self):
        """测试更长时间降低确定性"""
        # 使用较小的价格差，避免概率饱和
        prob_short = self.gbm.calculate_win_probability(65000, 64990, 60)
        prob_long = self.gbm.calculate_win_probability(65000, 64990, 300)
        
        # 短时间应该有更高的确定性
        self.assertGreater(prob_short, prob_long)
    
    def test_monte_carlo_simulation(self):
        """测试蒙特卡洛模拟"""
        prob = self.gbm.monte_carlo_simulation(
            current_price=65000,
            target_price=64900,
            time_to_expiry=120,
            n_paths=1000
        )
        
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)
    
    def test_estimate_sigma(self):
        """测试波动率估计"""
        # 模拟价格序列
        prices = [65000, 65100, 65050, 65200, 65150, 65300, 65250, 65400]
        sigma = GeometricBrownianMotion.estimate_sigma_from_prices(prices, 300)
        
        self.assertGreater(sigma, 0)
        self.assertLess(sigma, 10)  # 年化波动率应该合理
    
    def test_update_parameters(self):
        """测试参数更新"""
        self.gbm.update_parameters(mu=0.002, sigma=0.03)
        
        self.assertEqual(self.gbm.mu, 0.002)
        self.assertEqual(self.gbm.sigma, 0.03)


if __name__ == '__main__':
    unittest.main()