"""数据标准化脚本 — MVP: 队名标准化、字段校验。"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.shared.paths import NORMALIZED_DIR
from wcpa.schemas.team import Team
from wcpa.schemas.match import Match


def main():
    """MVP: 校验 normalized 数据是否符合 schema。"""
    teams_path = NORMALIZED_DIR / "teams.sample.json"
    matches_path = NORMALIZED_DIR / "matches.sample.json"

    if teams_path.exists():
        with open(teams_path, "r", encoding="utf-8") as f:
            teams_data = json.load(f)
        teams = [Team(**t) for t in teams_data]
        print(f"Validated {len(teams)} teams.")

    if matches_path.exists():
        with open(matches_path, "r", encoding="utf-8") as f:
            matches_data = json.load(f)
        matches = [Match(**m) for m in matches_data]
        print(f"Validated {len(matches)} matches.")

    print("\nData normalization complete (MVP: schema validation).")


if __name__ == "__main__":
    main()
