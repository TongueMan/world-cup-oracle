"""DebateTranscript 模型 — Agent 辩论记录与裁决。"""

from typing import Optional

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class AgentOpinion(WCPABaseModel):
    """单个 Agent 的辩论意见。"""

    agent: str  # Agent 名称
    support_team_id: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    summary: str = ""
    detail: str = ""
    reason_codes: list[str] = []
    cited_signals: list[str] = []
    risk_flags: list[str] = []


class JudgeDecision(WCPABaseModel):
    """裁判决策。

    ``decision_type`` 对应 ConsensusType 枚举值。
    """

    winner_team_id: Optional[str] = None
    decision_type: str = "rational_lead"
    final_confidence: float = Field(ge=0, le=1)
    upset_index: float = Field(default=0.0, ge=0, le=1)
    summary: str = ""
    final_score: str = ""
    disagreement_sources: list[str] = []


class DebateTranscript(WCPABaseModel):
    """单场比赛的 Agent 辩论完整记录。"""

    match_id: str
    opinions: list[AgentOpinion] = []
    judge_decision: Optional[JudgeDecision] = None
