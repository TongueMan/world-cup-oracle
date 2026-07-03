"""Prediction command routes."""

from fastapi import APIRouter, HTTPException

from wcpa.data.real_dataset import DataUnavailableError
from wcpa.simulation.oracle_tournament import OracleTournamentEngine

router = APIRouter()


@router.post("/tournament")
async def predict_tournament(
    seed: int = 42,
    mode: str = "balanced",
    precompute_agents: bool = True,
    strict: bool = True,
):
    """Run full prediction.

    Strict mode is default and refuses fixture/demo data.
    """
    try:
        artifact = OracleTournamentEngine(seed=seed, mode=mode).run_and_save(
            precompute_agents=precompute_agents,
            strict=strict,
        )
    except DataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=exc.report.model_dump(mode="json")) from exc
    return {
        "status": "complete",
        "seed": seed,
        "mode": mode,
        "precompute_agents": precompute_agents,
        "artifact": artifact.model_dump(mode="json"),
    }
