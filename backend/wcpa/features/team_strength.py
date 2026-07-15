"""球队综合评分计算。权重从 model-weights.yml 读取。"""

from wcpa.schemas.team import Team
from wcpa.schemas.artifact import TeamFeatures
from wcpa.shared.config_loader import load_config


def compute_team_strength(team: Team, weights: dict | None = None) -> TeamFeatures:
    """计算球队综合评分。

    公式:
      team_strength = w1*fifa_rank_norm + w2*elo_norm + w3*form
                    + w4*attack + w5*defense + w6*wc_exp + w7*health
    """
    if weights is None:
        cfg = load_config("model-weights")
        weights = cfg["team_strength"]

    # 归一化参数 (MVP 固定值)
    max_fifa_rank = 50
    max_elo = 2200

    norm_fifa = max(0.0, min(1.0, 1 - (team.fifa_rank - 1) / max_fifa_rank))
    norm_elo = max(0.0, min(1.0, team.elo_rating / max_elo))

    strength = (
        weights["fifa_rank_score"] * norm_fifa
        + weights["elo_score"] * norm_elo
        + weights["recent_form_score"] * team.recent_form_score
        + weights["attack_score"] * team.attack_score
        + weights["defense_score"] * team.defense_score
        + weights["world_cup_experience_score"] * team.world_cup_experience_score
        + weights["squad_health_score"] * team.squad_health_score
    )

    return TeamFeatures(
        team_id=team.team_id,
        team_strength=strength,
        normalized_fifa_rank=norm_fifa,
        normalized_elo=norm_elo,
        recent_form=team.recent_form_score,
        attack=team.attack_score,
        defense=team.defense_score,
        world_cup_experience=team.world_cup_experience_score,
        squad_health=team.squad_health_score,
        fifa_rank=team.fifa_rank,
        elo_rating=team.elo_rating,
        source_key=team.source_key,
        source_url=team.source_url,
    )
