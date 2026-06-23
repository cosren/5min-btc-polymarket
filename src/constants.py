"""
全局常量配置（单一数据源）

修改规则：所有阈值、分档、参数都在这里定义，一处修改处处生效。
其他模块通过 `from src import constants` 导入，不要在各个文件中硬编码。
"""

# ====== OBI (Order Book Imbalance) 主阈值 ======
OBI_THRESHOLD = 0.35

# ====== 默认值回退 ======
DEFAULT_FILTER_OBI_THRESHOLD = OBI_THRESHOLD
DEFAULT_DIRECTION_OBI_THRESHOLD = OBI_THRESHOLD
DEFAULT_BACKTEST_OBI_THRESHOLD = OBI_THRESHOLD

# ====== OBI 策略分档（仪表盘统计面板） ======
OBI_BUCKETS = [
    (0.00, 0.40, "0.00-0.40"),
    (0.40, 0.60, "0.40-0.60"),
    (0.60, 0.80, "0.60-0.80"),
    (0.80, float("inf"), ">0.80"),
]

# ====== 仪表盘 OBI 颜色阈值 ======
OBI_COLOR_POSITIVE = 0.15
OBI_COLOR_NEGATIVE = -0.15

# ====== Web 仪表盘 OBI 参考线 ======
OBI_CHART_HLINE = 0.85


def get_obi_threshold() -> float:
    """获取 OBI 主阈值（对外统一接口）"""
    return OBI_THRESHOLD


def get_obi_bucket(abs_obi: float) -> str:
    """根据 OBI 绝对值返回分档标签"""
    for lo, hi, label in OBI_BUCKETS:
        if lo <= abs_obi < hi:
            return label
    return "unknown"