"""Schemas for the WorldCup structured data tool."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from wcpa.schemas import WCPABaseModel


class WorldCupTeam(WCPABaseModel):
    team_id: str
    name_en: str | None = None
    name_zh: str | None = None
    fifa_code: str | None = None
    aliases: list[str] = []
    flag_code: str | None = None


class WorldCupMatch(WCPABaseModel):
    match_id: str
    stage: str
    group_name: str | None = None
    kickoff_time: datetime | None = None
    kickoff_label: str | None = None
    resolved_kickoff_date: str | None = None
    date_confidence: str = "high"
    data_as_of: datetime | None = None
    home_team_id: str | None = None
    away_team_id: str | None = None
    winner_team_id: str | None = None
    home_team_raw: str | None = None
    away_team_raw: str | None = None
    winner_team_raw: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_penalty: int | None = None
    away_penalty: int | None = None
    status: str = "scheduled"
    next_match_id: str | None = None
    home_source_match_id: str | None = None
    away_source_match_id: str | None = None
    source: str = "bing_sports_html_fragment"
    source_url: str = ""
    raw_html_file: str = ""
    raw_content_hash: str = ""
    parser_version: str = "bing-html-v1"
    schema_version: str = "worldcup-match-v1"
    fetched_at: datetime | None = None
    parse_warnings: list[str] = []
    metadata: dict[str, Any] = {}


class WorldCupSyncStatus(WCPABaseModel):
    last_success_at: datetime | None = None
    last_failed_at: datetime | None = None
    last_status: str = "not_synced"
    source: str = "bing_sports_html_fragment"
    fetched_count: int = 0
    parsed_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    error_message: str | None = None
    raw_snapshot_dir: str | None = None
