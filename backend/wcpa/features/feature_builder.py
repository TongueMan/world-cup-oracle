"""特征构造入口。"""

from wcpa.schemas.team import Team
from wcpa.schemas.artifact import TeamFeatures
from wcpa.features.team_strength import compute_team_strength


def build_features(
    teams: list[Team], weights: dict | None = None
) -> dict[str, TeamFeatures]:
    """从球队数据构建特征字典。

    Args:
        teams: 球队列表。
        weights: 可选的权重字典，为 None 时从 model-weights.yml 加载。

    Returns:
        ``{team_id: TeamFeatures}`` 映射。
    """
    return {t.team_id: compute_team_strength(t, weights) for t in teams}
