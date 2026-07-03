"""Sync WorldCup structured data from Bing Sports fragments."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.worldcup.service import WorldCupDataService


def main():
    service = WorldCupDataService()
    result = service.sync_worldcup_data()
    print(
        {
            "status": result.status,
            "fetched_count": result.fetched_count,
            "parsed_count": result.parsed_count,
            "inserted_count": result.inserted_count,
            "updated_count": result.updated_count,
            "raw_snapshot_dir": result.raw_snapshot_dir,
        }
    )


if __name__ == "__main__":
    main()
