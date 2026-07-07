"""Import local open-source football datasets into staged/fact PostgreSQL tables."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.shared.paths import PROJECT_ROOT
from wcpa.worldcup.environment import WorldCupEnvironmentService


@dataclass(frozen=True)
class ImportResult:
    dataset: str
    loaded: int = 0
    skipped: int = 0
    status: str = "ok"
    errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "loaded": self.loaded,
            "skipped": self.skipped,
            "status": self.status,
            "errors": self.errors or [],
        }


def import_all_foundational_data(
    repository: PostgresRepository | None = None,
    project_root: Path = PROJECT_ROOT,
    odds_limit: int | None = None,
    staging_limit_per_dataset: int | None = None,
) -> dict[str, Any]:
    repo = repository or PostgresRepository()
    results = [
        ensure_match_environment_features(repo),
        import_historical_worldcup_matches(repo, project_root),
        import_worldcup_squads(repo, project_root),
        import_team_form_snapshots(repo),
        import_historical_odds(repo, project_root, limit=odds_limit),
        stage_open_source_file_inventory(repo, project_root, limit_per_dataset=staging_limit_per_dataset),
    ]
    return {
        "status": "ok" if all(result.status == "ok" for result in results) else "partial",
        "results": [result.to_dict() for result in results],
    }


def ensure_match_environment_features(repository: PostgresRepository) -> ImportResult:
    service = WorldCupEnvironmentService(repository)
    venue_report = service.sync_venues()
    mapping_report = service.sync_match_venues()
    feature_report = service.build_match_environment_features()
    return ImportResult(
        dataset="match_environment_features",
        loaded=feature_report.loaded_count,
        skipped=feature_report.skipped_count,
        status="ok" if feature_report.loaded_count else "partial",
        errors=(venue_report.errors or []) + (mapping_report.errors or []) + (feature_report.errors or []),
    )


def import_historical_worldcup_matches(
    repository: PostgresRepository,
    project_root: Path = PROJECT_ROOT,
) -> ImportResult:
    path = project_root / "data" / "knowledge" / "worldcup" / "history.json"
    if not path.exists():
        return ImportResult("historical_worldcup_matches", status="missing", errors=[str(path)])
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for match in payload.get("matches") or []:
        rows.append(
            {
                "competition": "FIFA World Cup",
                "edition_year": match.get("year"),
                "match_date": match.get("date"),
                "stage": match.get("stage") or match.get("round") or "",
                "home_team": match.get("home_team") or "",
                "away_team": match.get("away_team") or "",
                "home_score": match.get("home_score"),
                "away_score": match.get("away_score"),
                "winner_team": match.get("winner_team") or "",
                "source": match.get("source") or "openfootball_worldcup_json",
                "source_url": match.get("source_url") or "",
                "source_path": str(path.relative_to(project_root)),
                "confidence": 0.9,
                "data_status": "published",
                "payload": match,
            }
        )
    result = repository.upsert_data_historical_matches(rows)
    return ImportResult("historical_worldcup_matches", loaded=result.get("loaded", 0))


def import_worldcup_squads(
    repository: PostgresRepository,
    project_root: Path = PROJECT_ROOT,
) -> ImportResult:
    base = project_root / "开源数据" / "世界杯" / "worldcup-master"
    if not base.exists():
        return ImportResult("worldcup_squads", status="missing", errors=[str(base)])
    rows: list[dict[str, Any]] = []
    skipped = 0
    for path in sorted((base).rglob("squads/*.txt")):
        year = _edition_year(path)
        team_name = _team_name_from_squad_file(path)
        if year is None or not team_name:
            skipped += 1
            continue
        parsed = _parse_squad_file(path, year, team_name, project_root)
        rows.extend(parsed)
    result = repository.upsert_data_team_squads(rows)
    return ImportResult("worldcup_squads", loaded=result.get("loaded", 0), skipped=skipped)


def import_team_form_snapshots(repository: PostgresRepository) -> ImportResult:
    matches = repository.load_worldcup_matches()
    stats: dict[str, dict[str, Any]] = {}
    for match in matches:
        if match.get("status") not in {"complete", "final"}:
            continue
        home_id = match.get("home_team_id") or match.get("home_team_raw")
        away_id = match.get("away_team_id") or match.get("away_team_raw")
        if not home_id or not away_id:
            continue
        home_score = match.get("home_score")
        away_score = match.get("away_score")
        if home_score is None or away_score is None:
            continue
        _record_team_match(stats, home_id, match.get("home_team_raw") or home_id, home_score, away_score)
        _record_team_match(stats, away_id, match.get("away_team_raw") or away_id, away_score, home_score)
    rows = []
    today = date.today().isoformat()
    for team_id, row in stats.items():
        played = row["played"]
        if not played:
            continue
        rows.append(
            {
                "team_id": team_id,
                "team_name": row["team_name"],
                "snapshot_date": today,
                "source": "worldcup_matches_completed_results",
                "source_url": "",
                "matches_considered": played,
                "form_score": round(row["points"] / (played * 3), 4),
                "attack_score": round(min(1.0, row["goals_for"] / max(1, played * 3)), 4),
                "defense_score": round(max(0.0, 1 - row["goals_against"] / max(1, played * 3)), 4),
                "confidence": 0.75,
                "data_status": "published",
                "payload": row,
            }
        )
    result = repository.upsert_data_team_form_snapshots(rows)
    return ImportResult("team_form_snapshots", loaded=result.get("loaded", 0))


def import_historical_odds(
    repository: PostgresRepository,
    project_root: Path = PROJECT_ROOT,
    limit: int | None = None,
) -> ImportResult:
    path = (
        project_root
        / "开源数据"
        / "历史赛果赔率数据"
        / "data"
        / "processed"
        / "football_data_matches_normalized.csv"
    )
    if not path.exists():
        return ImportResult("historical_odds", status="missing", errors=[str(path)])
    loaded = 0
    batch: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            for bookmaker, keys in _odds_key_groups().items():
                home = _float_or_none(row.get(keys[0]))
                draw = _float_or_none(row.get(keys[1]))
                away = _float_or_none(row.get(keys[2]))
                if home is None or draw is None or away is None:
                    continue
                batch.append(
                    {
                        "match_id": "",
                        "market": "1x2_historical_league",
                        "bookmaker": bookmaker,
                        "home_price": home,
                        "draw_price": draw,
                        "away_price": away,
                        **_implied_probs(home, draw, away),
                        "source": row.get("source") or "football-data.co.uk",
                        "source_url": row.get("source_url") or "",
                        "observed_at": row.get("fetched_at") or datetime.now(timezone.utc),
                        "confidence": 0.65,
                        "data_status": "staged",
                        "source_match_key": row.get("match_key") or _hash_json(row),
                        "payload": row,
                    }
                )
                loaded += 1
                if limit is not None and loaded >= limit:
                    break
            if len(batch) >= 1000:
                repository.upsert_data_odds_snapshots(batch)
                batch = []
            if limit is not None and loaded >= limit:
                break
    if batch:
        repository.upsert_data_odds_snapshots(batch)
    return ImportResult("historical_odds", loaded=loaded)


def stage_open_source_file_inventory(
    repository: PostgresRepository,
    project_root: Path = PROJECT_ROOT,
    limit_per_dataset: int | None = None,
) -> ImportResult:
    datasets = {
        "tactical_events": project_root / "开源数据" / "高阶事件战术数据" / "data" / "events",
        "tactical_lineups": project_root / "开源数据" / "高阶事件战术数据" / "data" / "lineups",
        "tactical_three_sixty": project_root / "开源数据" / "高阶事件战术数据" / "data" / "three-sixty",
        "odds_raw_files": project_root / "开源数据" / "历史赛果赔率数据" / "data" / "raw",
    }
    rows: list[dict[str, Any]] = []
    skipped = 0
    for dataset_key, root in datasets.items():
        if not root.exists():
            skipped += 1
            continue
        count = 0
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = str(path.relative_to(project_root))
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "source_path": relative,
                    "record_key": _file_record_key(path),
                    "record_type": path.suffix.lstrip(".") or "file",
                    "quality_status": "inventory_only",
                    "payload": {
                        "bytes": path.stat().st_size,
                        "suffix": path.suffix,
                        "relative_path": relative,
                    },
                }
            )
            count += 1
            if limit_per_dataset is not None and count >= limit_per_dataset:
                break
    for index in range(0, len(rows), 1000):
        repository.upsert_staging_open_source_records(rows[index : index + 1000])
    return ImportResult("open_source_file_inventory", loaded=len(rows), skipped=skipped)


def _parse_squad_file(path: Path, year: int, fallback_team: str, project_root: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    team_name = fallback_team
    header = re.search(r"#\s*([^#\n(]+?)\s*(?:\([A-Z]{2,4}\))?\s*$", text, re.M)
    if header:
        team_name = header.group(1).strip()
    rows = []
    for line in text.splitlines():
        match = re.match(r"\s*-\s+([A-Z]{2})\s+(.+?)(?:\s+##\s*(.*))?$", line)
        if not match:
            continue
        position = match.group(1).strip()
        player_name = re.sub(r"\s+", " ", match.group(2)).strip()
        meta = (match.group(3) or "").strip()
        shirt_number = ""
        club = ""
        if meta:
            parts = [part.strip() for part in meta.split(",", 1)]
            shirt_number = parts[0]
            club = parts[1] if len(parts) > 1 else ""
        rows.append(
            {
                "competition": "FIFA World Cup",
                "edition_year": year,
                "team_name": team_name,
                "player_name": player_name,
                "shirt_number": shirt_number,
                "position": position,
                "source": "openfootball_worldcup_master",
                "source_url": "https://github.com/openfootball/worldcup",
                "source_path": str(path.relative_to(project_root)),
                "confidence": 0.75,
                "data_status": "staged",
                "payload": {"club": club, "raw_meta": meta},
            }
        )
    return rows


def _edition_year(path: Path) -> int | None:
    for parent in path.parents:
        match = re.match(r"(\d{4})--", parent.name)
        if match:
            return int(match.group(1))
    return None


def _team_name_from_squad_file(path: Path) -> str:
    stem = path.stem
    if "-" in stem:
        return stem.split("-", 1)[1].replace("-", " ").title()
    return stem.replace("-", " ").title()


def _record_team_match(stats: dict[str, dict[str, Any]], team_id: str, team_name: str, goals_for: int, goals_against: int) -> None:
    row = stats.setdefault(
        team_id,
        {"team_name": team_name, "played": 0, "points": 0, "goals_for": 0, "goals_against": 0},
    )
    row["played"] += 1
    row["goals_for"] += int(goals_for)
    row["goals_against"] += int(goals_against)
    if goals_for > goals_against:
        row["points"] += 3
    elif goals_for == goals_against:
        row["points"] += 1


def _odds_key_groups() -> dict[str, tuple[str, str, str]]:
    return {
        "bet365": ("odds_home_b365", "odds_draw_b365", "odds_away_b365"),
        "average": ("odds_home_avg", "odds_draw_avg", "odds_away_avg"),
        "maximum": ("odds_home_max", "odds_draw_max", "odds_away_max"),
    }


def _float_or_none(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _implied_probs(home: float, draw: float, away: float) -> dict[str, float]:
    inv = [1 / home, 1 / draw, 1 / away]
    total = sum(inv)
    home_prob = round(inv[0] / total, 6)
    draw_prob = round(inv[1] / total, 6)
    return {
        "implied_home_prob": home_prob,
        "implied_draw_prob": draw_prob,
        "implied_away_prob": round(1.0 - home_prob - draw_prob, 6),
    }


def _file_record_key(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha1(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")).hexdigest()


def _hash_json(payload: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
