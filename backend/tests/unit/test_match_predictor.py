"""单场预测器测试。"""
import pytest
import numpy as np
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.schemas.match import Match
from wcpa.schemas.team import Team
from wcpa.schemas.artifact import TeamFeatures
from wcpa.features.feature_builder import build_features
from wcpa.shared.random_utils import create_rng


def test_strong_team_higher_win_prob(teams, features):
    """强队胜率应高于弱队。"""
    predictor = BaselineMatchPredictor()

    # ARG (fifa_rank=1) vs ECU (fifa_rank=32)
    match = Match(match_id="test", stage="group", group="X",
                 home_team_id="ARG", away_team_id="ECU")

    rng = create_rng(42)
    pred = predictor.predict(match,
                            next(t for t in teams if t.team_id == "ARG"),
                            next(t for t in teams if t.team_id == "ECU"),
                            features["ARG"], features["ECU"], rng, allow_draw=True)

    # ARG 胜率应高于 ECU 胜率
    assert pred.home_win_prob > pred.away_win_prob


def test_reproducibility(teams, features):
    """固定 seed 两次预测结果一致。"""
    predictor = BaselineMatchPredictor()
    match = Match(match_id="test", stage="group", group="X",
                 home_team_id="BRA", away_team_id="ARG")

    pred1 = predictor.predict(match,
                             next(t for t in teams if t.team_id == "BRA"),
                             next(t for t in teams if t.team_id == "ARG"),
                             features["BRA"], features["ARG"],
                             create_rng(42), allow_draw=True)
    pred2 = predictor.predict(match,
                             next(t for t in teams if t.team_id == "BRA"),
                             next(t for t in teams if t.team_id == "ARG"),
                             features["BRA"], features["ARG"],
                             create_rng(42), allow_draw=True)

    assert pred1.predicted_score == pred2.predicted_score
    assert pred1.winner_team_id == pred2.winner_team_id


def test_knockout_has_winner(teams, features):
    """淘汰赛必须产生 winner。"""
    predictor = BaselineMatchPredictor()

    # 多次模拟淘汰赛，确保每次都有 winner
    for seed in range(100):
        match = Match(match_id=f"k_{seed}", stage="QF",
                     home_team_id="BRA", away_team_id="ARG")
        rng = create_rng(seed)
        pred = predictor.predict(match,
                                next(t for t in teams if t.team_id == "BRA"),
                                next(t for t in teams if t.team_id == "ARG"),
                                features["BRA"], features["ARG"],
                                rng, allow_draw=False)
        assert pred.winner_team_id is not None, f"Seed {seed}: no winner in knockout"


def test_confidence_range(teams, features):
    """置信度在 [0, 1] 范围。"""
    predictor = BaselineMatchPredictor()
    for seed in range(50):
        match = Match(match_id=f"c_{seed}", stage="group", group="X",
                     home_team_id="FRA", away_team_id="ENG")
        pred = predictor.predict(match,
                                next(t for t in teams if t.team_id == "FRA"),
                                next(t for t in teams if t.team_id == "ENG"),
                                features["FRA"], features["ENG"],
                                create_rng(seed), allow_draw=True)
        assert 0 <= pred.confidence <= 1
        assert 0 <= pred.home_win_prob + pred.draw_prob + pred.away_win_prob <= 1.01
