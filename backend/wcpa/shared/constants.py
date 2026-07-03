"""项目级枚举常量定义。"""

from enum import Enum


class DataQuality(str, Enum):
    """数据质量等级。"""

    A = "A"  # 官方权威
    B = "B"  # 可信媒体
    C = "C"  # 手工整理
    D = "D"  # 模型兜底


class Stage(str, Enum):
    """比赛阶段。"""

    GROUP = "group"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    FINAL = "Final"


class ConsensusType(str, Enum):
    """共识类型 — Agent 辩论裁决结果分类。"""

    STRONG_CONSENSUS = "strong_consensus"
    RATIONAL_LEAD = "rational_lead"
    RATIONAL_LEAD_WITH_SYMBOLIC_WARNING = "rational_lead_with_symbolic_warning"
    NARRATIVE_DARK_HORSE_WARNING = "narrative_dark_horse_warning"
    MULTI_TRACK_SPLIT = "multi_track_split"


class PredictionMode(str, Enum):
    """预测模式。"""

    PROFESSIONAL = "professional"
    BALANCED = "balanced"
    UPSET = "upset"
    ENTERTAINMENT = "entertainment"


class Confederation(str, Enum):
    """洲际足联。"""

    UEFA = "UEFA"
    CONMEBOL = "CONMEBOL"
    CONCACAF = "CONCACAF"
    AFC = "AFC"
    CAF = "CAF"
    OFC = "OFC"
