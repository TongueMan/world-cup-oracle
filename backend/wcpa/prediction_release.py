"""Stage-aware prediction generation and candidate/published release management."""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.data.real_dataset import DataUnavailableError
from wcpa.data.team_feature_assembler import LiveTeamFeatureAssembler
from wcpa.features.feature_builder import build_features
from wcpa.prediction.external_context import ExternalContextResult, ExternalPredictionContextBuilder
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.prediction_report import attach_and_cache_report, load_cached_report
from wcpa.schemas.artifact import (
    DataQualityReport,
    DataSourceStatus,
    FeatureModuleStatus,
    ReasoningTrace,
    TournamentPrediction,
)
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import PredictionContext
from wcpa.schemas.tournament import Bracket, KnockoutSlot
from wcpa.shared.paths import CONFIG_DIR, PREDICTIONS_DIR
from wcpa.simulation.conditional_monte_carlo import run_conditional_monte_carlo
from wcpa.simulation.tournament_state import ANCHOR_ACTIVE_ROUND, CHAMPIONSHIP_ROUNDS, build_tournament_state, is_complete, is_concrete_team, normalize_stage, resolve_winner, schedule_for_anchor
from wcpa.worldcup.service import WorldCupDataService


MIN_PUBLISHED_SIMULATIONS = 10_000
MAX_SNAPSHOT_AGE_SECONDS = 60 * 60
RUN_LOCK = threading.Lock()


class PredictionArtifactStore:
    """Durable file-first artifact store with optional PostgreSQL mirroring."""

    def __init__(self, root: Path = PREDICTIONS_DIR, repository: PostgresRepository | None = None):
        self.root = root
        self.candidate_dir = root / "candidates"
        self.history_dir = root / "history"
        self.repository = repository

    def save_candidate(self, artifact: TournamentPrediction) -> None:
        anchor = _artifact_anchor(artifact)
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        self._write(self.candidate_dir / f"{artifact.artifact_id}.json", artifact)
        self._write(self._candidate_path(anchor), artifact)
        self._save_to_repository(artifact)

    def publish(self, artifact: TournamentPrediction) -> TournamentPrediction:
        validation_errors = validate_candidate(artifact)
        if validation_errors:
            raise ValueError("Cannot publish invalid prediction: " + ",".join(validation_errors))
        anchor = _artifact_anchor(artifact)
        published = _ensure_report(
            artifact.model_copy(update={"publication_status": "published"})
        )
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._write(self.history_dir / f"{published.artifact_id}.json", published)
        self._write(self._published_path(anchor), published)
        self._save_to_repository(published)
        return published

    def load_published(self, anchor: str = "current") -> TournamentPrediction | None:
        return self._load(self._published_path(anchor))

    def load_candidate(self, anchor: str = "current") -> TournamentPrediction | None:
        return self._load(self._candidate_path(anchor))

    def load_by_id(self, artifact_id: str) -> TournamentPrediction | None:
        for path in (
            self.history_dir / f"{artifact_id}.json",
            self.candidate_dir / f"{artifact_id}.json",
        ):
            artifact = self._load(path)
            if artifact:
                return artifact
        current = self.load_published()
        return current if current and current.artifact_id == artifact_id else None

    def list_snapshots(self) -> list[dict[str, Any]]:
        if not self.history_dir.exists():
            return []
        rows = []
        for path in self.history_dir.glob("*.json"):
            artifact = self._load(path)
            if artifact is None or validate_published_artifact(
                artifact,
                expected_anchor=_artifact_anchor(artifact),
            ):
                continue
            state = artifact.current_tournament_state
            rows.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "generated_at": artifact.generated_at,
                    "input_data_as_of": artifact.input_data_as_of,
                    "anchor_label": state.anchor_label if state else "未知阶段",
                    "requested_anchor": state.requested_anchor if state else "current",
                    "active_round": state.active_round if state else "unknown",
                    "schedule_hash": artifact.schedule_hash,
                    "simulation_count": artifact.simulation_count,
                    "data_verified": artifact.data_verified,
                    "publication_status": artifact.publication_status,
                    "quality_status": artifact.data_quality_report.status if artifact.data_quality_report else "unknown",
                    "usable": True,
                }
            )
        return sorted(rows, key=lambda row: str(row["generated_at"] or ""), reverse=True)

    @staticmethod
    def _load(path: Path) -> TournamentPrediction | None:
        if not path.exists():
            return None
        try:
            return TournamentPrediction.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write(path: Path, artifact: TournamentPrediction) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def _candidate_path(self, anchor: str) -> Path:
        return self.root / f"candidate-{_safe_anchor(anchor)}.json"

    def _published_path(self, anchor: str) -> Path:
        return self.root / f"published-{_safe_anchor(anchor)}.json"

    def _save_to_repository(self, artifact: TournamentPrediction) -> None:
        try:
            repository = self.repository or PostgresRepository()
            repository.save_prediction(artifact)
            self.repository = repository
        except Exception:
            # File persistence is the source of truth for local development; a database mirror
            # must not block user-facing prediction reads or generation.
            return


