"""API dependency helpers for prediction artifacts."""

from wcpa.prediction_release import PredictionArtifactStore, validate_published_artifact
from wcpa.schemas.artifact import TournamentPrediction
from wcpa.simulation.tournament_state import build_tournament_state, is_concrete_team
from wcpa.worldcup.service import WorldCupDataService


def load_prediction_artifact_unchecked(anchor: str = "current") -> TournamentPrediction | None:
    """Read the latest stage-aware artifact without production gating."""

    store = PredictionArtifactStore()
    return store.load_published(anchor) or store.load_candidate(anchor)


def get_prediction_artifact(strict: bool = True, anchor: str = "current") -> TournamentPrediction | None:
    """Return a prediction artifact only if it is valid for production by default."""

    store = PredictionArtifactStore()
    artifact = store.load_published(anchor) if strict else load_prediction_artifact_unchecked(anchor)
    if artifact is None:
        return None
    if strict:
        current_state = _load_current_tournament_state() if anchor == "current" else None
        if anchor == "current" and current_state is None:
            return None
        if validate_published_artifact(
            artifact,
            expected_anchor=anchor,
            current_state=current_state,
        ):
            return None
    return artifact


def get_prediction_artifact_by_id(
    artifact_id: str,
    expected_anchor: str | None = None,
) -> TournamentPrediction | None:
    """Return one exact, fully validated published prediction."""

    artifact = PredictionArtifactStore().load_by_id(artifact_id)
    if artifact is None:
        return None
    anchor = expected_anchor or (
        artifact.current_tournament_state.requested_anchor
        if artifact.current_tournament_state
        else None
    )
    current_state = _load_current_tournament_state() if anchor == "current" else None
    if anchor == "current" and current_state is None:
        return None
    if validate_published_artifact(
        artifact,
        expected_anchor=anchor,
        current_state=current_state,
    ):
        return None
    return artifact


def _load_current_tournament_state():
    try:
        schedule = WorldCupDataService().list_matches()
    except Exception:
        return None
    team_ids = sorted({
        str(team_id)
        for row in schedule
        for team_id in (row.get("home_team_id"), row.get("away_team_id"))
        if is_concrete_team(team_id)
    })
    return build_tournament_state(schedule, team_ids, requested_anchor="current")
