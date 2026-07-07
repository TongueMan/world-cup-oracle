"""WorldCup structured data tool API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from wcpa.worldcup.environment import WorldCupEnvironmentService
from wcpa.worldcup.history import WorldCupHistoryService
from wcpa.worldcup.service import WorldCupDataService

router = APIRouter()


@router.get("/history/editions")
async def list_worldcup_history_editions():
    return WorldCupHistoryService().list_editions()


@router.get("/history/editions/{year}")
async def get_worldcup_history_edition(year: int):
    edition = WorldCupHistoryService().get_edition(year)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"WorldCup edition {year} not found.")
    return edition


@router.get("/history/editions/{year}/matches")
async def list_worldcup_history_edition_matches(
    year: int,
    team: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    home_team: str | None = Query(default=None, alias="homeTeam"),
    away_team: str | None = Query(default=None, alias="awayTeam"),
):
    return WorldCupHistoryService().list_matches(
        year=year,
        team=team,
        stage=stage,
        home_team=home_team,
        away_team=away_team,
    )


@router.get("/history/matches")
async def list_worldcup_history_matches(
    year: int | None = Query(default=None),
    team: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    home_team: str | None = Query(default=None, alias="homeTeam"),
    away_team: str | None = Query(default=None, alias="awayTeam"),
):
    return WorldCupHistoryService().list_matches(
        year=year,
        team=team,
        stage=stage,
        home_team=home_team,
        away_team=away_team,
    )


@router.get("/history/teams/{team}/matches")
async def list_worldcup_history_team_matches(team: str):
    return WorldCupHistoryService().list_team_matches(team)


@router.get("/history/finals")
async def list_worldcup_history_finals():
    return WorldCupHistoryService().list_finals()


@router.get("/matches")
async def list_worldcup_matches(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str | None = Query(default=None),
    stage: str | None = Query(default=None),
):
    return WorldCupDataService().list_matches(date_from, date_to, status, stage)


@router.get("/matches/{match_id}/environment")
async def get_worldcup_match_environment(match_id: str):
    return WorldCupEnvironmentService().get_match_environment(match_id)


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


@router.get("/venues")
async def list_worldcup_venues():
    return WorldCupEnvironmentService().list_venues()


@router.get("/venues/{venue_id}")
async def get_worldcup_venue(venue_id: str):
    return WorldCupEnvironmentService().get_venue(venue_id)


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


@router.post("/admin/sync-venues")
async def admin_sync_worldcup_venues():
    service = WorldCupEnvironmentService()
    venue_report = service.sync_venues()
    match_venue_report = service.sync_match_venues()
    return {
        "status": "ok" if venue_report.status == "ok" else "partial",
        "venues": venue_report.__dict__,
        "match_venues": match_venue_report.__dict__,
    }


@router.post("/admin/sync-environment")
async def admin_sync_worldcup_environment():
    service = WorldCupEnvironmentService()
    elevation_report = service.sync_venue_elevation()
    weather_report = service.sync_match_weather()
    feature_report = service.build_match_environment_features()
    return {
        "status": "ok" if feature_report.loaded_count else "partial",
        "elevation": elevation_report.__dict__,
        "weather": weather_report.__dict__,
        "features": feature_report.__dict__,
    }