class StagePredictionEngine:
    """Build a v4 candidate from one synchronized schedule snapshot."""

    def __init__(
        self,
        seed: int = 42,
        simulations: int = MIN_PUBLISHED_SIMULATIONS,
        external_context_builder: ExternalPredictionContextBuilder | None = None,
        team_feature_assembler: LiveTeamFeatureAssembler | None = None,
    ):
        self.seed = seed
        self.simulations = simulations
        self.predictor = BaselineMatchPredictor()
        self.external_context_builder = external_context_builder or ExternalPredictionContextBuilder()
        self.team_feature_assembler = team_feature_assembler or LiveTeamFeatureAssembler()

    def build_candidate(
        self,
        schedule: list[dict[str, Any]],
        sync_status: dict[str, Any],
        anchor: str = "current",
        now: datetime | None = None,
    ) -> TournamentPrediction:
        generated_at = now or datetime.now(timezone.utc)
        run_id = f"prediction-{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        artifact_id = f"wc2026-{uuid.uuid4().hex}"
        schedule_source = _source_status(sync_status)
        schedule_team_ids = sorted({
            str(team_id)
            for row in schedule
            for team_id in (row.get("home_team_id"), row.get("away_team_id"))
            if is_concrete_team(team_id)
        })
        anchor_schedule = schedule_for_anchor(schedule, anchor)
        state = build_tournament_state(anchor_schedule, schedule_team_ids, requested_anchor=anchor)
        historical_replay = anchor != "current"

        team_data_report: DataQualityReport | None = None
        try:
            assembled = self.team_feature_assembler.build(
                anchor_schedule,
                state.alive_teams,
                now=generated_at,
                allow_live_sources=not historical_replay,
            )
            teams = assembled.teams
            team_data_report = assembled.report
        except DataUnavailableError as exc:
            teams = []
            team_data_report = exc.report
        team_map = {team.team_id: team for team in teams}
        features = build_features(teams) if teams else {}

        predictions = []
        scenario_predictions = []
        prediction_contexts: dict[str, PredictionContext] = {}
        external_source_statuses: list[DataSourceStatus] = []
        schedule_by_id = {str(row.get("match_id")): row for row in anchor_schedule}
        predictable_match_ids = state.predictable_match_ids if state.validation_status == "ready" else []
        for match_id in predictable_match_ids:
            row = schedule_by_id.get(match_id)
            if not row:
                continue
            home_id = str(row.get("home_team_id") or "")
            away_id = str(row.get("away_team_id") or "")
            if home_id not in team_map or away_id not in team_map:
                continue
            external = self._external_context(row, home_id, away_id, allow_live_evidence=not historical_replay)
            context = external.context
            prediction_contexts[match_id] = context
            external_source_statuses.extend(external.source_statuses)
            prediction = self.predictor.predict(
                Match(
                    match_id=match_id,
                    stage=normalize_stage(row.get("stage")),
                    home_team_id=home_id,
                    away_team_id=away_id,
                    kickoff_time=row.get("kickoff_time"),
                    source=str(row.get("source") or "worldcup_matches"),
                    status=str(row.get("status") or "scheduled"),
                ),
                team_map[home_id], team_map[away_id], features[home_id], features[away_id],
                np.random.default_rng(self.seed), allow_draw=False, context=context,
            )
            predictions.append(prediction)

        for row, home_id, away_id in _scenario_matchups(anchor_schedule, state):
            if home_id not in team_map or away_id not in team_map:
                continue
            scenario_row = {
                **row,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_team_raw": home_id,
                "away_team_raw": away_id,
            }
            external = self._external_context(scenario_row, home_id, away_id, allow_live_evidence=not historical_replay)
            context = external.context
            context_key = f"{row.get('match_id')}:{home_id}:{away_id}"
            prediction_contexts[context_key] = context
            external_source_statuses.extend(external.source_statuses)
            scenario_predictions.append(
                self.predictor.predict(
                    Match(
                        match_id=context_key,
                        stage=normalize_stage(row.get("stage")),
                        home_team_id=home_id,
                        away_team_id=away_id,
                        kickoff_time=row.get("kickoff_time"),
                        source="scenario_matchup",
                        status="scheduled",
                    ),
                    team_map[home_id], team_map[away_id], features[home_id], features[away_id],
                    np.random.default_rng(self.seed), allow_draw=False, context=context,
                )
            )

        probabilities = run_conditional_monte_carlo(
            teams, anchor_schedule, state, self.predictor, features,
            n_sims=self.simulations, seed=self.seed, prediction_contexts=prediction_contexts,
        ) if teams and state.validation_status == "ready" else []
        top = next((row for row in probabilities if row.is_alive), None)
        quality_errors = list(dict.fromkeys([
            *_candidate_quality_errors(state, sync_status, teams, generated_at, self.simulations),
            *_team_data_quality_errors(team_data_report),
            *_prediction_output_errors(probabilities, state, self.simulations),
        ]))
        data_verified = not quality_errors
        quality_report = DataQualityReport(
            status=(
                "ready"
                if data_verified
                else "data_unavailable"
                if "verified_team_model_features_unavailable" in quality_errors
                else "invalid"
            ),
            strict=True,
            missing=list(dict.fromkeys([
                *quality_errors,
                *_prediction_missing_fields([*predictions, *scenario_predictions]),
            ])),
            source_statuses=[
                schedule_source,
                *(team_data_report.source_statuses if team_data_report else []),
                *external_source_statuses,
            ],
            message=(
                "赛事状态、输入快照和条件模拟已通过正式发布校验。"
                if data_verified
                else "当前输入未生成有效冠军概率，本次结果不会作为正式预测展示。"
            ),
        )
        actual_champion = _actual_champion(schedule)
        return TournamentPrediction(
            edition="2026", seed=self.seed, mode="professional", artifact_version="6.0.0",
            artifact_id=artifact_id, run_id=run_id, publication_status="candidate",
            probability_profile="professional", simulation_count=self.simulations,
            generated_at=generated_at, input_data_as_of=state.as_of_time,
            schedule_snapshot_id=state.schedule_snapshot_id, schedule_hash=state.schedule_hash,
            model_config_hash=_model_config_hash(), current_tournament_state=state,
            feature_modules=_feature_modules([*predictions, *scenario_predictions]),
            team_features=sorted(features.values(), key=lambda item: item.team_id),
            bracket=_schedule_bracket(anchor_schedule),
            match_predictions=predictions,
            scenario_match_predictions=scenario_predictions,
            match_results=[item.model_dump(mode="json") for item in state.locked_results],
            champion_team_id=actual_champion if anchor == "current" else None,
            rational_champion=top.team_id if top else (actual_champion if anchor == "current" else None),
            champion_probabilities=probabilities,
            path_reconstruction_notes=[state.anchor_label],
            data_sources=[
                schedule_source,
                *(team_data_report.source_statuses if team_data_report else []),
                *external_source_statuses,
            ],
            reasoning_traces=_team_reasoning_traces(features, probabilities),
            data_verified=data_verified, data_quality_report=quality_report,
        )

    def _external_context(
        self,
        row: dict[str, Any],
        home_id: str,
        away_id: str,
        allow_live_evidence: bool = True,
    ) -> ExternalContextResult:
        if not allow_live_evidence:
            match_id = str(row.get("match_id") or "")
            return ExternalContextResult(
                context=PredictionContext(
                    structured_data_available=True,
                    missing_fields=["market_odds", "confirmed_lineup_or_injuries", "fresh_web_evidence"],
                    web_search_attempted=False,
                    web_search_succeeded=False,
                    neutral_venue=True,
                ),
                source_statuses=[
                    DataSourceStatus(
                        source_key=f"historical_replay_external_context:{match_id}",
                        status="not_connected",
                        credibility="D",
                        records=0,
                        message="历史预测起点回放不会采用生成时刻之后的赔率、新闻或伤停信息。",
                    )
                ],
            )
        try:
            return self.external_context_builder.build(row, home_id, away_id)
        except Exception as exc:
            return ExternalContextResult(
                context=PredictionContext(
                    structured_data_available=True,
                    missing_fields=["market_odds", "confirmed_lineup_or_injuries", "fresh_web_evidence"],
                ),
                source_statuses=[
                    DataSourceStatus(
                        source_key=f"external_evidence:{row.get('match_id')}",
                        status="failed",
                        credibility="D",
                        records=0,
                        message=f"外部证据构建失败：{type(exc).__name__}",
                    )
                ],
            )


