"""NarrativeProfile 模型 — 球队叙事画像。"""

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class NarrativeProfile(WCPABaseModel):
    """球队叙事画像。

    描述球队的媒体热度、士气、黑马属性、压力、宿命感和球迷势头。
    ``narrative_score`` 为计算后的综合叙事分。
    """

    team_id: str
    media_heat_score: float = Field(ge=0, le=1)
    morale_score: float = Field(ge=0, le=1)
    dark_horse_score: float = Field(ge=0, le=1)
    pressure_score: float = Field(ge=0, le=1)
    destiny_score: float = Field(ge=0, le=1)
    fan_momentum_score: float = Field(ge=0, le=1)
    narrative_score: float = Field(default=0.0, ge=0, le=1)
    tags: list[str] = []
