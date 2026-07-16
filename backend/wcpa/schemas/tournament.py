"""核心赛事 schema — 小组积分、淘汰赛对阵表、冠军。"""

from typing import Optional

from wcpa.schemas import WCPABaseModel


class GroupStandingRow(WCPABaseModel):
    """小组积分榜单行。"""

    team_id: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0
    rank: int = 0
    qualification_status: str = "unknown"
    advancement_probability: float = 0.0


class GroupStanding(WCPABaseModel):
    """小组积分榜（已排序）。"""

    group: str
    rows: list[GroupStandingRow]


class KnockoutSlot(WCPABaseModel):
    """淘汰赛对阵槽位。

    ``home_source`` / ``away_source`` 描述球队来源，
    如 ``"GroupA_1"`` 或 ``"QF_W1"``。
    待决出时 ``home_team_id`` / ``away_team_id`` 为 None。
    """

    round: str  # QF/SF/Final
    match_id: str
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    home_source: str = ""
    away_source: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    winner_team_id: Optional[str] = None
    went_to_penalties: bool = False
    went_to_extra_time: bool = False
    status: str = "predicted"  # scheduled/final/predicted/reconstructed
    upset_index: float = 0.0


class Bracket(WCPABaseModel):
    """淘汰赛对阵表（含冠军）。"""

    slots: list[KnockoutSlot] = []
    champion_team_id: Optional[str] = None
    runner_up_team_id: Optional[str] = None