class PredictionReleaseService:
    """Sync, generate, validate and conditionally promote a prediction."""

    def __init__(
        self,
        worldcup_service: WorldCupDataService | None = None,
        store: PredictionArtifactStore | None = None,
        engine: StagePredictionEngine | None = None,
    ):
        self.worldcup_service = worldcup_service or WorldCupDataService()
        self.store = store or PredictionArtifactStore()
        self.engine = engine or StagePredictionEngine()

    def run(self, sync_first: bool = True, anchor: str = "current") -> dict[str, Any]:
        if not RUN_LOCK.acquire(blocking=False):
            raise PredictionRunInProgress("prediction run already in progress")
        sync_error = ""
        try:
            if sync_first:
                try:
                    self.worldcup_service.sync_worldcup_data()
                except Exception as exc:  # keep the previous published artifact on source failure
                    sync_error = f"schedule_sync_failed:{type(exc).__name__}"
            schedule = self.worldcup_service.list_matches()
            sync_status = self.worldcup_service.get_sync_status()
            if sync_error:
                sync_status = {**sync_status, "last_status": "failed", "error_message": sync_error}
            candidate = self.engine.build_candidate(schedule, sync_status, anchor=anchor)
            self.store.save_candidate(candidate)
            reasons = validate_candidate(candidate)
            previous = self.store.load_published(anchor)
            if not reasons:
                published = self.store.publish(candidate)
                publish_status = "published"
            else:
                published = previous
                publish_status = "retained_previous" if previous else "candidate_only"
            boundary_publication = self._archive_boundary(published) if anchor == "current" and published else None
            return {
                "run_id": candidate.run_id,
                "publish_status": publish_status,
                "reason_codes": reasons,
                "candidate_artifact_id": candidate.artifact_id,
                "published_artifact_id": published.artifact_id if published else None,
                "archived_stage": _artifact_anchor(boundary_publication) if boundary_publication else None,
                "artifact": candidate.model_dump(mode="json"),
            }
        finally:
            RUN_LOCK.release()

    def _archive_boundary(self, prediction: TournamentPrediction) -> TournamentPrediction | None:
        """Persist the exact live inputs when a new tournament stage has not started yet."""

        state = prediction.current_tournament_state
        boundary = _boundary_anchor(state)
        if not boundary or self.store.load_published(boundary) is not None:
            return None
        archived = prediction.model_copy(
            deep=True,
            update={
                "artifact_id": f"wc2026-{uuid.uuid4().hex}",
                "run_id": f"{prediction.run_id}-boundary-{boundary}",
                "publication_status": "candidate",
                "champion_team_id": None,
                "current_tournament_state": state.model_copy(update={"requested_anchor": boundary}),
                "prediction_report": None,
            },
        )
        self.store.save_candidate(archived)
        return self.store.publish(archived)


