"""校验输出 artifact 符合 schema。"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.shared.paths import PREDICTIONS_DIR
from wcpa.schemas.artifact import TournamentPrediction


def main():
    artifact_path = PREDICTIONS_DIR / "tournament-prediction.json"
    if not artifact_path.exists():
        print(f"ERROR: Artifact not found: {artifact_path}")
        sys.exit(1)

    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        artifact = TournamentPrediction(**data)
        print("[OK] Artifact valid")
        print(f"  Edition: {artifact.edition}")
        print(f"  Seed: {artifact.seed}")
        print(f"  Champion: {artifact.champion_team_id}")
        print(f"  Match predictions: {len(artifact.match_predictions)}")
        print(f"  Group standings: {len(artifact.group_standings)}")
        print(f"  Bracket slots: {len(artifact.bracket.slots) if artifact.bracket else 0}")
    except Exception as e:
        print(f"[FAIL] Artifact invalid: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
