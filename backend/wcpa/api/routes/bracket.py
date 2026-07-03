"""Bracket API routes."""

from fastapi import APIRouter, HTTPException

from wcpa.api.deps import get_prediction_artifact

router = APIRouter()


@router.get("")
async def get_bracket():
    artifact = get_prediction_artifact()
    if artifact is None or artifact.bracket is None:
        raise HTTPException(status_code=409, detail="No verified bracket found.")
    return artifact.bracket.model_dump()