class PredictionRunInProgress(RuntimeError):
    pass


def validate_candidate(artifact: TournamentPrediction) -> list[str]:
    reasons: list[str] = []
    state = artifact.current_tournament_state
    if state is None or state.validation_status != "ready":
        reasons.append("tournament_state_invalid")
    if not artifact.data_verified:
        reasons.append("data_not_verified")
    if artifact.data_quality_report is None or artifact.data_quality_report.status != "ready":
        reasons.append("data_quality_not_ready")
    if artifact.simulation_count < MIN_PUBLISHED_SIMULATIONS:
        reasons.append("simulation_count_below_minimum")
    alive = set(state.alive_teams if state else [])
    probability_sum = sum(row.probability for row in artifact.champion_probabilities)
    if artifact.champion_probabilities and abs(probability_sum - 1.0) > 1e-6:
        reasons.append("champion_probability_sum_invalid")
    if not artifact.champion_probabilities:
        reasons.append("champion_probabilities_empty")
    if any(not is_concrete_team(row.team_id) for row in artifact.champion_probabilities):
        reasons.append("placeholder_team_has_probability")
    if any(
        row.probability > 0 and row.simulation_count < MIN_PUBLISHED_SIMULATIONS
        for row in artifact.champion_probabilities
    ):
        reasons.append("champion_probability_simulation_count_below_minimum")
    if any(row.probability > 0 for row in artifact.champion_probabilities if row.team_id not in alive):
        reasons.append("eliminated_team_has_probability")
    prediction_ids = {row.match_id for row in artifact.match_predictions}
    if state and not prediction_ids.issubset(set(state.predictable_match_ids)):
        reasons.append("prediction_match_id_not_in_schedule")
    return list(dict.fromkeys(reasons))


