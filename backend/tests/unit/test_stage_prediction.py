"""Stage-aware tournament state, conditional simulation and release tests."""

from datetime import datetime, timedelta, timezone

import pytest

from wcpa.features.feature_builder import build_features
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.prediction_release import (
    PredictionArtifactStore,
    StagePredictionEngine,
    _boundary_anchor,
    _candidate_quality_errors,
    validate_candidate,
    validate_published_artifact,
)
from wcpa.data.real_dataset import DataUnavailableError
from wcpa.data.team_feature_assembler import LiveTeamFeatureResult
from wcpa.schemas.artifact import ChampionProbability, DataQualityReport, TournamentPrediction
from wcpa.schemas.team import Team
from wcpa.simulation.conditional_monte_carlo import run_conditional_monte_carlo
from wcpa.simulation.tournament_state import build_tournament_state, is_concrete_team


def test_post_qf_state_keeps_only_four_teams_alive():
    schedule = _post_qf_schedule()
    state = build_tournament_state(schedule, _team_ids())

    assert state.validation_status == "ready"
    assert state.active_round == "SF"
    assert state.round_completed == 0
    assert state.round_total == 2
    assert state.alive_teams == ["ARG", "BRA", "ENG", "FRA"]
    assert set(state.predictable_match_ids) == {"SF-1", "SF-2"}
    assert "QF-1" in state.completed_match_ids
    assert "FINAL" in state.remaining_match_ids


def test_exact_stage_boundary_is_eligible_for_immutable_archive():
    state = build_tournament_state(_post_qf_schedule(), _team_ids())

    assert state.active_round == "SF"
    assert state.round_completed == 0
    assert _boundary_anchor(state) == "post_qf"

    started = state.model_copy(update={"round_completed": 1})
    assert _boundary_anchor(started) is None


def test_partial_semifinal_state_includes_locked_winner_and_other_match():
    schedule = _post_qf_schedule()
    schedule[4].update(
        status="complete", home_score=2, away_score=1, winner_team_id="ARG"
    )
    state = build_tournament_state(schedule, _team_ids())

    assert state.active_round == "SF"
    assert state.round_completed == 1
    assert state.alive_teams == ["ARG", "ENG", "FRA"]
    assert state.predictable_match_ids == ["SF-2"]


def test_tbd_is_a_path_placeholder_and_does_not_break_partial_semifinal_simulation():
    teams = _teams()
    schedule = _post_qf_schedule()
    schedule[4].update(status="complete", home_score=2, away_score=1, winner_team_id="ARG")
    schedule[6].update(home_team_id="ARG", away_team_id="TBD")
    state = build_tournament_state(schedule, [team.team_id for team in teams])

    rows = run_conditional_monte_carlo(
        teams,
        schedule,
        state,
        BaselineMatchPredictor(),
        build_features(teams),
        n_sims=300,
        seed=42,
    )

    assert is_concrete_team("TBD") is False
    assert is_concrete_team("W102") is False
    assert sum(row.probability for row in rows) == pytest.approx(1.0)
    assert {row.team_id for row in rows if row.probability > 0} <= {"ARG", "FRA", "ENG"}


def test_conditional_monte_carlo_never_revives_qf_losers():
    teams = _teams()
    schedule = _post_qf_schedule()
    state = build_tournament_state(schedule, [team.team_id for team in teams])
    rows = run_conditional_monte_carlo(
        teams,
        schedule,
        state,
        BaselineMatchPredictor(),
        build_features(teams),
        n_sims=300,
        seed=42,
    )

    assert sum(row.probability for row in rows) == pytest.approx(1.0)
    assert all(row.probability == 0 for row in rows if row.team_id in {"NED", "ESP", "POR", "GER"})
    assert all(row.probability > 0 for row in rows if row.team_id in set(state.alive_teams))
    assert all(row.simulation_count == 300 for row in rows)


def test_final_state_distributes_probability_only_between_finalists():
    teams = _teams()
    schedule = _post_qf_schedule()
    schedule[4].update(status="complete", home_score=2, away_score=0, winner_team_id="ARG")
    schedule[5].update(status="complete", home_score=1, away_score=2, winner_team_id="ENG")
    schedule[6].update(home_team_id="ARG", away_team_id="ENG")
    state = build_tournament_state(schedule, [team.team_id for team in teams])
    rows = run_conditional_monte_carlo(
        teams, schedule, state, BaselineMatchPredictor(), build_features(teams), n_sims=300, seed=42
    )

    assert state.active_round == "Final"
    assert state.alive_teams == ["ARG", "ENG"]
    assert sum(row.probability for row in rows if row.team_id in {"ARG", "ENG"}) == pytest.approx(1.0)
    assert all(row.probability == 0 for row in rows if row.team_id not in {"ARG", "ENG"})


