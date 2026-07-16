"""schemas 包 — Pydantic v2 数据模型层。

定义所有 WCPA 领域 schema，统一继承 :class:`WCPABaseModel`。
"""

from pydantic import BaseModel, ConfigDict


class WCPABaseModel(BaseModel):
    """所有 WCPA schema 的基类。

    - ``frozen=True``: 模型实例不可变，防止意外篡改。
    - ``populate_by_name=True``: 允许通过字段名（而非仅别名）填充。
    - ``str_strip_whitespace=True``: 自动去除字符串字段首尾空白。
    """

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


# ---- 以下导入必须在 WCPABaseModel 定义之后 ----
from wcpa.schemas.team import Team  # noqa: E402
from wcpa.schemas.player import Player  # noqa: E402
from wcpa.schemas.match import Match, MatchResult  # noqa: E402
from wcpa.schemas.tournament import (  # noqa: E402
    GroupStandingRow,
    GroupStanding,
    KnockoutSlot,
    Bracket,
)
from wcpa.schemas.prediction import (  # noqa: E402
    BookmakerOdds,
    MatchPrediction,
    PredictionContext,
    PredictionEvidence,
    ProbabilityAdjustment,
    ProbabilityComponent,
    ScorelineProbability,
    SemanticProbabilitySignal,
)
from wcpa.schemas.artifact import (  # noqa: E402
    TournamentPrediction,
    TeamFeatures,
    ReasoningTrace,
    ChampionProbability,
    DataSourceStatus,
    DataQualityReport,
    PredictionAgentReport,
    PredictionReportFigure,
    PredictionReportReference,
    PredictionReportSection,
)
from wcpa.schemas.worldcup import WorldCupMatch, WorldCupSyncStatus, WorldCupTeam  # noqa: E402
from wcpa.schemas.worldcup_environment import (  # noqa: E402
    WorldCupEnvironmentFeatures,
    WorldCupMatchEnvironment,
    WorldCupMatchVenue,
    WorldCupVenue,
    WorldCupVenueList,
    WorldCupWeatherSnapshot,
)

__all__ = [
    "WCPABaseModel",
    "Team",
    "Player",
    "Match",
    "MatchResult",
    "GroupStandingRow",
    "GroupStanding",
    "KnockoutSlot",
    "Bracket",
    "MatchPrediction",
    "BookmakerOdds",
    "PredictionContext",
    "PredictionEvidence",
    "ProbabilityAdjustment",
    "ProbabilityComponent",
    "ScorelineProbability",
    "SemanticProbabilitySignal",
    "TournamentPrediction",
    "TeamFeatures",
    "ReasoningTrace",
    "ChampionProbability",
    "DataSourceStatus",
    "DataQualityReport",
    "PredictionAgentReport",
    "PredictionReportFigure",
    "PredictionReportReference",
    "PredictionReportSection",
    "WorldCupMatch",
    "WorldCupSyncStatus",
    "WorldCupTeam",
    "WorldCupEnvironmentFeatures",
    "WorldCupMatchEnvironment",
    "WorldCupMatchVenue",
    "WorldCupVenue",
    "WorldCupVenueList",
    "WorldCupWeatherSnapshot",
]
