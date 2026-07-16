"""artifact 契约 schema — 最终预测产物。

TournamentPrediction 是 API 和报告的唯一数据源。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from wcpa.schemas import WCPABaseModel
from wcpa.schemas.tournament import GroupStanding, Bracket
from wcpa.schemas.prediction import MatchPrediction


class ReasoningTrace(WCPABaseModel):
    """推理链路记录。

    ``target_id`` 可以是 match_id 或 team_id。
    ``top_factors`` 形如 ``[{"name": "...", "impact": 0.24}]``。
    """

    target_id: str
    summary: str = ""
    top_factors: list[dict] = []
    assumptions: list[str] = []


class TeamFeatures(WCPABaseModel):
    """球队特征向量 — 归一化后用于模型输入。"""

    team_id: str
    team_strength: float = 0.0
    normalized_fifa_rank: float = 0.0
    normalized_elo: float = 0.0
    recent_form: float = 0.0
    attack: float = 0.0
    defense: float = 0.0
    world_cup_experience: float = 0.0
    squad_health: float = 0.0
    fifa_rank: Optional[int] = None
    elo_rating: Optional[int] = None
    source_key: str = ""
    source_url: str = ""


class ChampionProbability(WCPABaseModel):
    """由锦标赛 Monte Carlo 统计得到的球队夺冠概率。"""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    probability: float = Field(default=0.0, ge=0, le=1)
    most_common_eliminator: str = ""
    potential_key_match: str = ""
    simulation_count: int = Field(default=0, ge=0)
    probability_source: str = "monte_carlo"
    is_alive: bool = True
    eliminator_stats: list[dict] = Field(default_factory=list)
    key_matchups: list[dict] = Field(default_factory=list)


class TournamentStateMatch(WCPABaseModel):
    """赛事状态中的官方比赛快照。"""

    match_id: str
    stage: str
    status: str
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    winner_team_id: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_penalty: Optional[int] = None
    away_penalty: Optional[int] = None
    kickoff_time: Optional[datetime] = None
    next_match_id: Optional[str] = None
    home_source_match_id: Optional[str] = None
    away_source_match_id: Optional[str] = None


class TournamentState(WCPABaseModel):
    """一份可供条件模拟消费的、不可歧义的赛事状态。"""

    requested_anchor: str = "current"
    anchor_label: str = "当前赛况"
    as_of_time: Optional[datetime] = None
    active_round: str = "unknown"
    round_completed: int = 0
    round_total: int = 0
    completed_match_ids: list[str] = Field(default_factory=list)
    remaining_match_ids: list[str] = Field(default_factory=list)
    predictable_match_ids: list[str] = Field(default_factory=list)
    alive_teams: list[str] = Field(default_factory=list)
    eliminated_teams: list[str] = Field(default_factory=list)
    locked_results: list[TournamentStateMatch] = Field(default_factory=list)
    remaining_matches: list[TournamentStateMatch] = Field(default_factory=list)
    schedule_snapshot_id: str = ""
    schedule_hash: str = ""
    validation_status: Literal["ready", "invalid"] = "invalid"
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class FeatureModuleStatus(WCPABaseModel):
    """一个特征模块在本次预测中的真实接入状态。"""

    enabled: bool = False
    status: Literal["available", "partial", "not_connected"] = "not_connected"
    message: str = ""
    coverage: float = Field(default=0.0, ge=0, le=1)


class DataSourceStatus(WCPABaseModel):
    """数据源采集状态。"""

    source_key: str
    status: str = "unknown"
    credibility: str = "D"
    fetched_at: Optional[datetime] = None
    records: int = 0
    message: str = ""


class DataQualityReport(WCPABaseModel):
    """Strict data readiness report for production predictions."""

    status: str = "unknown"  # ready/degraded_prediction/data_unavailable/invalid
    strict: bool = True
    missing: list[str] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    invalid_records: list[dict] = Field(default_factory=list)
    source_statuses: list[DataSourceStatus] = Field(default_factory=list)
    message: str = ""


class PredictionReportSection(WCPABaseModel):
    """A user-facing prediction report section generated from one artifact."""

    title: str
    body: str
    bullets: list[str] = Field(default_factory=list)
    kind: str = "analysis"
    citations: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)


class PredictionReportReference(WCPABaseModel):
    """A report citation or model/data source reference."""

    reference_id: str
    label: str
    source_name: str = ""
    url: str = ""
    kind: str = "source"
    note: str = ""


class PredictionReportFigure(WCPABaseModel):
    """A real report figure with the exact client-renderable data payload."""

    figure_id: str
    title: str
    kind: str
    description: str = ""
    data: dict = Field(default_factory=dict)


class PredictionAgentReport(WCPABaseModel):
    """Structured Agent report bound to an artifact and prediction anchor."""

    report_id: str = ""
    artifact_id: str = ""
    anchor: str = "current"
    generated_at: Optional[datetime] = None
    status: str = "generated"
    headline: str = ""
    summary: str = ""
    title: str = ""
    abstract: str = ""
    methodology_note: str = ""
    references: list[PredictionReportReference] = Field(default_factory=list)
    figures: list[PredictionReportFigure] = Field(default_factory=list)
    data_disclosure: str = ""
    sections: list[PredictionReportSection] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_artifact_version: str = ""


class TournamentPrediction(WCPABaseModel):
    """最终预测 artifact — API 和报告的唯一数据源。

    包含完整赛事预测结果：小组积分、淘汰赛对阵、单场预测、
    冠军概率、数据来源、质量状态和推理链路。
    """

    edition: str = "2026"
    seed: int = 42
    mode: str = "balanced"
    artifact_version: str = "6.0.0"
    config_hash: str = ""  # 用于可复现性校验
    generated_at: Optional[datetime] = None
    artifact_id: str = ""
    run_id: str = ""
    publication_status: Literal["legacy", "candidate", "published"] = "legacy"
    probability_profile: str = "professional"
    simulation_count: int = Field(default=0, ge=0)
    input_data_as_of: Optional[datetime] = None
    schedule_snapshot_id: str = ""
    schedule_hash: str = ""
    model_config_hash: str = ""
    current_tournament_state: Optional[TournamentState] = None
    feature_modules: dict[str, FeatureModuleStatus] = Field(default_factory=dict)
    team_features: list[TeamFeatures] = Field(default_factory=list)

    group_standings: list[GroupStanding] = []
    bracket: Optional[Bracket] = None
    match_predictions: list[MatchPrediction] = []
    scenario_match_predictions: list[MatchPrediction] = Field(default_factory=list)
    match_results: list[dict] = []  # list[MatchResult] 序列化

    champion_team_id: Optional[str] = None
    runner_up_team_id: Optional[str] = None
    semifinalists: list[str] = []

    # 数据与概率模型给出的冠军预测
    rational_champion: Optional[str] = None

    # 附加数据
    reasoning_traces: list[ReasoningTrace] = []
    champion_probabilities: list[ChampionProbability] = []
    data_sources: list[DataSourceStatus] = []
    champion_path: list[dict] = []
    path_reconstruction_notes: list[str] = []
    prediction_report: Optional[PredictionAgentReport] = None
    data_verified: bool = False
    data_quality_report: Optional[DataQualityReport] = None