def validate_published_artifact(
    artifact: TournamentPrediction,
    expected_anchor: str | None = None,
    current_state=None,
) -> list[str]:
    """Validate the single contract used by every public prediction read path."""

    reasons = validate_candidate(artifact)
    if artifact.publication_status != "published":
        reasons.append("prediction_not_published")
    state = artifact.current_tournament_state
    if expected_anchor and (state is None or state.requested_anchor != expected_anchor):
        reasons.append("prediction_anchor_mismatch")
    if expected_anchor == "current" and current_state is not None and state is not None:
        if not _same_tournament_state(state, current_state):
            reasons.append("current_tournament_state_mismatch")
    return list(dict.fromkeys(reasons))


def _artifact_anchor(artifact: TournamentPrediction) -> str:
    state = artifact.current_tournament_state
    return state.requested_anchor if state and state.requested_anchor else "current"


def _safe_anchor(anchor: str) -> str:
    return anchor if anchor in {"current", "pre_tournament", "post_group", "post_r32", "post_r16", "post_qf", "post_sf"} else "current"


def _ensure_report(artifact: TournamentPrediction) -> TournamentPrediction:
    cached = load_cached_report(artifact)
    if cached is not None:
        return artifact.model_copy(update={"prediction_report": cached})
    return attach_and_cache_report(artifact)


def _candidate_quality_errors(state, sync_status, teams, now, simulations) -> list[str]:
    errors = list(state.validation_errors)
    if str(sync_status.get("last_status") or "").lower() != "success":
        errors.append("schedule_sync_not_success")
    if state.as_of_time is None:
        errors.append("schedule_snapshot_time_missing")
    else:
        as_of = state.as_of_time
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        if state.requested_anchor == "current" and (now - as_of).total_seconds() > MAX_SNAPSHOT_AGE_SECONDS:
            errors.append("schedule_snapshot_stale")
    if "live_match_in_progress" in state.validation_warnings:
        errors.append("live_match_in_progress")
    team_map = {team.team_id: team for team in teams}
    if any(team_id not in team_map for team_id in state.alive_teams):
        errors.append("alive_team_features_missing")
    if simulations < MIN_PUBLISHED_SIMULATIONS:
        errors.append("simulation_count_below_minimum")
    return list(dict.fromkeys(errors))


