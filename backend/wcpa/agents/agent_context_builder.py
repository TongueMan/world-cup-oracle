"""Build local context for match-scoped Agent tools."""

from __future__ import annotations

import re
from typing import Any

from wcpa.agents.odds_service import ApiFootballOddsService, OddsServiceError
from wcpa.worldcup.environment import WorldCupEnvironmentService, load_venue_seed
from wcpa.worldcup.service import WorldCupDataService


class AgentContextError(RuntimeError):
    """Raised when an Agent context cannot be built."""


def build_match_context(match_id: str) -> dict[str, Any]:
    service = WorldCupDataService()
    match = service.get_match_detail(match_id)
    if match is None:
        raise AgentContextError(f"WorldCup match {match_id} not found.")
    try:
        environment = WorldCupEnvironmentService().get_match_environment(match_id)
    except Exception:
        environment = None
    environment = _enrich_environment_from_match(match, environment)
    odds = _build_odds_context(match)
    return {
        "match": match,
        "environment": environment,
        "odds": odds,
        "bracket": _build_bracket_context(service, match),
        "team_history": _build_team_history_context(service, match),
    }


def match_label(context: dict[str, Any]) -> str:
    match = context.get("match") or {}
    home = match.get("home_team_raw") or match.get("home_team_id") or "TBD"
    away = match.get("away_team_raw") or match.get("away_team_id") or "TBD"
    return f"{home} vs {away}"


def _build_odds_context(match: dict[str, Any]) -> dict[str, Any]:
    try:
        return ApiFootballOddsService().get_match_odds(match)
    except OddsServiceError as exc:
        return {
            "provider": "api-football",
            "status": "api_error",
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            "provider": "api-football",
            "status": "internal_error",
            "reason": str(exc),
        }


def _enrich_environment_from_match(match: dict[str, Any], environment: dict[str, Any] | None) -> dict[str, Any]:
    current = dict(environment or {})
    current = _remove_time_misaligned_weather(match, current)
    venue = current.get("venue") if isinstance(current.get("venue"), dict) else {}
    if venue:
        return current
    source_venue_id = _match_source_venue_id(match)
    if not source_venue_id:
        return current or {
            "match_id": match.get("match_id"),
            "data_status": "data_unavailable",
            "reason": "match venue id missing",
        }
    seed_venue = _find_seed_venue_by_source_id(source_venue_id)
    if not seed_venue:
        return current or {
            "match_id": match.get("match_id"),
            "data_status": "data_unavailable",
            "reason": f"venue seed not found for {source_venue_id}",
            "source_venue_id": source_venue_id,
        }
    current.update(
        {
            "match_id": match.get("match_id"),
            "venue": seed_venue,
            "source_venue_id": source_venue_id,
            "data_status": "partial" if current else "venue_confirmed_weather_unavailable",
            "reason": current.get("reason") or "venue resolved from match metadata and venue seed",
        }
    )
    return current


