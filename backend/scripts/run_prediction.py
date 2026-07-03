"""运行完整预测流水线。"""
import argparse
import sys
import os

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.simulation.tournament_simulator import TournamentSimulator


def main():
    parser = argparse.ArgumentParser(description="Run World Cup prediction pipeline")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--mode",
        type=str,
        default="balanced",
        choices=["professional", "balanced", "upset", "entertainment"],
        help="Prediction mode",
    )
    args = parser.parse_args()

    print(f"Running prediction with seed={args.seed}, mode={args.mode}...")
    sim = TournamentSimulator(seed=args.seed, mode=args.mode)
    artifact = sim.run_and_save()

    print(f"\n=== Prediction Complete ===")
    print(f"Champion: {artifact.champion_team_id}")
    print(f"Runner-up: {artifact.runner_up_team_id}")
    print(f"Semifinalists: {artifact.semifinalists}")
    print(f"Total predictions: {len(artifact.match_predictions)}")
    print(f"\nGroup Standings:")
    for gs in artifact.group_standings:
        teams = [f"{r.rank}.{r.team_id}({r.points}pts)" for r in gs.rows]
        print(f"  Group {gs.group}: {', '.join(teams)}")
    print(f"\nKnockout:")
    for slot in artifact.bracket.slots:
        home = slot.home_team_id or "TBD"
        away = slot.away_team_id or "TBD"
        score = f"{slot.home_score}-{slot.away_score}" if slot.home_score is not None else ""
        winner = f"-> {slot.winner_team_id}" if slot.winner_team_id else ""
        print(f"  {slot.round} {slot.match_id}: {home} {score} {away} {winner}")


if __name__ == "__main__":
    main()