def test_post_qf_anchor_ignores_completed_semifinal_result():
    schedule = _post_qf_schedule()
    schedule[4].update(status="complete", home_score=2, away_score=0, winner_team_id="ARG")
    schedule[6].update(home_team_id="ARG", away_team_id="W102")

    state = build_tournament_state(schedule, _team_ids(), requested_anchor="post_qf")

    assert state.requested_anchor == "post_qf"
    assert state.active_round == "SF"
    assert "SF-1" not in state.completed_match_ids
    assert state.alive_teams == ["ARG", "BRA", "ENG", "FRA"]
    assert set(state.predictable_match_ids) == {"SF-1", "SF-2"}
    assert "FINAL" in state.remaining_match_ids


def test_post_sf_anchor_uses_semifinal_winners_only():
    schedule = _post_qf_schedule()
    schedule[4].update(status="complete", home_score=2, away_score=0, winner_team_id="ARG")
    schedule[5].update(status="complete", home_score=1, away_score=2, winner_team_id="ENG")
    schedule[6].update(home_team_id="ARG", away_team_id="ENG", status="scheduled")

    state = build_tournament_state(schedule, _team_ids(), requested_anchor="post_sf")

    assert state.requested_anchor == "post_sf"
    assert state.active_round == "Final"
    assert state.alive_teams == ["ARG", "ENG"]
    assert state.predictable_match_ids == ["FINAL"]
    assert "SF-1" in state.completed_match_ids
    assert "SF-2" in state.completed_match_ids


def test_snapshot_freshness_boundary_is_sixty_minutes():
    now = datetime.now(timezone.utc)
    state = build_tournament_state(_post_qf_schedule(), _team_ids())
    sync_status = {"last_status": "success"}
    teams = _teams()

    fresh = state.model_copy(update={"as_of_time": now - timedelta(minutes=59)})
    stale = state.model_copy(update={"as_of_time": now - timedelta(minutes=61)})

    assert "schedule_snapshot_stale" not in _candidate_quality_errors(fresh, sync_status, teams, now, 10_000)
    assert "schedule_snapshot_stale" in _candidate_quality_errors(stale, sync_status, teams, now, 10_000)


def test_candidate_validation_rejects_eliminated_probability():
    state = build_tournament_state(_post_qf_schedule(), _team_ids())
    artifact = TournamentPrediction(
        artifact_version="4.0.0",
        publication_status="candidate",
        simulation_count=10_000,
        data_verified=True,
        current_tournament_state=state,
        champion_probabilities=[
            ChampionProbability(team_id="ARG", probability=0.9, simulation_count=10_000),
            ChampionProbability(team_id="NED", probability=0.1, is_alive=False, simulation_count=10_000),
        ],
    )

    assert "eliminated_team_has_probability" in validate_candidate(artifact)


def test_candidate_cannot_claim_ready_when_champion_probabilities_are_empty():
    state = build_tournament_state(_post_qf_schedule(), _team_ids())
    artifact = TournamentPrediction(
        artifact_version="4.0.0",
        publication_status="candidate",
        simulation_count=10_000,
        data_verified=True,
        data_quality_report=DataQualityReport(status="ready", strict=True),
        current_tournament_state=state,
        champion_probabilities=[],
    )

    assert "champion_probabilities_empty" in validate_candidate(artifact)
    published = artifact.model_copy(update={"publication_status": "published"})
    assert "champion_probabilities_empty" in validate_published_artifact(published, "current")


def test_stage_engine_fails_closed_when_verified_team_features_are_unavailable():
    report = DataQualityReport(
        status="data_unavailable",
        strict=True,
        missing=["missing_required_model_fields"],
        message="真实球队模型字段不完整。",
    )

    class UnavailableAssembler:
        def build(self, _schedule, _required_team_ids, now=None, allow_live_sources=True):
            raise DataUnavailableError(report)

    candidate = StagePredictionEngine(
        simulations=10_000,
        team_feature_assembler=UnavailableAssembler(),
    ).build_candidate(
        _post_qf_schedule(),
        {"last_status": "success", "source": "official_test_schedule"},
        anchor="current",
    )

    assert candidate.champion_probabilities == []
    assert candidate.data_verified is False
    assert candidate.data_quality_report.status == "data_unavailable"
    assert "verified_team_model_features_unavailable" in candidate.data_quality_report.missing


def test_historical_anchor_replay_can_be_regenerated_without_live_evidence_leakage():
    ready_report = DataQualityReport(status="ready", strict=True)

    class ReadyAssembler:
        def build(self, _schedule, required_team_ids, now=None, allow_live_sources=True):
            required = set(required_team_ids)
            return LiveTeamFeatureResult(
                teams=[team for team in _teams() if team.team_id in required],
                report=ready_report,
            )

    schedule = _post_qf_schedule()
    schedule[4].update(status="complete", home_score=2, away_score=0, winner_team_id="ARG")
    schedule[6].update(home_team_id="ARG", away_team_id="W102")

    candidate = StagePredictionEngine(
        simulations=10_000,
        team_feature_assembler=ReadyAssembler(),
    ).build_candidate(
        schedule,
        {"last_status": "success", "source": "official_test_schedule"},
        anchor="post_qf",
    )

    assert {row.match_id for row in candidate.match_predictions} == {"SF-1", "SF-2"}
    assert candidate.champion_probabilities
    assert candidate.data_verified is True
    assert candidate.data_quality_report.status == "ready"
    assert "historical_anchor_not_at_live_boundary" not in candidate.data_quality_report.missing
    assert any(
        source.source_key.startswith("historical_replay_external_context:")
        for source in candidate.data_quality_report.source_statuses
    )


