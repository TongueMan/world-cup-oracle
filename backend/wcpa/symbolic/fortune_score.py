"""气运值计算 — MVP 桩。"""
# TODO: 实现冠军气运值、逆风翻盘值、点球命硬值
def compute_fortune_score(historical_honor: float, winning_streak: float,
                          leader_factor: float, schedule_difficulty: float,
                          fan_momentum: float, weights: dict | None = None) -> float:
    """计算气运值 — MVP 简化版。"""
    if weights is None:
        weights = {"historical_honor": 0.30, "winning_streak": 0.25,
                   "leader_factor": 0.20, "schedule_difficulty": 0.15, "fan_momentum": 0.10}
    score = (weights["historical_honor"] * historical_honor +
             weights["winning_streak"] * winning_streak +
             weights["leader_factor"] * leader_factor +
             weights["schedule_difficulty"] * schedule_difficulty +
             weights["fan_momentum"] * fan_momentum)
    return max(0.0, min(1.0, score))
