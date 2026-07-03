"""MatchPrediction 模型 — 单场比赛预测结果。"""

from typing import Optional

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class MatchPrediction(WCPABaseModel):
    """单场比赛预测。

    包含胜负概率、预测比分、信心度、爆冷指数和共识类型。
    ``consensus_type`` 对应 ConsensusType 枚举值。
    """

    match_id: str
    home_win_prob: float = Field(ge=0, le=1)
    draw_prob: float = Field(ge=0, le=1)
    away_win_prob: float = Field(ge=0, le=1)
    predicted_score: str = ""  # "1-2"
    winner_team_id: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    upset_index: float = Field(default=0.0, ge=0, le=1)
    consensus_type: str = "rational_lead"
    reason_codes: list[str] = []
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    is_locked_result: bool = False
    source: str = "prediction"
    extra_time_prob: float = 0.0
    penalty_prob: float = 0.0
    tactical_summary: str = ""
    narrative_summary: str = ""
    symbolic_summary: str = ""
