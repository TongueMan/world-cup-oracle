"""Audit local/open-source data coverage against the PostgreSQL store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from wcpa.data.health import collect_data_health_snapshot, save_data_health_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit World Cup data coverage.")
    parser.add_argument("--save", action="store_true", help="Persist the snapshot to data_health_snapshots.")
    args = parser.parse_args()

    snapshot = save_data_health_snapshot() if args.save else collect_data_health_snapshot()
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
