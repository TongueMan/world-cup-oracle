"""Optional background scheduler for WorldCup data synchronization."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from wcpa.shared.env import env_bool, env_int
from wcpa.worldcup.service import WorldCupDataService


class WorldCupSyncScheduler:
    def __init__(self) -> None:
        self.enabled = env_bool("WCPA_ENABLE_WORLDCUP_SCHEDULER", False)
        self.interval_seconds = max(300, env_int("WCPA_WORLDCUP_SYNC_INTERVAL_SECONDS", 3600))
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(WorldCupDataService().sync_worldcup_data)
            except Exception as exc:
                print(f"[worldcup-sync] {datetime.now(timezone.utc).isoformat()} failed: {exc}")
            await asyncio.sleep(self.interval_seconds)


scheduler = WorldCupSyncScheduler()
