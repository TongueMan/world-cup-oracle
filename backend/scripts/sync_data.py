"""Collect external source snapshots without mutating prediction outputs."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.data.sources.web_collectors import WebCollector


def main():
    repo = PostgresRepository()
    snapshots = WebCollector().collect_all()
    for snapshot in snapshots:
        repo.save_source_snapshot(
            snapshot.source_key,
            snapshot.url,
            snapshot.status.status,
            snapshot.status.credibility,
            snapshot.raw,
            snapshot.status.message,
        )
        print(f"{snapshot.source_key}: {snapshot.status.status} - {snapshot.status.message}")


if __name__ == "__main__":
    main()