def _remove_time_misaligned_weather(match: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
    if not environment.get("weather") or _match_has_precise_kickoff_time(match):
        return environment
    current = dict(environment)
    venue = current.get("venue") if isinstance(current.get("venue"), dict) else {}
    current.pop("weather", None)
    current["features"] = {}
    current["summary"] = "比赛日期和场馆已经确认，但缺少精确开球时刻，不能把小时级天气称为开球时天气。"
    current["data_status"] = "partial"
    current["reason"] = "kickoff_clock_time_unavailable"
    if venue:
        current["source"] = venue.get("source") or current.get("source")
        current["source_url"] = venue.get("source_url") or current.get("source_url")
    return current


def _match_has_precise_kickoff_time(match: dict[str, Any]) -> bool:
    label = " ".join(
        str(match.get(key) or "")
        for key in ("kickoff_label", "date_label", "time_label")
    )
    if re.search(r"\b\d{1,2}:\d{2}\b", label):
        return True
    warnings = {str(item) for item in match.get("parse_warnings") or []}
    return bool(match.get("kickoff_time")) and "kickoff_clock_time_missing" not in warnings and not label.strip()


def _match_source_venue_id(match: dict[str, Any]) -> str:
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    return str(metadata.get("venue_id") or match.get("venue") or "").strip()


def _find_seed_venue_by_source_id(source_venue_id: str) -> dict[str, Any] | None:
    try:
        venues = load_venue_seed()
    except Exception:
        return None
    for venue in venues:
        source_ids = [str(item) for item in venue.get("source_venue_ids") or []]
        if source_venue_id in source_ids or source_venue_id == str(venue.get("venue_id") or ""):
            return venue
    return None


def _build_bracket_context(service: WorldCupDataService, match: dict[str, Any]) -> dict[str, Any]:
    matches = service.list_matches()
    numbered = _infer_match_numbers(matches)
    current_number = next(
        (number for number, item in numbered.items() if item.get("match_id") == match.get("match_id")),
        None,
    )
    placeholders = []
    for side in ("home", "away"):
        code = str(match.get(f"{side}_team_id") or match.get(f"{side}_team_raw") or "")
        parsed = _parse_placeholder(code)
        if not parsed:
            continue
        result_type, number = parsed
        source_match = numbered.get(number)
        placeholders.append(
            {
                "side": side,
                "code": code,
                "kind": "winner" if result_type == "W" else "loser",
                "match_number": number,
                "source_match": _compact_match(source_match) if source_match else None,
                "status": "resolved_path_known" if source_match else "source_match_not_found",
            }
        )
    return {
        "current_match_number": current_number,
        "has_placeholders": bool(placeholders),
        "placeholders": placeholders,
        "policy": (
            "这些 W/L 编号是淘汰赛路径占位符，不是具体球队。回答时必须解释来源并做情景推演，"
            "不能把占位符编造成已确定球队。"
            if placeholders
            else ""
        ),
    }


def _build_team_history_context(service: WorldCupDataService, match: dict[str, Any]) -> dict[str, Any]:
    matches = service.list_matches()
    current_id = match.get("match_id")
    return {
        "home_previous_matches": _previous_completed_matches(matches, match.get("home_team_id"), current_id),
        "away_previous_matches": _previous_completed_matches(matches, match.get("away_team_id"), current_id),
    }


def _previous_completed_matches(
    matches: list[dict[str, Any]],
    team_id: str | None,
    current_match_id: str | None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if not team_id or str(team_id).startswith(("W", "L")):
        return []
    rows = []
    for item in matches:
        if item.get("match_id") == current_match_id:
            continue
        if item.get("status") not in {"complete", "final"}:
            continue
        if team_id not in {item.get("home_team_id"), item.get("away_team_id"), item.get("winner_team_id")}:
            continue
        rows.append(item)
    rows.sort(key=lambda item: str(item.get("kickoff_time") or item.get("kickoff_label") or ""), reverse=True)
    return [_compact_match_with_score(item) for item in rows[:limit]]


def _compact_match_with_score(match: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_match(match)
    for key in ("home_score", "away_score", "home_penalty", "away_penalty"):
        if match.get(key) is not None:
            compact[key] = match.get(key)
    return compact


def _infer_match_numbers(matches: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    numbers: dict[int, dict[str, Any]] = {}
    bases = {"R32": 73, "R16": 89, "QF": 97, "SF": 101}
    for stage, base in bases.items():
        stage_matches = [item for item in matches if item.get("stage") == stage]
        for index, item in enumerate(stage_matches):
            numbers[base + index] = item
    final = next((item for item in matches if item.get("stage") == "Final"), None)
    third_place = next((item for item in matches if item.get("stage") == "ThirdPlace"), None)
    if third_place:
        numbers[103] = third_place
    if final:
        numbers[104] = final
    return numbers


def _parse_placeholder(value: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"([WL])(\d{2,3})", value.strip(), re.I)
    if not match:
        return None
    return match.group(1).upper(), int(match.group(2))


def _compact_match(match: dict[str, Any] | None) -> dict[str, Any]:
    if not match:
        return {}
    return {
        key: match.get(key)
        for key in (
            "match_id",
            "stage",
            "status",
            "kickoff_time",
            "kickoff_label",
            "home_team_id",
            "away_team_id",
            "home_team_raw",
            "away_team_raw",
            "winner_team_id",
            "winner_team_raw",
        )
        if match.get(key) is not None
    }
