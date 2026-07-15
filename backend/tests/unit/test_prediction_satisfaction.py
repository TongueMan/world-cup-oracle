"""预测用户满意度自动质量门测试。"""

from wcpa.agents.prediction_bridge import format_agent_match_prediction
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.prediction.satisfaction import evaluate_prediction_satisfaction
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import PredictionContext
from wcpa.shared.random_utils import create_rng


def _team(teams, team_id):
    return next(team for team in teams if team.team_id == team_id)


def test_complete_prediction_answer_passes_automatic_satisfaction_gate(teams, features):
    prediction = BaselineMatchPredictor().predict(
        Match(
            match_id="satisfaction",
            stage="QF",
            home_team_id="BRA",
            away_team_id="ARG",
        ),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(42),
        allow_draw=False,
    )
    answer = format_agent_match_prediction(prediction, "巴西", "阿根廷", 0)

    result = evaluate_prediction_satisfaction(prediction, answer)

    assert result.automatic_score == 60
    assert result.passed is True
    assert result.hard_failures == []


def test_low_data_prediction_still_passes_without_refusal():
    prediction = BaselineMatchPredictor().predict(
        Match(
            match_id="minimal-satisfaction",
            stage="group",
            home_team_id="Team Alpha",
            away_team_id="Team Beta",
        ),
        None,
        None,
        None,
        None,
        create_rng(7),
        context=PredictionContext(
            structured_data_available=False,
            web_search_attempted=True,
            web_search_succeeded=False,
        ),
    )
    answer = format_agent_match_prediction(prediction, "Team Alpha", "Team Beta", 0)

    result = evaluate_prediction_satisfaction(prediction, answer)

    assert prediction.data_grade == "E"
    assert result.passed is True
    assert "missing_data_refusal" not in result.hard_failures


def test_refusal_is_a_hard_failure(teams, features):
    prediction = BaselineMatchPredictor().predict(
        Match(match_id="refusal", stage="group", home_team_id="BRA", away_team_id="ARG"),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(1),
    )

    result = evaluate_prediction_satisfaction(
        prediction,
        "数据不足所以无法预测。",
    )

    assert result.passed is False
    assert "missing_data_refusal" in result.hard_failures
