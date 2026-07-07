"""Data coverage audit utilities for the local dataset and PostgreSQL store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.shared.paths import PROJECT_ROOT


CORE_TABLES = [
    "worldcup_matches",
    "worldcup_teams",
    "worldcup_standings",
    "venues",
    "match_venues",
    "match_environment_features",
    "bing_knowledge_records",
    "source_snapshots",
    "agent_workflow_runs",
    "agent_workflow_steps",
    "data_historical_matches",
    "data_team_squads",
    "data_injury_suspension_reports",
    "data_odds_snapshots",
    "data_team_form_snapshots",
    "staging_open_source_records",
]


@dataclass(frozen=True)
class FileMetric:
    path: str
    exists: bool
    record_count: int | None = None
    file_count: int | None = None
    bytes: int | None = None
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "path": self.path,
            "exists": self.exists,
            "record_count": self.record_count,
            "file_count": self.file_count,
            "bytes": self.bytes,
        }
        if self.detail:
            payload["detail"] = self.detail
        return {key: value for key, value in payload.items() if value is not None}


def collect_data_health_snapshot(
    repository: PostgresRepository | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    repo = repository or PostgresRepository()
    local_metrics = _collect_local_metrics(project_root)
    database_counts = repo.load_table_counts(CORE_TABLES) if repo.enabled else {}
    missing_domains = _missing_domains(local_metrics, database_counts)
    summary = {
        "local_metric_count": len(local_metrics),
        "database_table_count": len(database_counts),
        "missing_domain_count": len(missing_domains),
        "critical_missing_domains": [
            item["domain"] for item in missing_domains if item.get("priority") == "P0"
        ],
    }
    return {
        "snapshot_type": "data_coverage",
        "status": "attention_required" if missing_domains else "ok",
        "summary": summary,
        "payload": {
            "local": [metric.to_dict() for metric in local_metrics],
            "database_counts": database_counts,
            "missing_domains": missing_domains,
        },
    }


def save_data_health_snapshot(
    repository: PostgresRepository | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    repo = repository or PostgresRepository()
    snapshot = collect_data_health_snapshot(repo, project_root)
    snapshot_id = repo.save_data_health_snapshot(
        snapshot_type=snapshot["snapshot_type"],
        status=snapshot["status"],
        summary=snapshot["summary"],
        payload=snapshot["payload"],
    )
    return {**snapshot, "snapshot_id": snapshot_id}


def _collect_local_metrics(project_root: Path) -> list[FileMetric]:
    targets = [
        "data/knowledge/bing/matches.jsonl",
        "data/knowledge/bing/bracket.jsonl",
        "data/knowledge/bing/standings.jsonl",
        "data/knowledge/bing/player_stats.jsonl",
        "data/knowledge/bing/teams.jsonl",
        "data/knowledge/bing/news.jsonl",
        "data/knowledge/worldcup/history.json",
        "data/knowledge/worldcup/matches.json",
        "data/knowledge/worldcup/standings.json",
        "data/knowledge/worldcup/teams.json",
        "data/normalized/matches.real.json",
        "data/normalized/teams.real.json",
        "data/seeds/venues_seed.json",
    ]
    metrics = [_file_metric(project_root, target) for target in targets]
    open_source = project_root / "开源数据"
    metrics.extend(_open_source_metrics(project_root, open_source))
    return metrics


def _file_metric(project_root: Path, relative: str) -> FileMetric:
    path = project_root / relative
    if not path.exists():
        return FileMetric(path=relative, exists=False)
    if path.suffix == ".jsonl":
        count = sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
        return FileMetric(path=relative, exists=True, record_count=count, bytes=path.stat().st_size)
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return FileMetric(
                path=relative,
                exists=True,
                bytes=path.stat().st_size,
                detail={"error": "json_decode_failed"},
            )
        if isinstance(data, list):
            return FileMetric(
                path=relative,
                exists=True,
                record_count=len(data),
                bytes=path.stat().st_size,
            )
        if isinstance(data, dict):
            detail = {
                key: len(value) if hasattr(value, "__len__") else type(value).__name__
                for key, value in data.items()
            }
            return FileMetric(
                path=relative,
                exists=True,
                record_count=_dict_primary_count(data),
                bytes=path.stat().st_size,
                detail=detail,
            )
    return FileMetric(path=relative, exists=True, bytes=path.stat().st_size)


def _dict_primary_count(data: dict[str, Any]) -> int | None:
    for key in ("matches", "teams", "standings", "editions", "finals"):
        value = data.get(key)
        if hasattr(value, "__len__"):
            return len(value)
    return None


def _open_source_metrics(project_root: Path, open_source: Path) -> list[FileMetric]:
    if not open_source.exists():
        return [FileMetric(path="开源数据", exists=False)]
    metrics: list[FileMetric] = []
    for child in sorted(open_source.iterdir(), key=lambda item: item.name):
        if child.is_dir():
            metrics.append(
                FileMetric(
                    path=str(child.relative_to(project_root)),
                    exists=True,
                    file_count=sum(1 for item in child.rglob("*") if item.is_file()),
                )
            )
    selected = {
        "开源数据/世界杯/worldcup-master": "worldcup_master",
        "开源数据/高阶事件战术数据/data/events": "tactical_events",
        "开源数据/高阶事件战术数据/data/lineups": "tactical_lineups",
        "开源数据/高阶事件战术数据/data/three-sixty": "tactical_three_sixty",
        "开源数据/历史赛果赔率数据/data/raw": "odds_raw",
        "开源数据/世界杯球场数据": "venue_open_data",
    }
    for relative, key in selected.items():
        path = project_root / relative
        metrics.append(
            FileMetric(
                path=relative,
                exists=path.exists(),
                file_count=sum(1 for item in path.rglob("*") if item.is_file()) if path.exists() else None,
                detail={"source_key": key},
            )
        )
    return metrics


def _missing_domains(local_metrics: list[FileMetric], database_counts: dict[str, int]) -> list[dict[str, str]]:
    by_path = {metric.path.replace("\\", "/"): metric for metric in local_metrics}
    missing: list[dict[str, str]] = []

    def add_if(local_path: str, table: str, domain: str, priority: str, reason: str) -> None:
        metric = by_path.get(local_path)
        local_has_data = bool(metric and metric.exists and ((metric.record_count or 0) > 0 or (metric.file_count or 0) > 0))
        db_has_data = database_counts.get(table, 0) > 0
        if local_has_data and not db_has_data:
            missing.append(
                {
                    "domain": domain,
                    "priority": priority,
                    "local_path": local_path,
                    "target_table": table,
                    "reason": reason,
                }
            )

    add_if(
        "data/knowledge/worldcup/history.json",
        "data_historical_matches",
        "historical_worldcup_matches",
        "P1",
        "本地有历史世界杯比赛，但数据库历史比赛表为空。",
    )
    add_if(
        "开源数据/世界杯/worldcup-master",
        "data_team_squads",
        "worldcup_squads",
        "P1",
        "本地有历届阵容文件，但数据库阵容表为空。",
    )
    add_if(
        "开源数据/历史赛果赔率数据/data/raw",
        "data_odds_snapshots",
        "historical_odds",
        "P1",
        "本地有赔率文件，但数据库赔率快照表为空。",
    )
    add_if(
        "data/knowledge/bing/news.jsonl",
        "data_injury_suspension_reports",
        "injury_suspension_news",
        "P0",
        "新闻/伤停信息未形成结构化数据，赛前预测必须降级表达。",
    )
    if database_counts.get("match_environment_features", 0) == 0:
        missing.append(
            {
                "domain": "match_environment_features",
                "priority": "P0",
                "local_path": "data/seeds/venues_seed.json",
                "target_table": "match_environment_features",
                "reason": "比赛环境特征表为空，草皮、屋顶、天气、海拔不能作为确定事实输出。",
            }
        )
    return missing

