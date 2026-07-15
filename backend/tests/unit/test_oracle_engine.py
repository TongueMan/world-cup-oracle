"""Full Oracle engine smoke tests."""

import pytest

from wcpa.schemas.match import Match
from wcpa.simulation.monte_carlo import _actual_result
from wcpa.simulation.oracle_tournament import OracleTournamentEngine


def test_oracle_engine_generates_48_team_shape(monkeypatch):
    monkeypatch.setenv("WCPA_ENABLE_WEB_COLLECTORS", "false")
    artifact = OracleTournamentEngine(seed=7).run(precompute_agents=False, strict=False)

    assert len(artifact.group_standings) == 12
    assert artifact.bracket is not None
    assert artifact.champion_team_id is not None
    assert len([slot for slot in artifact.bracket.slots if slot.round == "R32"]) == 16
    assert len(artifact.champion_probabilities) == 48
    assert sum(row.probability for row in artifact.champion_probabilities) == pytest.approx(1.0)
    assert all(row.probability_source == "monte_carlo" for row in artifact.champion_probabilities)
    assert all(row.simulation_count == 1000 for row in artifact.champion_probabilities)
    assert all(
        not any(key.startswith("reach_") for key in row.model_dump())
        for row in artifact.champion_probabilities
    )
    assert len(artifact.data_sources) > 0


def test_oracle_engine_has_third_place_contenders(monkeypatch):
    monkeypatch.setenv("WCPA_ENABLE_WEB_COLLECTORS", "false")
    artifact = OracleTournamentEngine(seed=7).run(precompute_agents=False, strict=False)

    third_rows = [
        row
        for standing in artifact.group_standings
        for row in standing.rows
        if row.rank == 3
    ]
    assert len(third_rows) == 12
    assert all(row.qualification_status == "third_place_contender" for row in third_rows)


def test_oracle_engine_strict_degrades_when_real_data_is_missing(monkeypatch):
    monkeypatch.setenv("WCPA_ENABLE_WEB_COLLECTORS", "false")
    artifact = OracleTournamentEngine(seed=7, monte_carlo_iterations=20).run(
        precompute_agents=False
    )

    assert artifact.champion_team_id is not None
    assert artifact.data_verified is False
    assert artifact.data_quality_report is not None
    assert artifact.data_quality_report.status == "degraded_prediction"
    assert artifact.data_quality_report.strict is True
    assert "低置信度预测" in artifact.data_quality_report.message


def test_finished_match_result_is_locked_for_simulation():
    match = Match(
        match_id="actual-1",
        stage="group",
        group="A",
        home_team_id="BRA",
        away_team_id="ARG",
        status="final",
        home_score=2,
        away_score=1,
        source="official_api",
    )

    result = _actual_result(match)

    assert result is not None
    assert result.is_actual is True
    assert result.winner_team_id == "BRA"
    assert result.home_score == 2
    assert result.away_score == 1
