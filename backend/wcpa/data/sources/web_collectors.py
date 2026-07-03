"""Production web collectors.

The formal data path is intentionally narrowed to the Bing Sports World Cup
page. Other sources can still exist in the repository for experiments, but
``WebCollector`` only returns Bing Sports snapshots.
"""

from __future__ import annotations

from datetime import datetime, timezone

from wcpa.data.sources.bing_worldcup import (
    BING_WORLD_CUP_URL,
    SourceSnapshot,
    BingSportsWorldCupCollector,
)
from wcpa.schemas.artifact import DataSourceStatus
from wcpa.shared.env import env_bool


BING_SCHEDULE_URL = BING_WORLD_CUP_URL


class WebCollector:
    """Compatibility wrapper around the Bing-only collector."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def collect_all(self) -> list[SourceSnapshot]:
        if not env_bool("WCPA_ENABLE_WEB_COLLECTORS", True):
            now = datetime.now(timezone.utc)
            return [
                SourceSnapshot(
                    source_key="bing_sports_worldcup",
                    url="disabled",
                    status=DataSourceStatus(
                        source_key="bing_sports_worldcup",
                        status="disabled",
                        credibility="D",
                        fetched_at=now,
                        records=0,
                        message="Bing Sports collector disabled.",
                    ),
                    raw={},
                )
            ]
        return BingSportsWorldCupCollector(timeout=self.timeout).collect().snapshots

    def fetch_bing(self) -> SourceSnapshot:
        return BingSportsWorldCupCollector(timeout=self.timeout).collect().snapshots[0]
