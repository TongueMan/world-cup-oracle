"""Stage-aware prediction command routes."""

from fastapi import APIRouter, HTTPException

from wcpa.prediction_release import PredictionReleaseService, PredictionRunInProgress

router = APIRouter()
ALLOWED_ANCHORS = {"current", "pre_tournament", "post_group", "post_r32", "post_r16", "post_qf", "post_sf"}


@router.post("/tournament")
async def predict_tournament(
    seed: int = 42,
    mode: str = "professional",
    precompute_agents: bool = False,
    strict: bool = True,
    anchor: str = "current",
):
    """同步最新赛程，生成 candidate，并在通过门禁后发布。"""
    if seed != 42 or mode != "professional" or precompute_agents or not strict or anchor not in ALLOWED_ANCHORS:
        raise HTTPException(
            status_code=422,
            detail="Prediction requires a supported anchor, seed=42, mode=professional, precompute_agents=false and strict=true.",
        )
    try:
        return PredictionReleaseService().run(sync_first=True, anchor=anchor)
    except PredictionRunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
