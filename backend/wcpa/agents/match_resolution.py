"""Resolve match references from user-facing Agent questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from wcpa.worldcup.service import WorldCupDataService, _TEAM_ID_BY_ALIAS


TEAM_CODE_ALIASES = {
    "SUI": ["switzerland", "swiss", "瑞士"],
    "ALG": ["algeria", "阿尔及利亚"],
    "COL": ["colombia", "哥伦比亚"],
    "GHA": ["ghana", "加纳"],
    "ARG": ["argentina", "阿根廷"],
    "CPV": ["cape verde", "佛得角"],
    "FRA": ["france", "法国"],
    "PAR": ["paraguay", "巴拉圭"],
    "CAN": ["canada", "加拿大"],
    "MAR": ["morocco", "摩洛哥"],
    "POR": ["portugal", "葡萄牙"],
    "ESP": ["spain", "西班牙"],
    "USA": ["united states", "u.s.", "us", "usa", "美国"],
    "BEL": ["belgium", "比利时"],
    "BRA": ["brazil", "巴西"],
    "JPN": ["japan", "日本"],
}


@dataclass(frozen=True)
class MatchResolution:
    requested_team_ids: list[str]
    conflicts_current: bool
    candidates: list[dict[str, Any]]


def resolve_question_match(question: str, current_context: dict[str, Any]) -> MatchResolution:
    requested = extract_team_ids(question)
    if len(requested) < 2:
        return MatchResolution(requested, False, [])
    current = current_context.get("match") or {}
    current_ids = {
        current.get("home_team_id"),
        current.get("away_team_id"),
        *_current_raw_team_ids(current),
    }
    conflicts = set(requested[:2]) != {item for item in current_ids if item}
    candidates = find_matches_by_teams(requested[:2]) if conflicts else []
    return MatchResolution(requested[:2], conflicts, candidates)


def extract_team_ids(text: str) -> list[str]:
    normalized = _normalize_text(text)
    found: list[tuple[int, str]] = []
    for alias, team_id in _TEAM_ID_BY_ALIAS.items():
        position = _alias_position(normalized, alias)
        if position >= 0:
            found.append((position, team_id))
    for team_id, aliases in TEAM_CODE_ALIASES.items():
        code_match = re.search(rf"\b{re.escape(team_id.casefold())}\b", normalized)
        if code_match:
            found.append((code_match.start(), team_id))
        for alias in aliases:
            position = _alias_position(normalized, alias)
            if position >= 0:
                found.append((position, team_id))
    ordered: list[str] = []
    for _, team_id in sorted(found, key=lambda item: item[0]):
        _append_unique(ordered, team_id)
    return ordered


def _current_raw_team_ids(match: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("home_team_raw", "away_team_raw", "home_team_name", "away_team_name"):
        for team_id in extract_team_ids(str(match.get(key) or "")):
            _append_unique(ids, team_id)
    return ids


def find_matches_by_teams(team_ids: list[str]) -> list[dict[str, Any]]:
    if len(team_ids) < 2:
        return []
    left, right = team_ids[:2]
    rows = WorldCupDataService().list_matches()
    matches = []
    for row in rows:
        pair = {row.get("home_team_id"), row.get("away_team_id")}
        if {left, right} == {item for item in pair if item}:
            matches.append(_candidate(row))
    return matches[:5]


def match_summary(match: dict[str, Any]) -> dict[str, Any]:
    return _candidate(match)


def _candidate(match: dict[str, Any]) -> dict[str, Any]:
    home = match.get("home_team_raw") or match.get("home_team_id") or "TBD"
    away = match.get("away_team_raw") or match.get("away_team_id") or "TBD"
    return {
        "match_id": match.get("match_id"),
        "label": f"{home} vs {away}",
        "stage": match.get("stage"),
        "status": match.get("status"),
        "kickoff_time": match.get("kickoff_time"),
        "kickoff_label": match.get("kickoff_label"),
        "score": _score(match),
    }


def _score(match: dict[str, Any]) -> str | None:
    if match.get("home_score") is None or match.get("away_score") is None:
        return None
    return f"{match.get('home_score')}-{match.get('away_score')}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _alias_position(text: str, alias: str) -> int:
    normalized = alias.casefold()
    if not normalized:
        return -1
    if len(normalized) <= 3 and re.fullmatch(r"[a-z0-9.]+", normalized):
        match = re.search(rf"\b{re.escape(normalized)}\b", text)
        return match.start() if match else -1
    return text.find(normalized)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
