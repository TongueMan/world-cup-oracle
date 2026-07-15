"""Public prediction reads must share one fail-closed availability contract."""

from fastapi.testclient import TestClient

from wcpa.api import deps
from wcpa.api.server import app
from wcpa.schemas.artifact import ChampionProbability, DataQualityReport, TournamentPrediction
from wcpa.simulation.tournament_state import build_tournament_state


def test_strict_read_never_falls_back_to_candidate(monkeypatch):
    candidate = _valid_prediction(publication_status="candidate")

    class Store:
        def load_published(self, _anchor="current"):
            return None

        def load_candidate(self, _anchor="current"):
            return candidate

    monkeypatch.setattr(deps, "PredictionArtifactStore", Store)

    assert deps.get_prediction_artifact(strict=True) is None
    assert deps.get_prediction_artifact(strict=False) is candidate


def test_strict_read_rejects_empty_probabilities_even_when_flags_claim_ready(monkeypatch):
    invalid = _valid_prediction(publication_status="published").model_copy(
        update={"champion_probabilities": []}
    )

    class Store:
        def load_published(self, _anchor="current"):
            return invalid

    monkeypatch.setattr(deps, "PredictionArtifactStore", Store)
    monkeypatch.setattr(deps, "_load_current_tournament_state", lambda: invalid.current_tournament_state)

    assert deps.get_prediction_artifact(strict=True) is None


def test_current_read_rejects_a_published_prediction_from_an_older_match_state(monkeypatch):
    artifact = _valid_prediction(publication_status="published")
    newer_state = artifact.current_tournament_state.model_copy(
        update={
            "completed_match_ids": [*artifact.current_tournament_state.completed_match_ids, "SF-1"],
            "remaining_match_ids": ["SF-2", "FINAL"],
            "alive_teams": ["ARG", "ENG", "FRA"],
        }
    )

    class Store:
        def load_published(self, _anchor="current"):
            return artifact

    monkeypatch.setattr(deps, "PredictionArtifactStore", Store)
    monkeypatch.setattr(deps, "_load_current_tournament_state", lambda: newer_state)

    assert deps.get_prediction_artifact(strict=True) is None


def test_public_apis_return_unavailable_instead_of_candidate_payload(monkeypatch):
    monkeypatch.setattr("wcpa.api.routes.predictions.get_prediction_artifact", lambda strict=True, anchor="current": None)
    client = TestClient(app, raise_server_exceptions=False)

    tournament = client.get("/api/predictions/tournament?anchor=current")
    probabilities = client.get("/api/predictions/champion-probabilities")

    assert tournament.status_code == 409
    assert tournament.json()["detail"] == {
        "status": "verified_prediction_unavailable",
        "message": "该阶段暂无通过验证的预测报告。",
    }
    assert probabilities.status_code == 409
    assert probabilities.json()["detail"]["status"] == "verified_prediction_unavailable"


def _valid_prediction(publication_status: str) -> TournamentPrediction:
    schedule = [
        _match("QF-1", "QF", "ARG", "BRA", "complete", "ARG", "SF-1"),
        _match("QF-2", "QF", "FRA", "ESP", "complete", "FRA", "SF-1"),
        _match("QF-3", "QF", "ENG", "GER", "complete", "ENG", "SF-2"),
        _match("QF-4", "QF", "POR", "NED", "complete", "POR", "SF-2"),
        _match("SF-1", "SF", "ARG", "FRA", "scheduled", None, "FINAL"),
        _match("SF-2", "SF", "ENG", "POR", "scheduled", None, "FINAL"),
        {
            **_match("FINAL", "Final", "W101", "TBD", "scheduled", None, None),
            "home_source_match_id": "SF-1",
            "away_source_match_id": "SF-2",
        },
    ]
    team_ids = ["ARG", "BRA", "FRA", "ESP", "ENG", "GER", "POR", "NED"]
    state = build_tournament_state(schedule, team_ids)
    return TournamentPrediction(
        artifact_id="prediction-1",
        artifact_version="4.0.0",
        publication_status=publication_status,
        simulation_count=10_000,
        data_verified=True,
        data_quality_report=DataQualityReport(status="ready", strict=True),
        current_tournament_state=state,
        champion_probabilities=[
            ChampionProbability(team_id=team_id, probability=0.25, simulation_count=10_000)
            for team_id in state.alive_teams
        ],
    )


def _match(match_id, stage, home, away, status, winner, next_match_id):
    complete = status == "complete"
    return {
        "match_id": match_id,
        "stage": stage,
        "home_team_id": home,
        "away_team_id": away,
        "status": status,
        "winner_team_id": winner,
        "home_score": 2 if complete else None,
        "away_score": 1 if complete else None,
        "next_match_id": next_match_id,
        "fetched_at": "2026-07-15T00:00:00Z",
        "source": "official_test_schedule",
    }
