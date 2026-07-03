"""辩论编排器 — MVP 桩实现。"""
from __future__ import annotations
from wcpa.schemas.debate import DebateTranscript, AgentOpinion, JudgeDecision
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.team import Team
from wcpa.schemas.symbolic import SymbolicSignal
from wcpa.debate.agent_opinion import DATA_ANALYST, TACTICAL_ANALYST, NARRATIVE_AGENT
from wcpa.debate.judge import BaselineJudgeAgent
from wcpa.agents.harness import AgentUnavailableError, MatchContext, build_agent_opinions

class DebateRunner:
    """辩论编排器 — LLM Harness with rule fallback."""
    
    def __init__(self):
        self.judge = BaselineJudgeAgent()
    
    def run_debate(
        self,
        match_id: str,
        prediction: MatchPrediction,
        match: Match | None = None,
        home: Team | None = None,
        away: Team | None = None,
        symbolic_signal: SymbolicSignal | None = None,
        narratives: list[dict] | None = None,
    ) -> DebateTranscript:
        """Run all analysis agents for one match."""
        if match and home and away:
            context = MatchContext(
                match=match,
                prediction=prediction,
                home_team=home.model_dump(mode="json"),
                away_team=away.model_dump(mode="json"),
                symbolic_signal=(
                    symbolic_signal.model_dump(mode="json") if symbolic_signal else None
                ),
                narrative_profiles=narratives or [],
            )
            try:
                opinions = build_agent_opinions(context)
            except AgentUnavailableError:
                return DebateTranscript(match_id=match_id, opinions=[], judge_decision=None)
        else:
            opinions = [
                AgentOpinion(
                    agent=DATA_ANALYST,
                    support_team_id=prediction.winner_team_id,
                    confidence=prediction.confidence,
                    summary=f"基于排名和近期状态，预测 {prediction.winner_team_id} 胜出。",
                    detail="兼容旧调用路径的规则观点。",
                    reason_codes=prediction.reason_codes,
                    cited_signals=["match_prediction"],
                ),
            ]
        
        decision = self.judge.adjudicate(match_id, opinions, prediction)
        
        return DebateTranscript(
            match_id=match_id,
            opinions=opinions,
            judge_decision=decision,
        )