def _team_data_quality_errors(report: DataQualityReport | None) -> list[str]:
    if report is None or report.status != "ready":
        return ["verified_team_model_features_unavailable"]
    return []


def _prediction_output_errors(probabilities, state, simulations: int) -> list[str]:
    errors: list[str] = []
    if not probabilities:
        errors.append("champion_probabilities_empty")
        return errors
    probability_sum = sum(row.probability for row in probabilities)
    if abs(probability_sum - 1.0) > 1e-6:
        errors.append("champion_probability_sum_invalid")
    alive = set(state.alive_teams)
    if any(row.probability > 0 and row.team_id not in alive for row in probabilities):
        errors.append("eliminated_team_has_probability")
    if any(not is_concrete_team(row.team_id) for row in probabilities):
        errors.append("placeholder_team_has_probability")
    if simulations < MIN_PUBLISHED_SIMULATIONS:
        errors.append("simulation_count_below_minimum")
    return errors


def _boundary_anchor(state) -> str | None:
    if state is None or state.validation_status != "ready" or state.round_completed != 0:
        return None
    for anchor, active_round in ANCHOR_ACTIVE_ROUND.items():
        if anchor != "current" and active_round == state.active_round:
            return anchor
    return None


def _same_tournament_state(left, right) -> bool:
    return (
        left.active_round == right.active_round
        and set(left.completed_match_ids) == set(right.completed_match_ids)
        and set(left.remaining_match_ids) == set(right.remaining_match_ids)
        and set(left.alive_teams) == set(right.alive_teams)
    )


def _source_status(status: dict[str, Any]) -> DataSourceStatus:
    value = str(status.get("last_status") or "unknown")
    return DataSourceStatus(
        source_key=str(status.get("source") or "worldcup_schedule"),
        status="ok" if value == "success" else value,
        credibility="B" if value == "success" else "D",
        fetched_at=status.get("last_success_at"),
        records=int(status.get("parsed_count") or status.get("fetched_count") or 0),
        message=str(status.get("error_message") or "赛程同步快照"),
    )


def _prediction_missing_fields(predictions) -> list[str]:
    values: list[str] = []
    for prediction in predictions:
        values.extend(prediction.missing_fields)
    return list(dict.fromkeys(values))


def _scenario_matchups(schedule, state, max_matchups: int = 8):
    """Enumerate near-term concrete matchup branches without turning placeholders into teams."""

    if state.validation_status != "ready":
        return []
    rows = [
        {**row, "stage": normalize_stage(row.get("stage")), "match_id": str(row.get("match_id") or "")}
        for row in schedule
        if normalize_stage(row.get("stage")) in CHAMPIONSHIP_ROUNDS
    ]
    by_id = {row["match_id"]: row for row in rows}
    incoming: dict[str, list[str]] = {}
    for row in rows:
        next_id = str(row.get("next_match_id") or "")
        if next_id:
            incoming.setdefault(next_id, []).append(row["match_id"])
    for values in incoming.values():
        values.sort()
    memo: dict[str, set[str]] = {}

    def possible_winners(match_id: str) -> set[str]:
        if match_id in memo:
            return memo[match_id]
        row = by_id.get(match_id)
        if not row:
            return set()
        winner = resolve_winner(row) if is_complete(row) else None
        if winner:
            memo[match_id] = {winner}
            return memo[match_id]
        home, away = side_options(row, 0), side_options(row, 1)
        memo[match_id] = home | away
        return memo[match_id]

    def side_options(row, index: int) -> set[str]:
        key = "home_team_id" if index == 0 else "away_team_id"
        if is_concrete_team(row.get(key)):
            return {str(row.get(key))}
        source_key = "home_source_match_id" if index == 0 else "away_source_match_id"
        source = str(row.get(source_key) or "")
        fallback = incoming.get(row["match_id"], [])
        if not source and len(fallback) > index:
            source = fallback[index]
        return possible_winners(source) if source else set()

    alive = set(state.alive_teams)
    result = []
    predictable = set(state.predictable_match_ids)
    for row in rows:
        if is_complete(row) or row["match_id"] in predictable:
            continue
        home_options = side_options(row, 0) & alive
        away_options = side_options(row, 1) & alive
        matchups = [
            (home, away)
            for home in sorted(home_options)
            for away in sorted(away_options)
            if home != away
        ]
        if not matchups or len(matchups) > max_matchups:
            continue
        result.extend((row, home, away) for home, away in matchups)
    return result


