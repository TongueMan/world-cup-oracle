"""Team API routes."""

from fastapi import APIRouter, HTTPException

from wcpa.data.real_dataset import DataUnavailableError, load_strict_real_dataset
from wcpa.data.sources.web_collectors import WebCollector

router = APIRouter()


@router.get("")
async def get_teams():
    """Return verified real teams only."""
    snapshots = WebCollector().collect_all()
    try:
        teams, _, _ = load_strict_real_dataset([snapshot.status for snapshot in snapshots])
    except DataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=exc.report.model_dump(mode="json")) from exc
    return [team.model_dump(mode="json") for team in teams]