def test_rejected_candidate_does_not_replace_published(tmp_path, monkeypatch):
    store = PredictionArtifactStore(root=tmp_path)
    state = build_tournament_state(_post_qf_schedule(), _team_ids())
    published = TournamentPrediction(
        artifact_id="published-1",
        artifact_version="4.0.0",
        publication_status="candidate",
        simulation_count=10_000,
        data_verified=True,
        data_quality_report=DataQualityReport(status="ready", strict=True),
        current_tournament_state=state,
        champion_probabilities=[
            ChampionProbability(team_id=team_id, probability=0.25, simulation_count=10_000)
            for team_id in state.alive_teams
        ],
    )
    monkeypatch.setattr("wcpa.prediction_release._ensure_report", lambda artifact: artifact)
    store.publish(published)
    candidate = TournamentPrediction(
        artifact_id="candidate-2", artifact_version="4.0.0", publication_status="candidate"
    )
    store.save_candidate(candidate)

    assert store.load_published().artifact_id == "published-1"
    assert store.load_candidate().artifact_id == "candidate-2"


def test_fresh_live_evidence_run_replaces_published_even_when_schedule_is_unchanged(tmp_path, monkeypatch):
    store = PredictionArtifactStore(root=tmp_path)
    state = build_tournament_state(_post_qf_schedule(), _team_ids())
    monkeypatch.setattr("wcpa.prediction_release._ensure_report", lambda artifact: artifact)

    def ready_prediction(artifact_id: str) -> TournamentPrediction:
        return TournamentPrediction(
            artifact_id=artifact_id,
            artifact_version="4.0.0",
            publication_status="candidate",
            simulation_count=10_000,
            data_verified=True,
            data_quality_report=DataQualityReport(status="ready", strict=True),
            current_tournament_state=state,
            schedule_hash=state.schedule_hash,
            model_config_hash="same-model",
            seed=42,
            champion_probabilities=[
                ChampionProbability(team_id=team_id, probability=0.25, simulation_count=10_000)
                for team_id in state.alive_teams
            ],
        )

    store.publish(ready_prediction("published-before-live-refresh"))
    store.publish(ready_prediction("published-after-live-refresh"))

    assert store.load_published().artifact_id == "published-after-live-refresh"


def _post_qf_schedule():
    now = datetime.now(timezone.utc).isoformat()
    return [
        _match("QF-1", "QF", "ARG", "NED", "complete", "ARG", "SF-1", now),
        _match("QF-2", "QF", "BRA", "ESP", "complete", "BRA", "SF-1", now),
        _match("QF-3", "QF", "FRA", "POR", "complete", "FRA", "SF-2", now),
        _match("QF-4", "QF", "ENG", "GER", "complete", "ENG", "SF-2", now),
        _match("SF-1", "SF", "ARG", "BRA", "scheduled", None, "FINAL", now),
        _match("SF-2", "SF", "FRA", "ENG", "scheduled", None, "FINAL", now),
        {
            **_match("FINAL", "Final", "W101", "W102", "scheduled", None, None, now),
            "home_source_match_id": "SF-1",
            "away_source_match_id": "SF-2",
        },
    ]


def _match(match_id, stage, home, away, status, winner, next_match_id, fetched_at):
    completed = status == "complete"
    return {
        "match_id": match_id,
        "stage": stage,
        "home_team_id": home,
        "away_team_id": away,
        "status": status,
        "winner_team_id": winner,
        "home_score": 2 if completed else None,
        "away_score": 1 if completed else None,
        "next_match_id": next_match_id,
        "fetched_at": fetched_at,
        "source": "official_test_schedule",
    }


def _team_ids():
    return ["ARG", "NED", "BRA", "ESP", "FRA", "POR", "ENG", "GER"]


def _teams():
    rows = []
    for index, team_id in enumerate(_team_ids(), 1):
        rows.append(
            Team(
                team_id=team_id,
                name=team_id,
                confederation="TEST",
                fifa_rank=index,
                elo_rating=1900 - index * 20,
                recent_form_score=0.8 - index * 0.02,
                attack_score=0.82 - index * 0.02,
                defense_score=0.8 - index * 0.02,
                squad_health_score=0.85,
                world_cup_experience_score=0.75,
                data_quality="B",
                source_key="test",
                verified=True,
            )
        )
    return rows
