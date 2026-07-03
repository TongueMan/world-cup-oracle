"""Match 和 MatchResult 模型 — 比赛与比赛结果。"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class Match(WCPABaseModel):
    """比赛模型。

    一场世界杯比赛的基本信息。
    ``stage`` 对应 Stage 枚举值 (group/R32/R16/QF/SF/Final)。
    """

    match_id: str
    stage: str  # group/R32/R16/QF/SF/Final
    group: Optional[str] = None
    home_team_id: str
    away_team_id: str
    kickoff_time: Optional[datetime] = None
    venue: Optional[str] = None
    source: str = "fixture"
    status: str = "scheduled"  # scheduled/live/final/predicted


class MatchResult(WCPABaseModel):
    """比赛结果。

    小组赛平局时 ``winner_team_id`` 为 None；
    淘汰赛必有值（含点球大战胜者）。
    """

    match_id: str
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    winner_team_id: Optional[str] = None
    went_to_penalties: bool = False
    went_to_extra_time: bool = False
    is_actual: bool = False
    source: str = "prediction"
