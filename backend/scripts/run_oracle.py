"""Run the full World Cup Oracle engine."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.simulation.oracle_tournament import OracleTournamentEngine
from wcpa.data.real_dataset import DataUnavailableError


def main():
    parser = argparse.ArgumentParser(description="Run full World Cup Oracle prediction")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", default="balanced")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo fixture expansion. Not valid for production predictions.",
    )
    args = parser.parse_args()

    engine = OracleTournamentEngine(seed=args.seed, mode=args.mode)
    try:
        artifact = engine.run_and_save(
            precompute_agents=not args.skip_agents,
            strict=not args.demo,
        )
    except DataUnavailableError as exc:
        print("Oracle prediction blocked: real data is unavailable.")
        print(exc.report.model_dump_json(indent=2))
        raise SystemExit(2) from exc
    print("Oracle prediction complete")
    print(f"Champion: {artifact.champion_team_id}")
    print(f"Runner-up: {artifact.runner_up_team_id}")
    print(f"Groups: {len(artifact.group_standings)}")
    print(f"Matches: {len(artifact.match_predictions)}")
    print(f"Agent debates: {len(artifact.debate_transcripts)}")


if __name__ == "__main__":
    main()
