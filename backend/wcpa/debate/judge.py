"""Judge Agent 裁决 — MVP 桩实现。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from wcpa.schemas.debate import JudgeDecision, AgentOpinion
from wcpa.schemas.prediction import MatchPrediction
from wcpa.shared.constants import ConsensusType

class JudgeAgent(ABC):
    """Judge Agent 接口。"""
    @abstractmethod
    def adjudicate(self, match_id: str, opinions: list[AgentOpinion],
                   prediction: MatchPrediction) -> JudgeDecision:
        ...

class BaselineJudgeAgent(JudgeAgent):
    """Weighted baseline judge with deterministic conflict handling."""
    
    def adjudicate(self, match_id: str, opinions: list[AgentOpinion],
                   prediction: MatchPrediction) -> JudgeDecision:
        support_counts: dict[str, int] = {}
        disagreement_sources: list[str] = []
        for opinion in opinions:
            if opinion.support_team_id:
                support_counts[opinion.support_team_id] = (
                    support_counts.get(opinion.support_team_id, 0) + 1
                )
            if opinion.risk_flags:
                disagreement_sources.extend(opinion.risk_flags)

        winner = prediction.winner_team_id
        if support_counts and prediction.confidence < 0.7:
            winner = max(support_counts.items(), key=lambda item: item[1])[0]

        symbolic_warning = any(
            op.agent in {"Tarot Agent", "I-Ching Agent", "Astrology Agent"}
            and op.risk_flags
            for op in opinions
        )
        split = len([team for team in support_counts if team]) > 1
        if split:
            decision_type = ConsensusType.MULTI_TRACK_SPLIT.value
            confidence = max(0.35, prediction.confidence - 0.1)
            upset_index = min(1.0, prediction.upset_index + 0.2)
            summary = "多轨道意见出现分裂，总控裁判降低置信度并提高爆冷警戒。"
        elif symbolic_warning:
            decision_type = ConsensusType.RATIONAL_LEAD_WITH_SYMBOLIC_WARNING.value
            confidence = max(0.35, prediction.confidence - 0.05)
            upset_index = min(1.0, prediction.upset_index + 0.15)
            summary = "理性轨仍领先，但象征轨提示比赛存在波动。"
        else:
            decision_type = ConsensusType.RATIONAL_LEAD.value
            confidence = prediction.confidence
            upset_index = prediction.upset_index
            summary = "理性轨主导预测结果，多数 Agent 未形成强反对。"

        return JudgeDecision(
            winner_team_id=winner,
            decision_type=decision_type,
            final_confidence=round(confidence, 4),
            upset_index=round(upset_index, 4),
            summary=summary,
            final_score=prediction.predicted_score,
            disagreement_sources=sorted(set(disagreement_sources)),
        )
