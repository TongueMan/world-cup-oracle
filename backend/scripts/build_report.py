"""从 artifact 生成 Markdown 报告。"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.shared.paths import PREDICTIONS_DIR, REPORTS_DIR
from wcpa.schemas.artifact import TournamentPrediction
from wcpa.report.report_generator import generate_report


def main():
    artifact_path = PREDICTIONS_DIR / "tournament-prediction.json"
    if not artifact_path.exists():
        print(f"ERROR: Artifact not found: {artifact_path}")
        sys.exit(1)

    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    artifact = TournamentPrediction(**data)
    report = generate_report(artifact)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "prediction-report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
