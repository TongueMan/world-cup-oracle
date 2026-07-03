"""Thin MCP-ready tool functions for WorldCup structured data."""

from __future__ import annotations

from typing import Any

from wcpa.worldcup.service import WorldCupDataService


def get_worldcup_matches(
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    return WorldCupDataService().list_matches(date_from, date_to, status, stage)


def get_worldcup_bracket() -> list[dict[str, Any]]:
    return WorldCupDataService().get_bracket()


def get_match_detail(match_id: str) -> dict[str, Any] | None:
    return WorldCupDataService().get_match_detail(match_id)


def get_worldcup_standings() -> list[dict[str, Any]]:
    return WorldCupDataService().get_standings()


def get_worldcup_player_stats() -> list[dict[str, Any]]:
    return WorldCupDataService().get_player_stats()


def get_worldcup_sync_status() -> dict[str, Any]:
    return WorldCupDataService().get_sync_status()


def admin_sync_worldcup_data() -> dict[str, Any]:
    result = WorldCupDataService().sync_worldcup_data()
    return {
        "status": result.status,
        "fetched_count": result.fetched_count,
        "parsed_count": result.parsed_count,
        "inserted_count": result.inserted_count,
        "updated_count": result.updated_count,
        "raw_snapshot_dir": result.raw_snapshot_dir,
        "error_message": result.error_message,
    }
