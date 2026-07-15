"""Data readiness and Bing knowledge status routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.data.sources.bing_worldcup import (
    BingSportsWorldCupCollector,
    load_bing_manifest,
)
from wcpa.schemas.artifact import DataQualityReport, DataSourceStatus

router = APIRouter()


@router.get("/database/status")
def get_database_status():
    return PostgresRepository().health()


@router.get("/status")
async def get_data_status():
    """Return Bing-only knowledge readiness status."""
    manifest = load_bing_manifest()
    fetched_live = False
    if manifest is None:
        run = BingSportsWorldCupCollector().collect()
        manifest = run.manifest
        fetched_live = True

    counts = manifest.get("counts", {})
    missing = list(manifest.get("missing", []))
    source_status = DataSourceStatus(
        source_key="bing_sports_worldcup",
        status="ok" if counts.get("matches", 0) else "data_unavailable",
        credibility="B",
        fetched_at=_parse_datetime(manifest.get("fetched_at")),
        records=int(counts.get("matches", 0) or 0),
        message=(
            f"Bing 单源知识库：比赛 {counts.get('matches', 0)}，"
            f"淘汰赛 {counts.get('bracket', 0)}，资讯 {counts.get('news', 0)}，"
            f"排名 {counts.get('standings', 0)}，统计 {counts.get('player_stats', 0)}。"
        ),
    )
    invalid_records = [
        {"dataset": key, "reason": "empty_or_incomplete", "count": counts.get(key, 0)}
        for key in ("matches", "bracket", "news", "standings", "player_stats")
        if counts.get(key, 0) == 0
    ]
    status = "ready" if not missing and not invalid_records else "invalid"
    if fetched_live:
        missing.append("knowledge_files_not_written_run_sync_real_data")
    report = DataQualityReport(
        status=status,
        strict=True,
        missing=missing,
        invalid_records=invalid_records,
        source_statuses=[source_status],
        message=(
            "Bing Sports 单源知识库已就绪。"
            if status == "ready"
            else "Bing Sports 单源知识库尚未完整；请运行同步任务或查看缺失项。"
        ),
    )
    return report.model_dump(mode="json") | {
        "primary_source": "bing_sports",
        "knowledge_manifest": manifest,
    }


def _parse_datetime(value: str | None):
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
