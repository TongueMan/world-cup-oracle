"""Validate the latest stage-aware prediction artifact."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.api.deps import _load_current_tournament_state
from wcpa.prediction_release import PredictionArtifactStore, validate_published_artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("anchor_positional", nargs="?", help="Stage anchor to validate.")
    parser.add_argument("--anchor", default=None, help="Stage anchor to validate.")
    args = parser.parse_args()
    anchor = args.anchor or args.anchor_positional or "current"
    store = PredictionArtifactStore()
    artifact = store.load_published(anchor) or store.load_candidate(anchor)
    if artifact is None:
        print(f"[FAIL] No stage-aware artifact found for anchor={anchor}")
        sys.exit(1)
    current_state = _load_current_tournament_state() if anchor == "current" else None
    reasons = validate_published_artifact(
        artifact,
        expected_anchor=anchor,
        current_state=current_state,
    )
    if anchor == "current" and current_state is None:
        reasons.append("current_tournament_state_unavailable")
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        print("[FAIL] Prediction is not available for public use")
        for reason in reasons:
            print(f"  - {reason}")
        sys.exit(1)
    print("[OK] Published prediction passed the public availability contract")
    print(f"  Artifact ID: {artifact.artifact_id}")
    print(f"  Anchor: {artifact.current_tournament_state.requested_anchor if artifact.current_tournament_state else anchor}")
    print(f"  Status: {artifact.publication_status}")
    print(f"  Simulations: {artifact.simulation_count}")
    print(f"  Match predictions: {len(artifact.match_predictions)}")
    print(f"  Champion probabilities: {len(artifact.champion_probabilities)}")
    print(f"  Report: {artifact.prediction_report.report_id if artifact.prediction_report else 'missing'}")


if __name__ == "__main__":
    main()
