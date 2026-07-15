"""Build a Markdown report from the latest stage-aware artifact."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.api.deps import get_prediction_artifact
from wcpa.prediction_report import attach_and_cache_report
from wcpa.shared.paths import REPORTS_DIR


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("anchor_positional", nargs="?", help="Stage anchor to build.")
    parser.add_argument("--anchor", default=None, help="Stage anchor to build.")
    args = parser.parse_args()
    anchor = args.anchor or args.anchor_positional or "current"
    artifact = get_prediction_artifact(strict=True, anchor=anchor)
    if artifact is None:
        print(f"ERROR: No verified published prediction found for anchor={anchor}")
        sys.exit(1)
    try:
        artifact = attach_and_cache_report(artifact)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    report = artifact.prediction_report
    if report is None:
        print("ERROR: Report generation failed")
        sys.exit(1)

    lines = [f"# {report.headline}", "", report.summary, ""]
    for section in report.sections:
        lines.extend([f"## {section.title}", "", section.body, ""])
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        lines.append("")
    if report.caveats:
        lines.extend(["## 边界说明", ""])
        for caveat in report.caveats:
            lines.append(f"- {caveat}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"prediction-report-{anchor}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
