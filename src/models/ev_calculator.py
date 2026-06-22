#!/usr/bin/env python3
"""期望值(Expected Value)校验计算模块

只有当EV > 0.05(5%正期望值优势)时才允许下单
EV = (P_win × 净赔率) - (1 - P_win)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ExpectedValueCalculator:
    """期望值计算器
    
    核心逻辑:
    - 获取GBM模型计算的真实胜率 P_win
    - 获取Polymarket盘口暗示概率 P_poly
    - 计算净赔率 = (1 / P_poly) - 1
    - 计算 EV = (P_win × 净赔率) - (1 - P_win)
    - 只有 EV > min_ev_threshold 才允许下单
    
    使用示例:
        calc = ExpectedValueCalculator(min_ev=0.05)
        ev = calc.calculate_ev(
            p_win=0.75,      # GBM计算的真实胜率75%
            p_poly=0.65      # Polymarket暗示概率65%
        )
        if calc.should_trade(ev):
            print("正期望值，可以下单")
    """
    
    def __init__(self, min_ev: float = 0.05):
        """初始化
        
        Args:
            min_ev: 最小期望值阈值，默认0.05(5%)
        """
        self.min_ev = min_ev
        self._ev_history: list = []
    
    def calculate_net_odds(self, p_poly: float) -> float:
        """计算净赔率
        
        净赔率 = (1 / P_poly) - 1
        
        Args:
            p_poly: Polymarket暗示概率 [0, 1]
        
        Returns:
            净赔率
        """
        if p_poly <= 0 or p_poly >= 1:
            return 0.0
        
        return (1.0 / p_poly) - 1.0
    
    def calculate_ev(
        self,
        p_win: float,
        p_poly: float,
        payout_ratio: Optional[float] = None
    ) -> float:
        """计算期望值
        
        EV = (P_win × 净赔率) - (1 - P_win)
        
        Args:
            p_win: GBM计算的真实胜率 [0, 1]
            p_poly: Polymarket暗示概率 [0, 1]
            payout_ratio: 净赔率(可选，如不提供则从p_poly计算)
        
        Returns:
            期望值
        """
        # 参数校验
        p_win = max(0.0, min(1.0, p_win))
        p_poly = max(0.01, min(0.99, p_poly))
        
        # 计算净赔率
        if payout_ratio is not None:
            b = payout_ratio
        else:
            b = self.calculate_net_odds(p_poly)
        
        # 计算EV
        ev = (p_win * b) - (1 - p_win)
        
        # 记录历史
        self._ev_history.append(ev)
        if len(self._ev_history) > 100:
            self._ev_history = self._ev_history[-100:]
        
        return ev
    
    def should_trade(self, ev: float) -> bool:
        """判断是否应该交易
        
        Args:
            ev: 期望值
        
        Returns:
            True表示EV超过阈值，可以交易
        """
        return ev > self.min_ev
    
    def calculate_edge(
        self,
        p_win: float,
        p_poly: float
    ) -> float:
        """计算优势度(Edge)
        
        Edge = P_win - P_poly
        正值表示我们比市场更看好这个方向
        
        Args:
            p_win: 真实胜率
            p_poly: 市场暗示概率
        
        Returns:
            优势度
        """
        return p_win - p_poly
    
    def get_trade_recommendation(
        self,
        p_win: float,
        p_poly: float,
        payout_ratio: Optional[float] = None
    ) -> dict:
        """获取交易建议
        
        Args:
            p_win: 真实胜率
            p_poly: 市场暗示概率
            payout_ratio: 净赔率
        
        Returns:
            包含详细分析的建议字典
        """
        ev = self.calculate_ev(p_win, p_poly, payout_ratio)
        edge = self.calculate_edge(p_win, p_poly)
        net_odds = payout_ratio if payout_ratio is not None else self.calculate_net_odds(p_poly)
        
        # 判断建议
        if ev > self.min_ev and edge > 0.05:
            recommendation = 'strong_buy'
        elif ev > 0 and edge > 0:
            recommendation = 'weak_buy'
        elif ev > -0.02:
            recommendation = 'neutral'
        else:
            recommendation = 'avoid'
        
        return {
            'p_win': p_win,
            'p_poly': p_poly,
            'net_odds': net_odds,
            'ev': ev,
            'edge': edge,
            'min_ev_threshold': self.min_ev,
            'passes_ev_filter': ev > self.min_ev,
            'recommendation': recommendation
        }
    
    @property
    def average_ev(self) -> float:
        """获取平均EV"""
        if not self._ev_history:
            return 0.0
        return sum(self._ev_history) / len(self._ev_history)