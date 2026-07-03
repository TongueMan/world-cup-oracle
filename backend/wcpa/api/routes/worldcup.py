"""WorldCup structured data tool API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from wcpa.worldcup.service import WorldCupDataService

router = APIRouter()


@router.get("/matches")
async def list_worldcup_matches(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str | None = Query(default=None),
    stage: str | None = Query(default=None),
):
    return WorldCupDataService().list_matches(date_from, date_to, status, stage)


@router.get("/matches/{match_id}")
async def get_worldcup_match(match_id: str):
    match = WorldCupDataService().get_match_detail(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"WorldCup match {match_id} not found.")
    return match


@router.get("/bracket")
async def get_worldcup_bracket():
    return WorldCupDataService().get_bracket()


@router.get("/standings")
async def get_worldcup_standings():
    return WorldCupDataService().get_standings()


@router.get("/player-stats")
async def get_worldcup_player_stats():
    return WorldCupDataService().get_player_stats()


@router.get("/sync/status")
async def get_worldcup_sync_status():
    return WorldCupDataService().get_sync_status()


@router.post("/admin/sync")
async def admin_sync_worldcup_data():
    result = WorldCupDataService().sync_worldcup_data()
    return {
        "status": result.status,
        "fetched_count": result.fetched_count,
        "parsed_count": result.parsed_count,
        "inserted_count": result.inserted_count,
        "updated_count": result.updated_count,
        "error_message": result.error_message,
        "raw_snapshot_dir": result.raw_snapshot_dir,
    }
