"""Poisson 与 Dixon-Coles 比分分布工具。"""

from __future__ import annotations

import math

import numpy as np


def estimate_lambda(
    home_attack: float,
    away_defense: float,
    away_attack: float,
    home_defense: float,
    base_goals: float = 1.35,
    home_advantage: float = 0.0,
    clamp_min: float = 0.1,
    clamp_max: float = 5.0,
) -> tuple[float, float]:
    """根据归一化攻防强度估算双方 90 分钟期望进球。"""

    lambda_home = (
        base_goals * (home_attack / max(away_defense, 0.1)) * (1 + home_advantage)
    )
    lambda_away = (
        base_goals * (away_attack / max(home_defense, 0.1)) * (1 - home_advantage)
    )
    return (
        max(clamp_min, min(clamp_max, lambda_home)),
        max(clamp_min, min(clamp_max, lambda_away)),
    )


def poisson_pmf(goals: int, expected_goals: float) -> float:
    """返回 Poisson 质量函数值。"""

    if goals < 0 or expected_goals < 0:
        return 0.0
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


def score_probability_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 10,
    dixon_coles_rho: float = 0.0,
) -> np.ndarray:
    """生成截断后重新归一化的比分概率矩阵。

    ``matrix[h, a]`` 表示常规时间主队进 ``h`` 球、客队进 ``a`` 球的概率。
    ``dixon_coles_rho`` 为 0 时就是独立 Poisson；非 0 时修正四个低比分格子。
    """

    if max_goals < 1:
        raise ValueError("max_goals must be at least 1")
    home = np.array([poisson_pmf(i, lambda_home) for i in range(max_goals + 1)])
    away = np.array([poisson_pmf(i, lambda_away) for i in range(max_goals + 1)])
    matrix = np.outer(home, away)

    if dixon_coles_rho:
        corrections = {
            (0, 0): 1 - lambda_home * lambda_away * dixon_coles_rho,
            (0, 1): 1 + lambda_home * dixon_coles_rho,
            (1, 0): 1 + lambda_away * dixon_coles_rho,
            (1, 1): 1 - dixon_coles_rho,
        }
        for (home_goals, away_goals), factor in corrections.items():
            matrix[home_goals, away_goals] *= max(0.0, factor)

    total = float(matrix.sum())
    if total <= 0:
        raise ValueError("score probability matrix has no probability mass")
    return matrix / total


def outcome_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    """从比分矩阵汇总主胜、平局、客胜概率。"""

    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    total = home_win + draw + away_win
    return home_win / total, draw / total, away_win / total


def most_likely_score(matrix: np.ndarray) -> tuple[int, int]:
    """返回比分矩阵众数。"""

    flat_index = int(np.argmax(matrix))
    return tuple(int(value) for value in np.unravel_index(flat_index, matrix.shape))


def top_scorelines(matrix: np.ndarray, limit: int = 8) -> list[tuple[int, int, float]]:
    """返回概率最高的比分及其概率。"""

    limit = max(1, min(limit, matrix.size))
    flat_indexes = np.argsort(matrix, axis=None)[::-1][:limit]
    rows: list[tuple[int, int, float]] = []
    for flat_index in flat_indexes:
        home_goals, away_goals = np.unravel_index(int(flat_index), matrix.shape)
        rows.append((int(home_goals), int(away_goals), float(matrix[home_goals, away_goals])))
    return rows


def sample_score_from_matrix(
    matrix: np.ndarray,
    rng: np.random.Generator,
) -> tuple[int, int]:
    """仅供模拟使用：按比分矩阵抽取一次比分。"""

    flat_index = int(rng.choice(matrix.size, p=matrix.ravel()))
    return tuple(int(value) for value in np.unravel_index(flat_index, matrix.shape))


def sample_score(
    lambda_home: float,
    lambda_away: float,
    rng: np.random.Generator,
    max_goals: int = 10,
) -> tuple[int, int]:
    """兼容旧调用的 Poisson 比分采样。"""

    matrix = score_probability_matrix(lambda_home, lambda_away, max_goals=max_goals)
    return sample_score_from_matrix(matrix, rng)
