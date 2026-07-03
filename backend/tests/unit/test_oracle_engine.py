"""Full Oracle engine smoke tests."""

import pytest

from wcpa.data.real_dataset import DataUnavailableError
from wcpa.simulation.oracle_tournament import OracleTournamentEngine


def test_oracle_engine_generates_48_team_shape(monkeypatch):
    monkeypatch.setenv("WCPA_ENABLE_WEB_COLLECTORS", "false")
    artifact = OracleTournamentEngine(seed=7).run(precompute_agents=False, strict=False)

    assert len(artifact.group_standings) == 12
    assert artifact.bracket is not None
    assert artifact.champion_team_id is not None
    assert len([slot for slot in artifact.bracket.slots if slot.round == "R32"]) == 16
    assert len(artifact.champion_probabilities) > 0
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


def test_oracle_engine_strict_refuses_missing_real_data(monkeypatch):
    monkeypatch.setenv("WCPA_ENABLE_WEB_COLLECTORS", "false")
    with pytest.raises(DataUnavailableError) as exc:
        OracleTournamentEngine(seed=7).run(precompute_agents=False)

    assert exc.value.report.status in {"data_unavailable", "invalid"}
    assert exc.value.report.strict is True
