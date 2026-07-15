"""多源融合预测与数据降级测试。"""

from datetime import datetime, timezone

import pytest

from wcpa.prediction.market_model import aggregate_bookmaker_odds, devig_three_way
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.prediction.poisson_model import (
    most_likely_score,
    outcome_probabilities,
    score_probability_matrix,
)
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import (
    BookmakerOdds,
    PredictionContext,
    PredictionEvidence,
    ProbabilityAdjustment,
    SemanticProbabilitySignal,
)
from wcpa.shared.random_utils import create_rng


def _match() -> Match:
    return Match(
        match_id="fusion-test",
        stage="QF",
        home_team_id="BRA",
        away_team_id="ARG",
    )


def _team(teams, team_id):
    return next(team for team in teams if team.team_id == team_id)


def test_poisson_matrix_is_normalized_and_explainable():
    matrix = score_probability_matrix(1.7, 0.9, max_goals=8)

    assert float(matrix.sum()) == pytest.approx(1.0)
    assert sum(outcome_probabilities(matrix)) == pytest.approx(1.0)
    home_goals, away_goals = most_likely_score(matrix)
    assert matrix[home_goals, away_goals] == pytest.approx(float(matrix.max()))


def test_dixon_coles_matrix_remains_normalized():
    independent = score_probability_matrix(1.2, 1.1, dixon_coles_rho=0.0)
    corrected = score_probability_matrix(1.2, 1.1, dixon_coles_rho=-0.08)

    assert float(corrected.sum()) == pytest.approx(1.0)
    assert corrected[0, 0] != pytest.approx(independent[0, 0])


def test_market_odds_are_devigged_and_aggregated():
    probabilities, overround = devig_three_way(2.0, 3.4, 4.1)
    estimate = aggregate_bookmaker_odds(
        [
            BookmakerOdds(bookmaker="one", home=2.0, draw=3.4, away=4.1),
            BookmakerOdds(bookmaker="two", home=2.1, draw=3.3, away=3.9),
        ]
    )

    assert sum(probabilities) == pytest.approx(1.0)
    assert overround > 0
    assert estimate is not None
    assert sum(estimate.probabilities) == pytest.approx(1.0)
    assert estimate.bookmaker_count == 2


def test_missing_odds_still_returns_grade_c_prediction(teams, features):
    prediction = BaselineMatchPredictor().predict(
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(42),
        allow_draw=True,
    )

    assert prediction.data_grade == "C"
    assert prediction.confidence <= 0.65
    assert "market_odds" in prediction.missing_fields
    assert prediction.score_distribution
    assert sum(
        [prediction.home_win_prob, prediction.draw_prob, prediction.away_win_prob]
    ) == pytest.approx(1.0)
    assert "market" not in {component.name for component in prediction.probability_components}


def test_complete_multisource_context_returns_grade_a(teams, features):
    evidence = PredictionEvidence(
        evidence_id="web-1",
        claim="双方首发已由官方确认。",
        source_type="web",
        source_name="official team release",
        url="https://example.com/lineup",
        updated_at=datetime.now(timezone.utc),
        freshness=1.0,
        confidence=0.95,
        supported_fields=["lineup"],
    )
    context = PredictionContext(
        odds=[BookmakerOdds(bookmaker="book", home=2.4, draw=3.1, away=3.0)],
        evidence=[evidence],
        semantic_signal=SemanticProbabilitySignal(
            home_win_prob=0.42,
            draw_prob=0.30,
            away_win_prob=0.28,
            confidence=0.75,
            rationale=["官方首发完整"],
            evidence_ids=["web-1"],
        ),
        structured_data_available=True,
        lineup_data_available=True,
        web_search_attempted=True,
        web_search_succeeded=True,
    )
    prediction = BaselineMatchPredictor().predict(
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(42),
        context=context,
    )

    assert prediction.data_grade == "A"
    assert {component.name for component in prediction.probability_components} == {
        "market",
        "strength",
        "goals",
        "web_semantic",
    }
    assert prediction.evidence
    assert sum(
        component.effective_weight for component in prediction.probability_components
    ) == pytest.approx(1.0, abs=0.001)