def _team_reasoning_traces(features, probabilities) -> list[ReasoningTrace]:
    probability_map = {row.team_id: row.probability for row in probabilities}
    traces = []
    factor_labels = {
        "normalized_fifa_rank": "FIFA 排名",
        "normalized_elo": "Elo 强度",
        "recent_form": "本届赛事近期状态",
        "attack": "进攻表现",
        "defense": "防守表现",
        "world_cup_experience": "世界杯经验",
        "squad_health": "阵容可用度",
    }
    for team_id, feature in sorted(features.items()):
        factors = [
            {"name": label, "value": round(float(getattr(feature, key)), 4)}
            for key, label in factor_labels.items()
        ]
        factors.sort(key=lambda item: item["value"], reverse=True)
        rank_text = f"FIFA 第 {feature.fifa_rank} 位" if feature.fifa_rank else "FIFA 排名未记录"
        elo_text = f"Elo {feature.elo_rating}" if feature.elo_rating else "Elo 未记录"
        traces.append(
            ReasoningTrace(
                target_id=team_id,
                summary=(
                    f"{rank_text}，{elo_text}；综合实力分 {feature.team_strength:.3f}，"
                    f"当前冠军概率 {probability_map.get(team_id, 0.0):.1%}。"
                ),
                top_factors=factors,
                assumptions=["所有特征值均来自本次预测保存的输入快照。"],
            )
        )
    return traces


def _feature_modules(predictions) -> dict[str, FeatureModuleStatus]:
    total = len(predictions)
    names = Counter(component.name for prediction in predictions for component in prediction.probability_components)
    adjustment_names = Counter(
        factor
        for prediction in predictions
        for factor in {adjustment.factor for adjustment in prediction.applied_adjustments}
    )
    evidence_fields: Counter[str] = Counter()
    for prediction in predictions:
        evidence_fields.update({
            field
            for evidence in prediction.evidence
            for field in evidence.supported_fields
        })
    web_evidence_count = sum(
        1
        for prediction in predictions
        if any(evidence.source_type == "web" for evidence in prediction.evidence)
    )
    result = {}
    labels = {
        "strength": "球队强度模型已进入本次概率。",
        "goals": "进球模型已进入本次概率。",
        "neutral_prior": "中性先验已进入本次概率。",
        "market": "本次预测未接入赔率数据。",
        "web_semantic": "本次预测未接入联网语义概率。",
        "lineup": "本次预测未接入确认阵容与伤停修正。",
        "environment": "环境信息尚未进入本次概率。",
        "rules": "已使用淘汰赛加时与点球基础规则，纪律规则未接入。",
        "discipline": "本次预测未接入黄牌与停赛纪律修正。",
        "tactical": "本次预测未接入战术对位修正。",
    }
    for name, message in labels.items():
        if name in {"lineup", "environment", "tactical"}:
            coverage = adjustment_names[name] / total if total else 0.0
            if name == "lineup":
                coverage = max(coverage, evidence_fields["lineup"] / total if total else 0.0, evidence_fields["injury"] / total if total else 0.0)
            if name == "environment":
                coverage = max(coverage, evidence_fields["environment"] / total if total else 0.0)
            if name == "tactical":
                coverage = max(coverage, evidence_fields["tactical"] / total if total else 0.0)
        elif name == "discipline":
            coverage = max(
                adjustment_names["suspension"] / total if total else 0.0,
                evidence_fields["discipline"] / total if total else 0.0,
            )
        elif name == "web_semantic":
            component_coverage = names[name] / total if total and name in names else 0.0
            evidence_coverage = web_evidence_count / total if total else 0.0
            coverage = max(component_coverage, evidence_coverage)
        else:
            coverage = names[name] / total if total and name in names else 0.0
        if name == "rules":
            result[name] = FeatureModuleStatus(enabled=True, status="partial", message=message, coverage=1.0 if total else 0.0)
        elif name in {"lineup", "environment", "discipline", "tactical"} and coverage > 0:
            result[name] = FeatureModuleStatus(
                enabled=True,
                status="available" if adjustment_names[name] or (name == "discipline" and adjustment_names["suspension"]) else "partial",
                message=_module_message(name, coverage),
                coverage=min(1.0, coverage),
            )
        elif name == "web_semantic" and coverage > 0:
            adopted = names[name] > 0
            result[name] = FeatureModuleStatus(
                enabled=True,
                status="available" if adopted else "partial",
                message=(
                    _module_message(name, coverage)
                    if adopted
                    else "联网新闻已经完成来源筛选并进入风险证据；本场未形成方向足够明确的语义概率修正。"
                ),
                coverage=min(1.0, coverage),
            )
        else:
            result[name] = FeatureModuleStatus(
                enabled=coverage > 0,
                status="available" if coverage > 0 else "not_connected",
                message=_module_message(name, coverage) if coverage > 0 and _module_message(name, coverage) else message,
                coverage=coverage,
            )
    return result


