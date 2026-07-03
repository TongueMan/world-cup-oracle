"""裁决权重测试。"""
import pytest
from wcpa.debate.judge import BaselineJudgeAgent
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.debate import AgentOpinion
from wcpa.shared.config_loader import load_config


def test_default_weights():
    """默认融合权重为 70/20/10。"""
    cfg = load_config("model-weights")
    weights = cfg["track_fusion"]["modes"]["balanced"]
    assert weights["rational"] == 0.70
    assert weights["narrative"] == 0.20
    assert weights["symbolic"] == 0.10


def test_rational_weight_minimum():
    """理性权重在 balanced/professional 模式不低于 60%。"""
    cfg = load_config("model-weights")
    assert cfg["track_fusion"]["min_rational_weight"] == 0.60

    # balanced 和 professional 模式理性权重 >= 0.60
    modes = cfg["track_fusion"]["modes"]
    assert modes["balanced"]["rational"] >= 0.60
    assert modes["professional"]["rational"] >= 0.60


def test_judge_preserves_rational_winner():
    """裁决应保持理性预测的胜者。"""
    judge = BaselineJudgeAgent()

    pred = MatchPrediction(
        match_id="test", home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1,
        predicted_score="2-0", winner_team_id="BRA",
        confidence=0.85, upset_index=0.0,
        consensus_type="rational_lead", reason_codes=["ranking_gap"],
    )

    decision = judge.adjudicate("test", [], pred)

    # 裁决胜者应与理性预测一致
    assert decision.winner_team_id == "BRA"
    assert decision.decision_type == "rational_lead"


def test_symbolic_weight_max():
    """象征权重默认不超过 10%。"""
    cfg = load_config("symbolic-rules")
    assert cfg["constraints"]["max_symbolic_weight"] == 0.10