def test_evidence_bound_context_adjustment_changes_probability(teams, features):
    predictor = BaselineMatchPredictor()
    base = predictor.predict(
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(42),
    )
    adjusted = predictor.predict(
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(42),
        context=PredictionContext(
            adjustments=[
                ProbabilityAdjustment(
                    factor="lineup",
                    home_delta=0.05,
                    away_delta=-0.05,
                    confidence=1.0,
                    rationale="主队关键球员确认复出",
                    evidence_ids=["lineup-1"],
                )
            ],
            evidence=[
                PredictionEvidence(
                    evidence_id="lineup-1",
                    claim="主队关键球员确认复出",
                    source_type="web",
                    source_name="official team release",
                    confidence=0.95,
                    supported_fields=["lineup.home"],
                )
            ],
        ),
    )

    assert adjusted.home_win_prob > base.home_win_prob
    assert adjusted.away_win_prob < base.away_win_prob
    assert adjusted.applied_adjustments[0].evidence_ids == ["lineup-1"]


def test_web_semantic_signal_drives_grade_d_without_structured_data():
    context = PredictionContext(
        structured_data_available=False,
        web_search_attempted=True,
        web_search_succeeded=True,
        semantic_signal=SemanticProbabilitySignal(
            home_win_prob=0.55,
            draw_prob=0.25,
            away_win_prob=0.20,
            confidence=0.8,
            rationale=["联网资料支持主队"],
        ),
    )
    prediction = BaselineMatchPredictor().predict(
        _match(),
        None,
        None,
        None,
        None,
        create_rng(42),
        context=context,
    )

    assert prediction.data_grade == "D"
    assert prediction.confidence <= 0.50
    assert prediction.home_win_prob > prediction.away_win_prob
    assert "web_semantic" in {
        component.name for component in prediction.probability_components
    }


def test_only_team_names_and_failed_web_still_return_grade_e_prediction():
    context = PredictionContext(
        structured_data_available=False,
        web_search_attempted=True,
        web_search_succeeded=False,
    )
    prediction = BaselineMatchPredictor().predict(
        _match(),
        None,
        None,
        None,
        None,
        create_rng(7),
        context=context,
    )

    assert prediction.data_grade == "E"
    assert prediction.confidence <= 0.35
    assert prediction.predicted_score
    assert prediction.winner_team_id is None or prediction.winner_team_id in {"BRA", "ARG"}
    assert sum(
        [prediction.home_win_prob, prediction.draw_prob, prediction.away_win_prob]
    ) == pytest.approx(1.0)


def test_knockout_has_separate_advancement_and_neutral_penalty_prior(teams, features):
    prediction = BaselineMatchPredictor().predict(
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
        create_rng(11),
        allow_draw=False,
    )

    assert prediction.winner_team_id in {"BRA", "ARG"}
    assert prediction.home_advancement_prob + prediction.away_advancement_prob == pytest.approx(1.0)
    assert prediction.penalty_home_win_prob == 0.5
    assert prediction.penalty_away_win_prob == 0.5
    assert prediction.extra_time_prob == prediction.draw_prob


def test_display_score_is_mode_and_does_not_depend_on_seed(teams, features):
    predictor = BaselineMatchPredictor()
    args = (
        _match(),
        _team(teams, "BRA"),
        _team(teams, "ARG"),
        features["BRA"],
        features["ARG"],
    )

    first = predictor.predict(*args, create_rng(1))
    second = predictor.predict(*args, create_rng(999))

    assert first.predicted_score == second.predicted_score
    top = first.score_distribution[0]
    assert first.predicted_score == f"{top.home_goals}-{top.away_goals}"
