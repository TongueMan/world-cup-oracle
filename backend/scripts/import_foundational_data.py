"""Import foundational local data for Agent-grade match analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from wcpa.data.open_source_importer import import_all_foundational_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Import foundational World Cup Agent data.")
    parser.add_argument(
        "--odds-limit",
        type=int,
        default=None,
        help="Optional cap for historical odds rows. Omit for full import.",
    )
    parser.add_argument(
        "--staging-limit-per-dataset",
        type=int,
        default=None,
        help="Optional cap for open-source file inventory rows per dataset.",
    )
    args = parser.parse_args()
    result = import_all_foundational_data(
        odds_limit=args.odds_limit,
        staging_limit_per_dataset=args.staging_limit_per_dataset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

