"""Team 模型 — 球队基础数据。"""

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class Team(WCPABaseModel):
    """球队模型。

    字段对应数据归一化后的标准化球队档案。
    所有 0-1 范围的分数经过归一化处理。
    """

    team_id: str
    name: str
    confederation: str
    fifa_rank: int = Field(ge=1)
    elo_rating: int = Field(ge=0)
    recent_form_score: float = Field(ge=0, le=1)
    attack_score: float = Field(ge=0, le=1)
    defense_score: float = Field(ge=0, le=1)
    squad_health_score: float = Field(ge=0, le=1)
    world_cup_experience_score: float = Field(default=0.5, ge=0, le=1)
    data_quality: str = "D"  # A/B/C/D
    source_key: str = ""
    source_url: str = ""
    verified: bool = False
