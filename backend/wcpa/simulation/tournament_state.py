"""Build a validated current tournament state from the synced schedule."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable

from wcpa.schemas.artifact import TournamentState, TournamentStateMatch


ROUND_ORDER = ("group", "R32", "R16", "QF", "SF", "Final")
CHAMPIONSHIP_ROUNDS = ("R32", "R16", "QF", "SF", "Final")
ANCHOR_ACTIVE_ROUND = {
    "current": "",
    "pre_tournament": "group",
    "post_group": "R32",
    "post_r32": "R16",
    "post_r16": "QF",
    "post_qf": "SF",
    "post_sf": "Final",
}
ROUND_LABELS = {
    "group": "小组赛",
    "R32": "32 强",
    "R16": "16 强",
    "QF": "8 强",
    "SF": "4 强",
    "Final": "决赛",
    "complete": "赛事结束",
}
_PLACEHOLDER = re.compile(r"^[WL]\d{1,3}$", re.IGNORECASE)
_PLACEHOLDER_LABELS = {
    "TBD",
    "TBC",
    "UNKNOWN",
    "N/A",
    "NA",
    "待定",
    "待确认",
    "未确定",
}


def normalize_stage(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "group": "group", "groupstage": "group",
        "r32": "R32", "roundof32": "R32", "32": "R32",
        "r16": "R16", "roundof16": "R16", "16": "R16",
        "qf": "QF", "quarterfinal": "QF", "quarterfinals": "QF",
        "sf": "SF", "semifinal": "SF", "semifinals": "SF",
        "final": "Final", "f": "Final",
        "thirdplace": "ThirdPlace", "3rdplace": "ThirdPlace",
    }
    return aliases.get(text, str(value or "").strip())


def is_complete(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "").lower() in {"complete", "completed", "final", "finished"}


def is_concrete_team(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.upper() not in _PLACEHOLDER_LABELS and not _PLACEHOLDER.fullmatch(text)


def resolve_winner(row: dict[str, Any]) -> str | None:
    winner = row.get("winner_team_id")
    if is_concrete_team(winner):
        return str(winner)
    home = row.get("home_team_id")
    away = row.get("away_team_id")
    home_score = row.get("home_score")
    away_score = row.get("away_score")
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return str(home) if is_concrete_team(home) else None
    if away_score > home_score:
        return str(away) if is_concrete_team(away) else None
    home_penalty = row.get("home_penalty")
    away_penalty = row.get("away_penalty")
    if home_penalty is not None and away_penalty is not None and home_penalty != away_penalty:
        return str(home if home_penalty > away_penalty else away)
    return None


def build_tournament_state(
    rows: Iterable[dict[str, Any]],
    all_team_ids: Iterable[str],
    requested_anchor: str = "current",
) -> TournamentState:
    schedule = schedule_for_anchor(rows, requested_anchor)
    schedule.sort(key=lambda row: (_stage_index(row["stage"]), row.get("kickoff_time") or "", row["match_id"]))
    championship = [row for row in schedule if row["stage"] in CHAMPIONSHIP_ROUNDS]
    errors: list[str] = []
    warnings: list[str] = []

    duplicate_ids = _duplicates(row["match_id"] for row in schedule)
    if duplicate_ids:
        errors.append("duplicate_match_ids:" + ",".join(sorted(duplicate_ids)))

    completed = [row for row in schedule if is_complete(row)]
    for row in completed:
        if row["stage"] in CHAMPIONSHIP_ROUNDS and resolve_winner(row) is None:
            errors.append(f"completed_match_without_winner:{row['match_id']}")
    if any(str(row.get("status") or "").lower() == "live" for row in schedule):
        warnings.append("live_match_in_progress")

    active_round = _active_round(schedule)
    if active_round == "complete":
        final = next((row for row in championship if row["stage"] == "Final" and is_complete(row)), None)
        alive = [resolve_winner(final)] if final and resolve_winner(final) else []
    elif active_round == "group":
        alive = sorted({team for row in schedule for team in _concrete_teams(row)})
    else:
        active_rows = [row for row in championship if row["stage"] == active_round]
        alive_set = {
            team
            for row in active_rows
            if not is_complete(row)
            for team in _concrete_teams(row)
        }
        alive_set.update(
            winner for row in active_rows if is_complete(row) for winner in [resolve_winner(row)] if winner
        )
        alive = sorted(alive_set)
        if any(not is_complete(row) and len(_concrete_teams(row)) < 2 for row in active_rows):
            errors.append(f"active_round_has_unresolved_participants:{active_round}")

    all_teams = sorted(set(all_team_ids))
    eliminated = sorted(set(all_teams) - set(alive))
    remaining = [row for row in championship if not is_complete(row)]
    predictable = [
        row for row in remaining
        if len(_concrete_teams(row)) == 2 and str(row.get("status") or "").lower() != "live"
    ]

    _validate_remaining_graph(remaining, championship, active_round, errors)
    as_of = _max_datetime(row.get("fetched_at") or row.get("data_as_of") for row in schedule)
    schedule_hash = _schedule_hash(schedule)
    active_rows = [row for row in schedule if row["stage"] == active_round]
    state = TournamentState(
        requested_anchor=requested_anchor,
        anchor_label=_anchor_label(active_round, active_rows),
        as_of_time=as_of,
        active_round=active_round,
        round_completed=sum(1 for row in active_rows if is_complete(row)),
        round_total=len(active_rows),
        completed_match_ids=[row["match_id"] for row in completed],
        remaining_match_ids=[row["match_id"] for row in remaining],
        predictable_match_ids=[row["match_id"] for row in predictable],
        alive_teams=alive,
        eliminated_teams=eliminated,
        locked_results=[_state_match(row, winner=resolve_winner(row)) for row in completed],
        remaining_matches=[_state_match(row) for row in remaining],
        schedule_snapshot_id=f"schedule-{schedule_hash[:16]}",
        schedule_hash=schedule_hash,
        validation_status="ready" if not errors else "invalid",
        validation_errors=errors,
        validation_warnings=warnings,
    )
    return state


def schedule_for_anchor(rows: Iterable[dict[str, Any]], requested_anchor: str = "current") -> list[dict[str, Any]]:
    """Return an anchor-safe schedule without leaking results after the chosen stage."""

    schedule = [_normalized_row(row) for row in rows]
    schedule.sort(key=lambda row: (_stage_index(row["stage"]), row.get("kickoff_time") or "", row["match_id"]))
    active_round = ANCHOR_ACTIVE_ROUND.get(requested_anchor, "") or ""
    if not active_round or requested_anchor == "current":
        return schedule
    if active_round not in ROUND_ORDER:
        return schedule

    cutoff = _stage_index(active_round)
    winners = {
        row["match_id"]: resolve_winner(row)
        for row in schedule
        if _stage_index(row["stage"]) < cutoff and is_complete(row) and resolve_winner(row)
    }
    incoming: dict[str, list[str]] = {}
    for row in schedule:
        next_id = row.get("next_match_id")
        if next_id:
            incoming.setdefault(str(next_id), []).append(row["match_id"])
    for values in incoming.values():
        values.sort()

    result: list[dict[str, Any]] = []
    for row in schedule:
        stage_index = _stage_index(row["stage"])
        if stage_index < cutoff:
            result.append(dict(row))
            continue
        next_row = _reset_future_result(row)
        if stage_index == cutoff:
            next_row = _fill_from_locked_sources(next_row, winners, incoming)
        elif row["stage"] in CHAMPIONSHIP_ROUNDS:
            next_row["home_team_id"] = None
            next_row["away_team_id"] = None
        result.append(next_row)
    return result


def _normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["stage"] = normalize_stage(row.get("stage"))
    result["match_id"] = str(row.get("match_id") or "")
    return result


def _reset_future_result(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["status"] = "scheduled"
    result["winner_team_id"] = None
    result["home_score"] = None
    result["away_score"] = None
    result["home_penalty"] = None
    result["away_penalty"] = None
    return result


def _fill_from_locked_sources(
    row: dict[str, Any],
    winners: dict[str, str | None],
    incoming: dict[str, list[str]],
) -> dict[str, Any]:
    result = dict(row)
    sources = [row.get("home_source_match_id"), row.get("away_source_match_id")]
    fallback = incoming.get(row["match_id"], [])
    if not is_concrete_team(result.get("home_team_id")):
        source = str(sources[0]) if sources[0] else (fallback[0] if fallback else "")
        if winners.get(source):
            result["home_team_id"] = winners[source]
    if not is_concrete_team(result.get("away_team_id")):
        source = str(sources[1]) if sources[1] else (fallback[1] if len(fallback) > 1 else "")
        if winners.get(source):
            result["away_team_id"] = winners[source]
    return result


def _active_round(schedule: list[dict[str, Any]]) -> str:
    for stage in ROUND_ORDER:
        rows = [row for row in schedule if row["stage"] == stage]
        if rows and any(not is_complete(row) for row in rows):
            return stage
    return "complete"


def _validate_remaining_graph(
    remaining: list[dict[str, Any]],
    championship: list[dict[str, Any]],
    active_round: str,
    errors: list[str],
) -> None:
    if active_round not in CHAMPIONSHIP_ROUNDS:
        return
    incoming: dict[str, list[str]] = {}
    for row in championship:
        next_id = row.get("next_match_id")
        if next_id:
            incoming.setdefault(str(next_id), []).append(row["match_id"])
    known_ids = {row["match_id"] for row in championship}
    for row in remaining:
        if row["stage"] == active_round:
            continue
        sources = [row.get("home_source_match_id"), row.get("away_source_match_id")]
        sources = [str(source) for source in sources if source]
        if len(sources) < 2:
            sources = incoming.get(row["match_id"], [])
        if len(sources) < 2 or any(source not in known_ids for source in sources[:2]):
            errors.append(f"unresolved_official_path:{row['match_id']}")


def _state_match(row: dict[str, Any], winner: str | None = None) -> TournamentStateMatch:
    return TournamentStateMatch(
        match_id=row["match_id"], stage=row["stage"], status=str(row.get("status") or "scheduled"),
        home_team_id=row.get("home_team_id"), away_team_id=row.get("away_team_id"),
        winner_team_id=winner or row.get("winner_team_id"), home_score=row.get("home_score"),
        away_score=row.get("away_score"), home_penalty=row.get("home_penalty"),
        away_penalty=row.get("away_penalty"), kickoff_time=row.get("kickoff_time"),
        next_match_id=row.get("next_match_id"), home_source_match_id=row.get("home_source_match_id"),
        away_source_match_id=row.get("away_source_match_id"),
    )


def _concrete_teams(row: dict[str, Any]) -> list[str]:
    return [str(team) for team in (row.get("home_team_id"), row.get("away_team_id")) if is_concrete_team(team)]


def _stage_index(stage: str) -> int:
    try:
        return ROUND_ORDER.index(stage)
    except ValueError:
        return len(ROUND_ORDER)


def _anchor_label(active_round: str, rows: list[dict[str, Any]]) -> str:
    if active_round == "complete":
        return "赛事已结束"
    completed = sum(1 for row in rows if is_complete(row))
    total = len(rows)
    suffix = f"（{completed}/{total} 已完成）" if completed and completed < total else ""
    return f"当前{ROUND_LABELS.get(active_round, active_round)}阶段{suffix}"


def _schedule_hash(schedule: list[dict[str, Any]]) -> str:
    fields = (
        "match_id", "stage", "status", "home_team_id", "away_team_id", "winner_team_id",
        "home_score", "away_score", "home_penalty", "away_penalty", "next_match_id",
        "home_source_match_id", "away_source_match_id", "fetched_at",
    )
    payload = [{field: row.get(field) for field in fields} for row in schedule]
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _max_datetime(values: Iterable[Any]) -> datetime | None:
    parsed: list[datetime] = []
    for value in values:
        if isinstance(value, datetime):
            parsed.append(value)
        elif value:
            try:
                parsed.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError:
                continue
    return max(parsed) if parsed else None


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
