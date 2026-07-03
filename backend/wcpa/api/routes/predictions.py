"""Prediction read and command routes."""

from fastapi import APIRouter, HTTPException

from wcpa.api.deps import get_prediction_artifact, load_prediction_artifact_unchecked
from wcpa.data.real_dataset import DataUnavailableError

router = APIRouter()


@router.get("/tournament")
async def get_tournament_prediction():
    """Return verified production prediction artifact."""
    artifact = get_prediction_artifact()
    if artifact is None:
        unchecked = load_prediction_artifact_unchecked()
        detail = (
            unchecked.data_quality_report.model_dump(mode="json")
            if unchecked and unchecked.data_quality_report
            else {
                "status": "data_unavailable",
                "message": "没有通过真实数据校验的正式预测结果。",
            }
        )
        raise HTTPException(status_code=409, detail=detail)
    return artifact.model_dump(mode="json")


@router.post("/run")
async def run_prediction(seed: int = 42, mode: str = "balanced", strict: bool = True):
    """Run prediction; strict mode refuses fixture/demo data."""
    from wcpa.simulation.oracle_tournament import OracleTournamentEngine

    try:
        artifact = OracleTournamentEngine(seed=seed, mode=mode).run_and_save(strict=strict)
    except DataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=exc.report.model_dump(mode="json")) from exc
    return {"status": "complete", "artifact": artifact.model_dump(mode="json")}


@router.get("/champion-probabilities")
async def get_champion_probabilities():
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return {
        "champion": artifact.champion_team_id,
        "runner_up": artifact.runner_up_team_id,
        "semifinalists": artifact.semifinalists,
        "probabilities": [item.model_dump() for item in artifact.champion_probabilities],
    }


@router.get("/upsets")
async def get_upsets():
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return artifact.upset_alerts


@router.get("/dark-horses")
async def get_dark_horses():
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return artifact.dark_horses


@router.get("/sources")
async def get_data_sources():
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return [source.model_dump() for source in artifact.data_sources]