def _module_message(name: str, coverage: float) -> str:
    coverage_text = f"{coverage:.0%}"
    messages = {
        "market": f"赔率盘口已进入 {coverage_text} 的单场概率。",
        "web_semantic": f"可靠联网语义信号已进入 {coverage_text} 的单场概率。",
        "lineup": f"阵容、伤停或首发证据已覆盖 {coverage_text} 的预测场次。",
        "environment": f"天气或场馆环境证据已覆盖 {coverage_text} 的预测场次。",
        "discipline": f"黄牌、停赛或纪律证据已覆盖 {coverage_text} 的预测场次。",
        "tactical": f"战术对位证据已覆盖 {coverage_text} 的预测场次。",
    }
    return messages.get(name, "")


def _schedule_bracket(schedule: list[dict[str, Any]]) -> Bracket:
    slots = []
    for row in schedule:
        stage = normalize_stage(row.get("stage"))
        if stage not in CHAMPIONSHIP_ROUNDS:
            continue
        home = row.get("home_team_id") if is_concrete_team(row.get("home_team_id")) else None
        away = row.get("away_team_id") if is_concrete_team(row.get("away_team_id")) else None
        slots.append(
            KnockoutSlot(
                round=stage, match_id=str(row.get("match_id")), home_team_id=home,
                away_team_id=away, home_source=str(row.get("home_source_match_id") or ""),
                away_source=str(row.get("away_source_match_id") or ""),
                home_score=row.get("home_score"), away_score=row.get("away_score"),
                winner_team_id=resolve_winner(row), went_to_penalties=(
                    row.get("home_penalty") is not None or row.get("away_penalty") is not None
                ), status="final" if is_complete(row) else str(row.get("status") or "scheduled"),
            )
        )
    champion = _actual_champion(schedule)
    return Bracket(slots=slots, champion_team_id=champion)


def _actual_champion(schedule: list[dict[str, Any]]) -> str | None:
    final = next((row for row in schedule if normalize_stage(row.get("stage")) == "Final" and is_complete(row)), None)
    return resolve_winner(final) if final else None


def _model_config_hash() -> str:
    digest = hashlib.sha256()
    for path in (CONFIG_DIR / "model-weights.yml", CONFIG_DIR / "simulation.yml"):
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()
