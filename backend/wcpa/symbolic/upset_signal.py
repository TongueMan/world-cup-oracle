"""爆冷信号生成 — MVP 桩。"""
# TODO: 实现爆冷信号综合判断
def compute_upset_signal(iching_upset_risk: float, tarot_volatility: float,
                         fortune_diff: float) -> float:
    """计算爆冷信号 — MVP 简化版。"""
    return max(0.0, min(1.0, (iching_upset_risk + tarot_volatility + fortune_diff) / 3))
