"""artifact 契约 schema — 最终预测产物。

TournamentPrediction 是 API 和报告的唯一数据源。
"""

from datetime import datetime
from typing import Optional

from wcpa.schemas import WCPABaseModel
from wcpa.schemas.tournament import GroupStanding, Bracket
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.debate import DebateTranscript
from wcpa.schemas.symbolic import SymbolicSignal
from wcpa.schemas.narrative import NarrativeProfile


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


class ChampionProbability(WCPABaseModel):
    """冠军概率排行项。"""

    team_id: str
    probability: float = 0.0
    track: str = "overall"


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

    status: str = "unknown"  # ready/data_unavailable/invalid
    strict: bool = True
    missing: list[str] = []
    conflicts: list[dict] = []
    invalid_records: list[dict] = []
    source_statuses: list[DataSourceStatus] = []
    message: str = ""


class TournamentPrediction(WCPABaseModel):
    """最终预测 artifact — API 和报告的唯一数据源。

    包含完整赛事预测结果：小组积分、淘汰赛对阵、单场预测、
    三轨道冠军、叙事画像、象征信号、辩论记录和推理链路。
    """

    edition: str = "2026"
    seed: int = 42
    mode: str = "balanced"
    artifact_version: str = "1.0.0"
    config_hash: str = ""  # 用于可复现性校验
    generated_at: Optional[datetime] = None

    group_standings: list[GroupStanding] = []
    bracket: Optional[Bracket] = None
    match_predictions: list[MatchPrediction] = []
    match_results: list[dict] = []  # list[MatchResult] 序列化

    champion_team_id: Optional[str] = None
    runner_up_team_id: Optional[str] = None
    semifinalists: list[str] = []

    # 三轨道冠军（MVP 阶段只有理性冠军）
    rational_champion: Optional[str] = None
    narrative_champion: Optional[str] = None
    symbolic_champion: Optional[str] = None

    # 附加数据
    narratives: list[NarrativeProfile] = []
    symbolic_signals: list[SymbolicSignal] = []
    debate_transcripts: list[DebateTranscript] = []
    reasoning_traces: list[ReasoningTrace] = []
    champion_probabilities: list[ChampionProbability] = []
    upset_alerts: list[dict] = []
    dark_horses: list[dict] = []
    data_sources: list[DataSourceStatus] = []
    champion_path: list[dict] = []
    path_reconstruction_notes: list[str] = []
    data_verified: bool = False
    data_quality_report: Optional[DataQualityReport] = None
