"""比赛预测输入、证据和输出契约。"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field, model_validator

from wcpa.schemas import WCPABaseModel


DataGrade = Literal["A", "B", "C", "D", "E"]
SourceType = Literal["local", "database", "api", "web", "agent", "model_prior"]


class PredictionEvidence(WCPABaseModel):
    """一条可追溯、可冲突的字段级证据。"""

    evidence_id: str
    claim: str
    source_type: SourceType
    source_name: str
    url: str = ""
    updated_at: Optional[datetime] = None
    freshness: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    supported_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    detail: str = ""
    affected_team_ids: list[str] = Field(default_factory=list)
    impact_summary: str = ""
    model_usage: Literal["applied", "model_input", "context_only"] = "context_only"


class BookmakerOdds(WCPABaseModel):
    """一家机构的十进制胜平负赔率快照。"""

    bookmaker: str
    source_type: Literal["local", "database", "api", "web"] = "api"
    home: float = Field(gt=1)
    draw: float = Field(gt=1)
    away: float = Field(gt=1)
    source_name: str = ""
    url: str = ""
    updated_at: Optional[datetime] = None
    freshness: float = Field(default=0.8, ge=0, le=1)
    confidence: float = Field(default=0.8, ge=0, le=1)


class SemanticProbabilitySignal(WCPABaseModel):
    """Agent 基于外部证据抽取的轻量概率信号。"""

    home_win_prob: float = Field(ge=0, le=1)
    draw_prob: float = Field(ge=0, le=1)
    away_win_prob: float = Field(ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_probability_sum(self) -> "SemanticProbabilitySignal":
        total = self.home_win_prob + self.draw_prob + self.away_win_prob
        if abs(total - 1.0) > 1e-6:
            raise ValueError("semantic probabilities must sum to 1")
        return self


class ProbabilityAdjustment(WCPABaseModel):
    """阵容、规则、体能、环境或战术产生的有界修正。"""

    factor: Literal["lineup", "suspension", "fatigue", "environment", "tactical", "other"]
    home_delta: float = Field(default=0.0, ge=-0.05, le=0.05)
    draw_delta: float = Field(default=0.0, ge=-0.05, le=0.05)
    away_delta: float = Field(default=0.0, ge=-0.05, le=0.05)
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class PredictionContext(WCPABaseModel):
    """可选的多源信息；任何字段缺失都不能阻止预测。"""

    odds: list[BookmakerOdds] = Field(default_factory=list)
    evidence: list[PredictionEvidence] = Field(default_factory=list)
    semantic_signal: Optional[SemanticProbabilitySignal] = None
    adjustments: list[ProbabilityAdjustment] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    structured_data_available: bool = True
    lineup_data_available: bool = False
    web_search_attempted: bool = False
    web_search_succeeded: bool = False
    neutral_venue: bool = True
    penalty_home_win_prob: Optional[float] = Field(default=None, ge=0, le=1)
    data_grade_override: Optional[DataGrade] = None


class ProbabilityComponent(WCPABaseModel):
    """一个子模型在最终融合中的概率与实际权重。"""

    name: Literal["market", "strength", "goals", "web_semantic", "neutral_prior"]
    home_win_prob: float = Field(ge=0, le=1)
    draw_prob: float = Field(ge=0, le=1)
    away_win_prob: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    base_weight: float = Field(ge=0, le=1)
    effective_weight: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ScorelineProbability(WCPABaseModel):
    """比分矩阵中用于解释的一个高概率比分。"""

    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class MatchPrediction(WCPABaseModel):
    """单场比赛的多源融合预测结果。"""

    match_id: str
    home_win_prob: float = Field(ge=0, le=1)
    draw_prob: float = Field(ge=0, le=1)
    away_win_prob: float = Field(ge=0, le=1)
    predicted_score: str = ""
    winner_team_id: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    upset_index: float = Field(default=0.0, ge=0, le=1)
    consensus_type: str = "rational_lead"
    reason_codes: list[str] = Field(default_factory=list)
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    is_locked_result: bool = False
    source: str = "prediction"

    data_grade: DataGrade = "E"
    confidence_cap: float = Field(default=0.35, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[PredictionEvidence] = Field(default_factory=list)
    probability_components: list[ProbabilityComponent] = Field(default_factory=list)
    applied_adjustments: list[ProbabilityAdjustment] = Field(default_factory=list)

    expected_home_goals: float = Field(default=0.0, ge=0)
    expected_away_goals: float = Field(default=0.0, ge=0)
    score_distribution: list[ScorelineProbability] = Field(default_factory=list)

    extra_time_prob: float = Field(default=0.0, ge=0, le=1)
    penalty_prob: float = Field(default=0.0, ge=0, le=1)
    extra_time_home_win_prob: float = Field(default=0.5, ge=0, le=1)
    extra_time_draw_prob: float = Field(default=0.0, ge=0, le=1)
    extra_time_away_win_prob: float = Field(default=0.5, ge=0, le=1)
    penalty_home_win_prob: float = Field(default=0.5, ge=0, le=1)
    penalty_away_win_prob: float = Field(default=0.5, ge=0, le=1)
    home_advancement_prob: float = Field(default=0.0, ge=0, le=1)
    away_advancement_prob: float = Field(default=0.0, ge=0, le=1)

    tactical_summary: str = ""

    @model_validator(mode="after")
    def validate_probability_sums(self) -> "MatchPrediction":
        outcome_total = self.home_win_prob + self.draw_prob + self.away_win_prob
        if abs(outcome_total - 1.0) > 0.0015:
            raise ValueError("match outcome probabilities must sum to 1")
        advancement_total = self.home_advancement_prob + self.away_advancement_prob
        if advancement_total and abs(advancement_total - 1.0) > 0.0015:
            raise ValueError("advancement probabilities must sum to 1")
        return self
