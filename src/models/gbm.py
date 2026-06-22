import math
import random
import statistics
from typing import List


class GeometricBrownianMotion:
    """几何布朗运动模型

    基于 GBM 假设计算价格达到目标方向的概率:
    - 解析解: 使用对数正态分布公式
    - 蒙特卡洛: 模拟多条价格路径

    GBM 公式:
        dS = μ*S*dt + σ*S*dW
        log(S_T/S_0) ~ N((μ - σ²/2)*T, σ²*T)

    BTC 典型年化波动率: 50%-80%，默认值 50%

    Usage:
        gbm = GeometricBrownianMotion(mu=0.001, sigma=0.50)
        prob = gbm.calculate_win_probability(65000, 64900, 120)
    """

    MIN_SIGMA = 0.05
    FALLBACK_SIGMA = 0.50

    def __init__(self, mu: float = 0.001, sigma: float = 0.50):
        self.mu = mu
        self.sigma = max(sigma, self.MIN_SIGMA)

    def update_parameters(self, mu: float, sigma: float):
        self.mu = mu
        self.sigma = max(sigma, self.MIN_SIGMA)

    def calculate_win_probability(
        self,
        current_price: float,
        target_price: float,
        time_to_expiry: float
    ) -> float:
        """使用解析公式计算 GBM 胜率

        P(S_T > target) = Φ(d2)
        其中 d2 = (log(S/K) + (μ - σ²/2)*T) / (σ*√T)

        内置保底机制：当波动率过低或时间过短时，回退到基于价格比率的启发式估算
        """
        if current_price <= 0 or target_price <= 0:
            return 0.5

        if time_to_expiry <= 0:
            return 1.0 if current_price > target_price else 0.0

        T = time_to_expiry / (365 * 24 * 3600)

        effective_sigma = self.sigma
        if effective_sigma < self.MIN_SIGMA:
            effective_sigma = self.FALLBACK_SIGMA

        sigma_T = effective_sigma * math.sqrt(T)

        if sigma_T < 1e-8:
            return self._heuristic_probability(current_price, target_price, time_to_expiry)

        d2 = (math.log(current_price / target_price) + (self.mu - 0.5 * effective_sigma ** 2) * T) / sigma_T
        prob = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))

        if prob < 0.30 or prob > 0.70:
            heuristic = self._heuristic_probability(current_price, target_price, time_to_expiry)
            prob = 0.3 * prob + 0.7 * heuristic

        return max(0.0, min(1.0, prob))

    @staticmethod
    def _heuristic_probability(
        current_price: float,
        target_price: float,
        time_to_expiry: float
    ) -> float:
        """保底启发式胜率估算

        当 GBM 解析解因极端参数失效时，基于价格比率和时间衰减估算胜率。
        核心思路：价格距目标越近、时间越充裕，胜率越高
        """
        price_ratio = target_price / current_price
        if price_ratio > 1:
            distance = price_ratio - 1.0
            base = 0.50 * math.exp(-distance * 100)
        else:
            distance = 1.0 - price_ratio
            base = 1.0 - 0.50 * math.exp(-distance * 100)

        time_factor = min(1.0, time_to_expiry / 300.0)
        return base * time_factor + 0.50 * (1.0 - time_factor)

    def monte_carlo_simulation(
        self,
        current_price: float,
        target_price: float,
        time_to_expiry: float,
        n_paths: int = 10000
    ) -> float:
        """蒙特卡洛模拟计算胜率

        Args:
            current_price: 当前价格
            target_price: 目标价格
            time_to_expiry: 距离到期时间（秒）
            n_paths: 模拟路径数

        Returns:
            胜率 [0, 1]
        """
        if time_to_expiry <= 0:
            return 1.0 if current_price > target_price else 0.0

        T = time_to_expiry / (365 * 24 * 3600)
        drift = (self.mu - 0.5 * self.sigma ** 2) * T
        diffusion = self.sigma * math.sqrt(T)

        wins = 0
        for _ in range(n_paths):
            z = random.gauss(0, 1)
            S_T = current_price * math.exp(drift + diffusion * z)
            if S_T > target_price:
                wins += 1

        return wins / n_paths

    @staticmethod
    def estimate_sigma_from_prices(
        prices: List[float],
        time_interval_sec: float = 300
    ) -> float:
        """从价格序列估计年化波动率

        Args:
            prices: 价格序列
            time_interval_sec: 采样间隔（秒）

        Returns:
            年化波动率
        """
        if len(prices) < 2:
            return 0.02

        log_returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                log_returns.append(math.log(prices[i] / prices[i - 1]))

        if not log_returns:
            return 0.02

        period_sigma = statistics.stdev(log_returns) if len(log_returns) >= 2 else 0.0
        periods_per_year = (365 * 24 * 3600) / time_interval_sec
        annual_sigma = period_sigma * math.sqrt(periods_per_year)

        return annual_sigma