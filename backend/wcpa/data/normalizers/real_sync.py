"""Normalize Bing Sports snapshots into project real-data fragments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wcpa.data.sources.web_collectors import SourceSnapshot
from wcpa.shared.paths import NORMALIZED_DIR


def normalize_snapshots_to_real_files(
    snapshots: list[SourceSnapshot],
    output_dir: Path = NORMALIZED_DIR,
) -> dict[str, Any]:
    """Write real schedule/team fragments from Bing Sports without fake fields."""
    matches: list[dict[str, Any]] = []
    teams: dict[str, dict[str, Any]] = {}

    for snapshot in snapshots:
        records = snapshot.raw.get("records", {})
        for raw_match in records.get("matches", snapshot.raw.get("matches", [])):
            match = _normalize_match(raw_match)
            matches.append(match)
            for side in ("home", "away"):
                if raw_match.get(f"{side}_is_placeholder"):
                    continue
                team_id = raw_match.get(f"{side}_team_id")
                name = raw_match.get(f"{side}_name")
                if not team_id or not name:
                    continue
                teams.setdefault(
                    team_id,
                    {
                        "team_id": team_id,
                        "name": name,
                        "source_key": "bing_sports_worldcup",
                        "source_url": raw_match.get("source_url", ""),
                        "verified": True,
                        "raw_name": name,
                        "sport_radar_id": raw_match.get(f"{side}_sport_radar_id"),
                    },
                )

    matches = sorted({match["match_id"]: match for match in matches}.values(), key=lambda item: item["match_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    matches_path = output_dir / "matches.real.json"
    teams_path = output_dir / "teams.real.json"
    matches_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
    teams_path.write_text(json.dumps(list(teams.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "matches_path": str(matches_path),
        "teams_path": str(teams_path),
        "matches": len(matches),
        "teams": len(teams),
    }


def _normalize_match(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": raw["match_id"],
        "stage": raw.get("stage", ""),
        "group": raw.get("group"),
        "home_team_id": raw.get("home_team_id"),
        "away_team_id": raw.get("away_team_id"),
        "home_score": raw.get("home_score"),
        "away_score": raw.get("away_score"),
        "winner_team_id": _winner_team_id(raw),
        "kickoff_time": None,
        "kickoff_label": raw.get("kickoff_label", ""),
        "date_label": raw.get("date_label", ""),
        "venue": raw.get("venue_id"),
        "source": "bing_sports_worldcup",
        "status": raw.get("status", "scheduled"),
        "source_url": raw.get("source_url", ""),
        "verified": True,
        "raw_home_name": raw.get("home_name"),
        "raw_away_name": raw.get("away_name"),
        "home_is_placeholder": raw.get("home_is_placeholder", False),
        "away_is_placeholder": raw.get("away_is_placeholder", False),
        "is_actual": raw.get("is_actual", False),
    }


def _winner_team_id(raw: dict[str, Any]) -> str | None:
    home_score = raw.get("home_score")
    away_score = raw.get("away_score")
    if home_score is None or away_score is None or home_score == away_score:
        return None
    return raw.get("home_team_id") if home_score > away_score else raw.get("away_team_id")
