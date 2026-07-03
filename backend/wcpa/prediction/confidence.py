"""置信度计算。"""

import math


def compute_confidence(strength_diff: float, prob_max: float) -> float:
    """基于实力差和概率集中度计算置信度。

    strength_diff 越大，置信度越高。
    prob_max (胜/平/负中最大概率) 越高，置信度越高。

    Args:
        strength_diff: 双方实力差的绝对值。
        prob_max: 胜/平/负三概率中的最大值。

    Returns:
        置信度，范围 [0.1, 0.95]。
    """
    # sigmoid 映射 strength_diff 到 [0, 1]
    diff_factor = 1 / (1 + math.exp(-strength_diff * 5))
    # 概率集中度因子: 从 [1/3, 1] 映射到 [0, 1]
    concentration = (prob_max - 0.333) / 0.667
    concentration = max(0.0, min(1.0, concentration))
    # 综合置信度
    confidence = 0.5 * diff_factor + 0.5 * concentration
    return max(0.1, min(0.95, confidence))
