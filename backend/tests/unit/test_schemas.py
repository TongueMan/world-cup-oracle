"""Schema 校验测试。"""
import pytest
from pydantic import ValidationError
from wcpa.schemas.team import Team
from wcpa.schemas.match import Match, MatchResult
from wcpa.schemas.prediction import MatchPrediction


def test_team_missing_required():
    with pytest.raises(ValidationError):
        Team(team_id="BRA")  # 缺少 name, confederation 等


def test_team_score_out_of_range():
    with pytest.raises(ValidationError):
        Team(team_id="BRA", name="Brazil", confederation="CONMEBOL",
             fifa_rank=1, elo_rating=2000,
             recent_form_score=1.5)  # 超过 1.0


def test_team_negative_rank():
    with pytest.raises(ValidationError):
        Team(team_id="BRA", name="Brazil", confederation="CONMEBOL",
             fifa_rank=-1, elo_rating=2000)


def test_match_valid():
    m = Match(match_id="G-A-001", stage="group", group="A",
              home_team_id="BRA", away_team_id="ARG")
    assert m.stage == "group"


def test_match_result_valid():
    r = MatchResult(match_id="G-A-001", home_score=2, away_score=1,
                    winner_team_id="BRA")
    assert r.home_score == 2
    assert r.went_to_penalties == False


def test_prediction_prob_range():
    with pytest.raises(ValidationError):
        MatchPrediction(match_id="x", home_win_prob=1.5,
                       draw_prob=0.2, away_win_prob=0.2,
                       predicted_score="1-0", confidence=0.5)


def test_team_valid():
    t = Team(team_id="BRA", name="Brazil", confederation="CONMEBOL",
             fifa_rank=1, elo_rating=2000,
             recent_form_score=0.8, attack_score=0.85,
             defense_score=0.75, squad_health_score=0.9,
             data_quality="A")
    assert t.team_id == "BRA"
