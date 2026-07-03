"""Service layer for WorldCup structured data queries and sync."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.data.sources.bing_worldcup import (
    BingKnowledgeRun,
    BingSportsWorldCupCollector,
    write_bing_knowledge_files,
)
from wcpa.schemas.worldcup import WorldCupMatch, WorldCupSyncStatus
from wcpa.shared.paths import DATA_DIR

WORLD_CUP_DIR = DATA_DIR / "knowledge" / "worldcup"
MATCHES_FILE = WORLD_CUP_DIR / "matches.json"
TEAMS_FILE = WORLD_CUP_DIR / "teams.json"
STANDINGS_FILE = WORLD_CUP_DIR / "standings.json"
SYNC_STATUS_FILE = WORLD_CUP_DIR / "sync_status.json"

SOURCE = "bing_sports_html_fragment"
PARSER_VERSION = "bing-html-v1"
MATCH_SCHEMA_VERSION = "worldcup-match-v1"
STANDING_SCHEMA_VERSION = "worldcup-standing-v1"
CHINA_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class WorldCupSyncResult:
    status: str
    matches: list[dict[str, Any]]
    teams: list[dict[str, Any]]
    standings: list[dict[str, Any]]
    fetched_count: int
    parsed_count: int
    inserted_count: int
    updated_count: int
    error_message: str | None
    raw_snapshot_dir: str | None


class WorldCupDataService:
    def __init__(
        self,
        repository: PostgresRepository | None = None,
        collector: BingSportsWorldCupCollector | None = None,
    ):
        self.repository = repository or PostgresRepository()
        self.collector = collector or BingSportsWorldCupCollector()

    def sync_worldcup_data(self) -> WorldCupSyncResult:
        started_at = datetime.now(timezone.utc)
        try:
            run = self.collector.collect()
            write_bing_knowledge_files(run)
            normalized = normalize_bing_run(run)
            WORLD_CUP_DIR.mkdir(parents=True, exist_ok=True)
            _write_json(MATCHES_FILE, normalized["matches"])
            _write_json(TEAMS_FILE, normalized["teams"])
            _write_json(STANDINGS_FILE, normalized["standings"])

            for snapshot in run.snapshots:
                self.repository.save_source_snapshot(
                    snapshot.source_key,
                    snapshot.url,
                    snapshot.status.status,
                    snapshot.status.credibility,
                    snapshot.raw,
                    snapshot.status.message,
                )
            self.repository.save_knowledge_records(run.records, run.manifest)
            self.repository.upsert_worldcup_teams(normalized["teams"])
            counts = self.repository.upsert_worldcup_matches(normalized["matches"])
            self.repository.upsert_worldcup_standings(normalized["standings"])

            status = "success" if len(normalized["matches"]) >= 104 else "partial"
            result = WorldCupSyncResult(
                status=status,
                matches=normalized["matches"],
                teams=normalized["teams"],
                standings=normalized["standings"],
                fetched_count=len(run.records.get("matches", [])),
                parsed_count=len(normalized["matches"]),
                inserted_count=counts["inserted"],
                updated_count=counts["updated"],
                error_message=None,
                raw_snapshot_dir=run.manifest.get("raw_dir"),
            )
            self._save_sync_run(started_at, result)
            return result
        except Exception as exc:
            result = WorldCupSyncResult(
                status="failed",
                matches=[],
                teams=[],
                standings=[],
                fetched_count=0,
                parsed_count=0,
                inserted_count=0,
                updated_count=0,
                error_message=str(exc),
                raw_snapshot_dir=None,
            )
            self._save_sync_run(started_at, result)
            raise

    def list_matches(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        stage: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.repository.load_worldcup_matches(date_from, date_to, status, stage)
        if not rows:
            rows = _read_json_list(MATCHES_FILE)
        return _filter_matches(rows, date_from, date_to, status, stage)

    def get_match_detail(self, match_id: str) -> dict[str, Any] | None:
        row = self.repository.load_worldcup_match(match_id)
        if row:
            return row
        return next((match for match in _read_json_list(MATCHES_FILE) if match.get("match_id") == match_id), None)

    def get_bracket(self) -> list[dict[str, Any]]:
        rows = self.repository.load_worldcup_bracket()
        if not rows:
            rows = [
                match
                for match in _read_json_list(MATCHES_FILE)
                if match.get("stage") != "group" or match.get("next_match_id")
            ]
        return rows

    def get_standings(self) -> list[dict[str, Any]]:
        rows = self.repository.load_worldcup_standings()
        return rows or _read_json_list(STANDINGS_FILE)

    def get_player_stats(self) -> list[dict[str, Any]]:
        rows = self.repository.load_bing_knowledge_records("player_stats")
        if rows:
            return _filter_player_stats(rows)
        return _filter_player_stats(_read_jsonl(DATA_DIR / "knowledge" / "bing" / "player_stats.jsonl"))

    def get_sync_status(self) -> dict[str, Any]:
        status = self.repository.load_worldcup_sync_status()
        if status:
            return WorldCupSyncStatus(**status).model_dump(mode="json")
        if SYNC_STATUS_FILE.exists():
            return json.loads(SYNC_STATUS_FILE.read_text(encoding="utf-8"))
        return WorldCupSyncStatus().model_dump(mode="json")

    def _save_sync_run(self, started_at: datetime, result: WorldCupSyncResult) -> None:
        finished_at = datetime.now(timezone.utc)
        self.repository.save_worldcup_sync_run(
            source=SOURCE,
            started_at=started_at,
            finished_at=finished_at,
            status=result.status,
            fetched_count=result.fetched_count,
            parsed_count=result.parsed_count,
            inserted_count=result.inserted_count,
            updated_count=result.updated_count,
            error_message=result.error_message,
            raw_snapshot_dir=result.raw_snapshot_dir,
        )
        payload = WorldCupSyncStatus(
            last_success_at=finished_at if result.status in {"success", "partial"} else None,
            last_failed_at=finished_at if result.status == "failed" else None,
            last_status=result.status,
            source=SOURCE,
            fetched_count=result.fetched_count,
            parsed_count=result.parsed_count,
            inserted_count=result.inserted_count,
            updated_count=result.updated_count,
            error_message=result.error_message,
            raw_snapshot_dir=result.raw_snapshot_dir,
        ).model_dump(mode="json")
        WORLD_CUP_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(SYNC_STATUS_FILE, payload)


def normalize_bing_run(run: BingKnowledgeRun) -> dict[str, list[dict[str, Any]]]:
    raw_dir = Path(run.manifest.get("raw_dir", ""))
    schedule_file = raw_dir / "sportsdetails.html"
    bracket_file = raw_dir / "bracket.html"
    schedule_hash = _file_hash(schedule_file)
    bracket_hash = _file_hash(bracket_file)
    bracket_by_id = {row.get("match_id"): row for row in run.records.get("bracket", []) if row.get("match_id")}
    matches: dict[str, dict[str, Any]] = {}
    for row in run.records.get("matches", []):
        match_id = row["match_id"]
        bracket = bracket_by_id.get(match_id, {})
        warnings: list[str] = []
        kickoff_label = row.get("kickoff_label") or bracket.get("date_label")
        kickoff_time = _parse_kickoff_time(row.get("date_label"), row.get("kickoff_label"))
        if not kickoff_time and row.get("status") != "final":
            warnings.append("kickoff_time_unparsed")
        home_team_id = _normalize_team_id(row.get("home_name"), row.get("home_team_id"))
        away_team_id = _normalize_team_id(row.get("away_name"), row.get("away_team_id"))
        winner_name = row.get("winner_name") or bracket.get("winner_name")
        winner_team_id = _normalize_team_id(winner_name, None) if winner_name else None
        match = WorldCupMatch(
            match_id=match_id,
            stage=row.get("stage") or bracket.get("round") or "",
            group_name=row.get("group"),
            kickoff_time=kickoff_time,
            kickoff_label=kickoff_label,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            winner_team_id=winner_team_id,
            home_team_raw=row.get("home_name"),
            away_team_raw=row.get("away_name"),
            winner_team_raw=winner_name,
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            home_penalty=bracket.get("home_penalty_score"),
            away_penalty=bracket.get("away_penalty_score"),
            status="complete" if row.get("status") == "final" else "scheduled",
            next_match_id=bracket.get("next_match_id"),
            source=SOURCE,
            source_url=row.get("source_url") or row.get("detail_url") or run.source_url,
            raw_html_file=str(schedule_file),
            raw_content_hash=schedule_hash or _hash_text(row.get("raw_label", "")),
            parser_version=PARSER_VERSION,
            schema_version=MATCH_SCHEMA_VERSION,
            fetched_at=_parse_dt(row.get("fetched_at")) or run.fetched_at,
            parse_warnings=warnings,
            metadata={
                "stage_label": row.get("stage_label"),
                "venue_id": row.get("venue_id"),
                "home_sport_radar_id": row.get("home_sport_radar_id"),
                "away_sport_radar_id": row.get("away_sport_radar_id"),
                "bracket_raw_html_file": str(bracket_file) if bracket else "",
                "bracket_raw_content_hash": bracket_hash if bracket else "",
            },
        ).model_dump(mode="json")
        matches[match_id] = match

    for row in run.records.get("bracket", []):
        match_id = row.get("match_id")
        if not match_id or match_id in matches:
            continue
        warnings = ["schedule_card_missing"]
        kickoff_time = _parse_kickoff_time(row.get("date_label"), row.get("time_label"))
        matches[match_id] = WorldCupMatch(
            match_id=match_id,
            stage=row.get("round") or "",
            group_name=None,
            kickoff_time=kickoff_time,
            kickoff_label=" ".join([str(row.get("date_label") or ""), str(row.get("time_label") or "")]).strip(),
            home_team_id=_normalize_team_id(row.get("home_name"), None),
            away_team_id=_normalize_team_id(row.get("away_name"), None),
            winner_team_id=_normalize_team_id(row.get("winner_name"), None) if row.get("winner_name") else None,
            home_team_raw=row.get("home_name"),
            away_team_raw=row.get("away_name"),
            winner_team_raw=row.get("winner_name"),
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            home_penalty=row.get("home_penalty_score"),
            away_penalty=row.get("away_penalty_score"),
            status="complete" if row.get("status") == "final" else "scheduled",
            next_match_id=row.get("next_match_id"),
            source=SOURCE,
            source_url=row.get("source_url") or run.source_url,
            raw_html_file=str(bracket_file),
            raw_content_hash=bracket_hash or row.get("raw_html_ref") or "",
            parser_version=PARSER_VERSION,
            schema_version=MATCH_SCHEMA_VERSION,
            fetched_at=run.fetched_at,
            parse_warnings=warnings,
            metadata={"round_label": row.get("round_label")},
        ).model_dump(mode="json")

    team_rows = normalize_teams(list(matches.values()), run.records.get("teams", []))
    standing_rows = normalize_standings(run.records.get("standings", []), run, bracket_hash)
    return {
        "matches": sorted(matches.values(), key=lambda item: (item.get("kickoff_time") or "", item["match_id"])),
        "teams": team_rows,
        "standings": standing_rows,
    }


def normalize_teams(matches: list[dict[str, Any]], source_teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for row in source_teams:
        team_id = _normalize_team_id(row.get("name"), row.get("team_id"))
        if team_id and not _is_placeholder_id(team_id):
            teams[team_id] = {
                "team_id": team_id,
                "name_en": _TEAM_EN.get(team_id),
                "name_zh": row.get("name"),
                "fifa_code": team_id if len(team_id) == 3 else None,
                "aliases": sorted(set([row.get("name"), team_id, *(_TEAM_ALIASES.get(team_id, []))]) - {None, ""}),
                "flag_code": team_id.lower() if len(team_id) == 3 else None,
            }
    for match in matches:
        for side in ("home", "away", "winner"):
            team_id = match.get(f"{side}_team_id")
            raw = match.get(f"{side}_team_raw")
            if team_id and raw and not _is_placeholder_id(team_id):
                teams.setdefault(
                    team_id,
                    {
                        "team_id": team_id,
                        "name_en": _TEAM_EN.get(team_id),
                        "name_zh": raw,
                        "fifa_code": team_id if len(team_id) == 3 else None,
                        "aliases": sorted(set([raw, team_id, *(_TEAM_ALIASES.get(team_id, []))]) - {None, ""}),
                        "flag_code": team_id.lower() if len(team_id) == 3 else None,
                    },
                )
    return sorted(teams.values(), key=lambda item: item["team_id"])


def normalize_standings(rows: list[dict[str, Any]], run: BingKnowledgeRun, raw_hash: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        team_name = row.get("team_name") or row.get("team_name_raw")
        group_name = row.get("group") or row.get("group_name")
        team_id = _normalize_team_id(team_name, row.get("team_id"))
        stable = f"{group_name}:{team_id or team_name}"
        payload = {
            "id": "standing:" + hashlib.sha1(stable.encode("utf-8")).hexdigest(),
            "group_name": group_name,
            "team_id": team_id,
            "team_name_raw": team_name or "",
            "played": row.get("played"),
            "won": row.get("won"),
            "drawn": row.get("drawn"),
            "lost": row.get("lost"),
            "goals_for": row.get("goals_for"),
            "goals_against": row.get("goals_against"),
            "goal_difference": row.get("goal_difference"),
            "points": row.get("points"),
            "source": SOURCE,
            "source_url": row.get("source_url") or run.source_url,
            "raw_content_hash": raw_hash or row.get("raw_html_ref") or "",
            "parser_version": PARSER_VERSION,
            "schema_version": STANDING_SCHEMA_VERSION,
            "fetched_at": run.fetched_at.isoformat(),
        }
        normalized.append(payload)
    return normalized


def _filter_matches(
    rows: list[dict[str, Any]],
    date_from: str | None,
    date_to: str | None,
    status: str | None,
    stage: str | None,
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        kickoff = row.get("kickoff_time")
        if date_from and kickoff and str(kickoff)[:10] < date_from:
            continue
        if date_to and kickoff and str(kickoff)[:10] > date_to:
            continue
        if status and row.get("status") != status.lower():
            continue
        if stage and row.get("stage") != stage:
            continue
        result.append(row)
    return result


def _parse_kickoff_time(date_label: str | None, kickoff_label: str | None) -> datetime | None:
    text = " ".join([date_label or "", kickoff_label or ""])
    timed_match = re.search(r"(\d{1,2})月(\d{1,2})日.*?(\d{1,2}):(\d{2})", text)
    if timed_match:
        month, day, hour, minute = [int(part) for part in timed_match.groups()]
        return datetime(2026, month, day, hour, minute, tzinfo=CHINA_TZ)
    date_match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if not date_match:
        return None
    month, day = [int(part) for part in date_match.groups()]
    return datetime(2026, month, day, 0, 0, tzinfo=CHINA_TZ)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _filter_player_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_categories = {"进球数", "助攻", "黄牌", "红牌"}
    return [
        row
        for row in rows
        if row.get("category") in allowed_categories
        and row.get("player_name")
        and row.get("value") is not None
    ]


def _normalize_team_id(name: str | None, fallback: str | None) -> str | None:
    if fallback and fallback.startswith("SportRadar_"):
        fallback = None
    if fallback and _is_placeholder_id(fallback):
        return fallback
    if name:
        clean = name.strip()
        if _is_placeholder_id(clean):
            return clean
        mapped = _TEAM_ID_BY_ALIAS.get(clean.casefold())
        if mapped:
            return mapped
        ascii_key = re.sub(r"[^A-Za-z0-9]+", "", clean.upper())
        if ascii_key:
            return ascii_key[:12]
        return "BING_" + hashlib.sha1(clean.encode("utf-8")).hexdigest()[:8].upper()
    return fallback


def _is_placeholder_id(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[WL]\d+", value.strip()))


_TEAM_EN = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "ALG": "Algeria",
    "BEL": "Belgium",
    "BIH": "Bosnia and Herzegovina",
    "BRA": "Brazil",
    "CAN": "Canada",
    "CIV": "Cote d'Ivoire",
    "COD": "DR Congo",
    "COL": "Colombia",
    "CPV": "Cape Verde",
    "CRO": "Croatia",
    "CUW": "Curacao",
    "CZE": "Czechia",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ENG": "England",
    "FRA": "France",
    "GER": "Germany",
    "GHA": "Ghana",
    "HAI": "Haiti",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "JOR": "Jordan",
    "JPN": "Japan",
    "KOR": "South Korea",
    "KSA": "Saudi Arabia",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "NED": "Netherlands",
    "NOR": "Norway",
    "NZL": "New Zealand",
    "PAR": "Paraguay",
    "PAN": "Panama",
    "POR": "Portugal",
    "QAT": "Qatar",
    "RSA": "South Africa",
    "SCO": "Scotland",
    "SEN": "Senegal",
    "ESP": "Spain",
    "SUI": "Switzerland",
    "SWE": "Sweden",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "URU": "Uruguay",
    "USA": "United States",
    "UZB": "Uzbekistan",
}

_TEAM_ALIASES = {
    "USA": ["United States", "U.S.", "US", "美国"],
    "KOR": ["South Korea", "Korea Republic", "韩国"],
    "RSA": ["South Africa", "南非"],
    "KSA": ["Saudi Arabia", "沙特阿拉伯"],
    "NED": ["Netherlands", "Holland", "荷兰"],
}

_TEAM_ZH = {
    "\u6fb3\u5927\u5229\u4e9a": "AUS",
    "\u57c3\u53ca": "EGY",
    "\u963f\u6839\u5ef7": "ARG",
    "\u963f\u5c14\u53ca\u5229\u4e9a": "ALG",
    "\u4f5b\u5f97\u89d2": "CPV",
    "\u6ce2\u9ed1": "BIH",
    "\u54e5\u4f26\u6bd4\u4e9a": "COL",
    "\u514b\u7f57\u5730\u4e9a": "CRO",
    "\u5e93\u62c9\u7d22\u5c9b": "CUW",
    "\u52a0\u7eb3": "GHA",
    "\u52a0\u62ff\u5927": "CAN",
    "\u6469\u6d1b\u54e5": "MAR",
    "\u5df4\u62c9\u572d": "PAR",
    "\u6cd5\u56fd": "FRA",
    "\u5df4\u897f": "BRA",
    "\u5df4\u62ff\u9a6c": "PAN",
    "\u632a\u5a01": "NOR",
    "\u58a8\u897f\u54e5": "MEX",
    "\u82f1\u683c\u5170": "ENG",
    "\u8461\u8404\u7259": "POR",
    "\u897f\u73ed\u7259": "ESP",
    "\u7f8e\u56fd": "USA",
    "\u6bd4\u5229\u65f6": "BEL",
    "\u745e\u58eb": "SUI",
    "\u5fb7\u56fd": "GER",
    "\u8377\u5170": "NED",
    "\u745e\u5178": "SWE",
    "\u65e5\u672c": "JPN",
    "\u6377\u514b": "CZE",
    "\u4e4c\u62c9\u572d": "URU",
    "\u4e4c\u5179\u522b\u514b\u65af\u5766": "UZB",
    "\u65b0\u897f\u5170": "NZL",
    "\u571f\u8033\u5176": "TUR",
    "\u97e9\u56fd": "KOR",
    "\u5357\u975e": "RSA",
    "\u6c99\u7279\u963f\u62c9\u4f2f": "KSA",
    "\u4f0a\u6717": "IRN",
    "\u4f0a\u62c9\u514b": "IRQ",
    "\u82cf\u683c\u5170": "SCO",
    "\u6d77\u5730": "HAI",
    "\u5361\u5854\u5c14": "QAT",
    "\u5965\u5730\u5229": "AUT",
    "\u5384\u74dc\u591a\u5c14": "ECU",
    "\u521a\u679c\u6c11\u4e3b\u5171\u548c\u56fd": "COD",
    "\u7a81\u5c3c\u65af": "TUN",
    "\u7ea6\u65e6": "JOR",
    "\u8c61\u7259\u6d77\u5cb8": "CIV",
    "\u585e\u5185\u52a0\u5c14": "SEN",
}


def _build_team_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for name, team_id in _TEAM_ZH.items():
        index[name.casefold()] = team_id
    for team_id, name in _TEAM_EN.items():
        index[team_id.casefold()] = team_id
        index[name.casefold()] = team_id
    for team_id, aliases in _TEAM_ALIASES.items():
        for alias in aliases:
            index[alias.casefold()] = team_id
    return index


_TEAM_ID_BY_ALIAS = _build_team_alias_index()
