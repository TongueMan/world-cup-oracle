"""Poisson 进球模型。"""

import numpy as np


def estimate_lambda(
    home_attack: float,
    away_defense: float,
    away_attack: float,
    home_defense: float,
    base_goals: float = 1.35,
    home_advantage: float = 0.15,
    clamp_min: float = 0.1,
    clamp_max: float = 5.0,
) -> tuple[float, float]:
    """估算双方期望进球数 lambda。

    lambda_home = base_goals * (home_attack / away_defense) * (1 + home_advantage)
    lambda_away = base_goals * (away_attack / home_defense) * (1 - home_advantage)
    """
    lambda_home = (
        base_goals * (home_attack / max(away_defense, 0.1)) * (1 + home_advantage)
    )
    lambda_away = (
        base_goals * (away_attack / max(home_defense, 0.1)) * (1 - home_advantage)
    )

    lambda_home = max(clamp_min, min(clamp_max, lambda_home))
    lambda_away = max(clamp_min, min(clamp_max, lambda_away))

    return lambda_home, lambda_away


def sample_score(
    lambda_home: float,
    lambda_away: float,
    rng: np.random.Generator,
    max_goals: int = 10,
) -> tuple[int, int]:
    """用 Poisson 分布采样比分。"""
    home_score = int(rng.poisson(lambda_home))
    away_score = int(rng.poisson(lambda_away))
    home_score = min(home_score, max_goals)
    away_score = min(away_score, max_goals)
    return home_score, away_score
