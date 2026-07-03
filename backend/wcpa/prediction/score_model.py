"""比分生成模型。"""

import numpy as np

from wcpa.prediction.poisson_model import estimate_lambda, sample_score
from wcpa.schemas.artifact import TeamFeatures


def generate_score(
    home: TeamFeatures,
    away: TeamFeatures,
    rng: np.random.Generator,
    config: dict | None = None,
) -> tuple[int, int]:
    """生成比分。"""
    if config is None:
        from wcpa.shared.config_loader import load_config

        config = load_config("model-weights")["score_model"]

    lambda_home, lambda_away = estimate_lambda(
        home.attack,
        away.defense,
        away.attack,
        home.defense,
        config.get("base_goals", 1.35),
        config.get("home_advantage", 0.15),
        config.get("lambda_clamp_min", 0.1),
        config.get("lambda_clamp_max", 5.0),
    )

    return sample_score(
        lambda_home, lambda_away, rng, config.get("max_goals", 10)
    )
