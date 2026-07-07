"""Local match data coverage checks for Agent analysis/report tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SEARCH_WORTHY_FIELDS = {
    "injury_news",
    "lineup_prediction",
    "referee_assignment",
    "technical_stats",
    "coach_press_conference",
    "media_reports",
}


@dataclass(frozen=True)
class MatchDataCoverage:
    available_fields: list[str]
    missing_local_fields: list[str]
    search_worthy_missing_fields: list[str]


def build_match_data_coverage(context: dict[str, Any]) -> MatchDataCoverage:
    match = context.get("match") or {}
    environment = context.get("environment") or {}
    odds = context.get("odds") or {}
    available = []
    missing = []

    if match.get("home_team_raw") or match.get("home_team_id"):
        available.append("home_team")
    else:
        missing.append("home_team")
    if match.get("away_team_raw") or match.get("away_team_id"):
        available.append("away_team")
    else:
        missing.append("away_team")
    if match.get("kickoff_time") or match.get("kickoff_label"):
        available.append("kickoff_time")
    else:
        missing.append("kickoff_time")
    if match.get("home_score") is not None and match.get("away_score") is not None:
        available.append("score")
    elif match.get("status") in {"complete", "final"}:
        missing.append("score")
    if environment:
        available.append("environment")
    else:
        missing.append("environment")
    if odds.get("status") == "available":
        available.append("odds_snapshot")
    else:
        missing.append("odds_snapshot")

    for field in sorted(SEARCH_WORTHY_FIELDS):
        missing.append(field)

    search_worthy = [field for field in missing if field in SEARCH_WORTHY_FIELDS]
    return MatchDataCoverage(
        available_fields=available,
        missing_local_fields=missing,
        search_worthy_missing_fields=search_worthy,
    )
