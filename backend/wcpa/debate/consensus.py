"""共识类型判定 — MVP 桩实现。"""
from wcpa.shared.constants import ConsensusType
from wcpa.schemas.prediction import MatchPrediction

def determine_consensus(
    rational_winner: str | None,
    narrative_winner: str | None,
    symbolic_upset_risk: float,
    prediction: MatchPrediction,
) -> ConsensusType:
    """判定共识类型 — MVP 简化版。"""
    # MVP: 总是返回 rational_lead
    return ConsensusType.RATIONAL_LEAD
