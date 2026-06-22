#!/usr/bin/env python3
"""凯利公式(Kelly Criterion)仓位管理模块

根据真实胜率和赔率计算最优下注比例
f* = [p × (b + 1) - 1] / b
实际使用建议采用四分之一凯利(1/4 f*)进行保守下注
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class KellyCriterion:
    """凯利公式仓位计算器
    
    核心公式:
    f* = [p × (b + 1) - 1] / b
    其中:
    - p = 真实胜率
    - b = 净赔率
    - f* = 最优下注比例
    
    为防范黑天鹅，建议使用:
    - 四分之一凯利: f_actual = f* / 4
    - 半凯利: f_actual = f* / 2
    
    使用示例:
        kelly = KellyCriterion(max_position_pct=5.0)
        fraction = kelly.calculate_kelly_fraction(
            p_win=0.75,      # 75%胜率
            payout_ratio=0.5  # 50%赔率
        )
        conservative = kelly.get_conservative_fraction(fraction, 'quarter')
    """
    
    def __init__(
        self,
        max_position_pct: float = 5.0,
        kelly_fraction_type: str = 'quarter'
    ):
        """初始化
        
        Args:
            max_position_pct: 单笔最大仓位比例(%)
            kelly_fraction_type: 凯利分数类型 ('quarter', 'half', 'full')
        """
        self.max_position_pct = max_position_pct
        self.kelly_fraction_type = kelly_fraction_type
        self._history: list = []
    
    def calculate_kelly_fraction(
        self,
        p_win: float,
        payout_ratio: float
    ) -> float:
        """计算凯利公式最优下注比例
        
        f* = [p × (b + 1) - 1] / b
        
        Args:
            p_win: 真实胜率 [0, 1]
            payout_ratio: 净赔率
        
        Returns:
            凯利最优下注比例 [0, 1]，负值表示不应下注
        """
        # 参数校验
        p_win = max(0.0, min(1.0, p_win))
        payout_ratio = max(0.01, payout_ratio)
        
        b = payout_ratio
        f_star = (p_win * (b + 1) - 1) / b
        
        # 记录历史
        self._history.append({
            'p_win': p_win,
            'payout_ratio': payout_ratio,
            'f_star': f_star
        })
        if len(self._history) > 100:
            self._history = self._history[-100:]
        
        return f_star
    
    def get_conservative_fraction(
        self,
        kelly_fraction: float,
        fraction_type: Optional[str] = None
    ) -> float:
        """获取保守下注比例
        
        Args:
            kelly_fraction: 凯利公式计算的最优比例
            fraction_type: 分数类型 ('quarter', 'half', 'full')
        
        Returns:
            实际使用的下注比例
        """
        f_type = fraction_type or self.kelly_fraction_type
        
        fractions = {
            'quarter': 0.25,
            'half': 0.5,
            'full': 1.0
        }
        
        multiplier = fractions.get(f_type, 0.25)
        
        # 凯利值为负时不下注
        if kelly_fraction <= 0:
            return 0.0
        
        conservative = kelly_fraction * multiplier
        
        # 应用最大仓位限制
        max_pos = self.max_position_pct / 100.0
        return min(conservative, max_pos)
    
    def calculate_position_size(
        self,
        equity: float,
        p_win: float,
        payout_ratio: float,
        fraction_type: Optional[str] = None
    ) -> float:
        """计算实际下注金额
        
        Args:
            equity: 账户总资金
            p_win: 真实胜率
            payout_ratio: 净赔率
            fraction_type: 分数类型
        
        Returns:
            下注金额(美元)
        """
        kelly_fraction = self.calculate_kelly_fraction(p_win, payout_ratio)
        conservative = self.get_conservative_fraction(kelly_fraction, fraction_type)
        
        return equity * conservative
    
    def should_bet(self, p_win: float, payout_ratio: float) -> bool:
        """判断是否应该下注
        
        当凯利值为正时才下注
        
        Args:
            p_win: 真实胜率
            payout_ratio: 净赔率
        
        Returns:
            True表示可以下注
        """
        kelly_fraction = self.calculate_kelly_fraction(p_win, payout_ratio)
        return kelly_fraction > 0
    
    def get_position_recommendation(
        self,
        equity: float,
        p_win: float,
        payout_ratio: float
    ) -> dict:
        """获取仓位建议
        
        Args:
            equity: 账户总资金
            p_win: 真实胜率
            payout_ratio: 净赔率
        
        Returns:
            包含详细建议的字典
        """
        kelly_fraction = self.calculate_kelly_fraction(p_win, payout_ratio)
        quarter_kelly = self.get_conservative_fraction(kelly_fraction, 'quarter')
        half_kelly = self.get_conservative_fraction(kelly_fraction, 'half')
        full_kelly = self.get_conservative_fraction(kelly_fraction, 'full')
        
        return {
            'kelly_fraction': kelly_fraction,
            'quarter_kelly_pct': quarter_kelly * 100,
            'half_kelly_pct': half_kelly * 100,
            'full_kelly_pct': full_kelly * 100,
            'quarter_kelly_usd': equity * quarter_kelly,
            'half_kelly_usd': equity * half_kelly,
            'full_kelly_usd': equity * full_kelly,
            'max_position_usd': equity * (self.max_position_pct / 100.0),
            'should_bet': kelly_fraction > 0,
            'recommended_type': self.kelly_fraction_type
        }
    
    @property
    def average_kelly(self) -> float:
        """获取历史平均凯利值"""
        if not self._history:
            return 0.0
        return sum(h['f_star'] for h in self._history) / len(self._history)