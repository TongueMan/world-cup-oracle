"""Monte Carlo simulation conditioned on the synchronized tournament state."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from wcpa.prediction.match_predictor import MatchPredictor
from wcpa.schemas.artifact import ChampionProbability, TournamentState
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import PredictionContext
from wcpa.schemas.team import Team
from wcpa.simulation.tournament_state import CHAMPIONSHIP_ROUNDS, is_complete, is_concrete_team, normalize_stage, resolve_winner


def run_conditional_monte_carlo(
    teams: list[Team],
    schedule: list[dict[str, Any]],
    state: TournamentState,
    predictor: MatchPredictor,
    features: dict,
    n_sims: int = 10_000,
    seed: int = 42,
    prediction_contexts: dict[str, PredictionContext] | None = None,
) -> list[ChampionProbability]:
    """Simulate only unresolved official knockout slots from ``state``."""

    if n_sims < 1:
        raise ValueError("n_sims must be at least 1")
    if state.active_round == "group":
        return []

    rows = [_normalize_row(row) for row in schedule]
    knockout = [row for row in rows if row["stage"] in CHAMPIONSHIP_ROUNDS]
    team_map = {team.team_id: team for team in teams}
    root_rng = np.random.default_rng(seed)
    prediction_cache = {}
    champion_counts: Counter[str] = Counter()
    eliminators: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    encounters: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    valid_simulations = 0

    incoming: dict[str, list[str]] = defaultdict(list)
    for row in knockout:
        if row.get("next_match_id"):
            incoming[str(row["next_match_id"])].append(row["match_id"])
    for values in incoming.values():
        values.sort()

    completed_winners = {
        row["match_id"]: resolve_winner(row)
        for row in knockout
        if is_complete(row) and resolve_winner(row)
    }

    def prediction_for(match_id: str, stage: str, home_id: str, away_id: str):
        key = (home_id, away_id)
        if key not in prediction_cache:
            prediction_cache[key] = predictor.predict(
                Match(
                    match_id=match_id,
                    stage=stage,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    source="conditional_monte_carlo",
                ),
                team_map.get(home_id), team_map.get(away_id),
                features.get(home_id), features.get(away_id),
                np.random.default_rng(seed), allow_draw=False,
                context=(
                    prediction_contexts.get(f"{match_id}:{home_id}:{away_id}")
                    or prediction_contexts.get(match_id)
                    if prediction_contexts
                    else None
                ),
            )
        return prediction_cache[key]

    ordered = sorted(knockout, key=lambda row: (CHAMPIONSHIP_ROUNDS.index(row["stage"]), row["match_id"]))
    for _ in range(n_sims):
        sim_rng = np.random.default_rng(root_rng.integers(0, 2**63 - 1))
        winners = dict(completed_winners)
        failed = False
        for row in ordered:
            home_id, away_id = _resolve_participants(row, winners, incoming)
            if is_complete(row):
                continue
            if not home_id or not away_id or home_id not in team_map or away_id not in team_map:
                failed = True
                break

            encounters[home_id][(away_id, row["stage"])] += 1
            encounters[away_id][(home_id, row["stage"])] += 1
            prediction = prediction_for(row["match_id"], row["stage"], home_id, away_id)
            winner = home_id if sim_rng.random() < prediction.home_advancement_prob else away_id
            loser = away_id if winner == home_id else home_id
            winners[row["match_id"]] = winner
            eliminators[loser][(winner, row["stage"])] += 1

        if failed:
            continue
        final = next((row for row in ordered if row["stage"] == "Final"), None)
        champion = winners.get(final["match_id"]) if final else None
        if champion:
            champion_counts[champion] += 1
            valid_simulations += 1

    if not valid_simulations:
        return []

    alive = set(state.alive_teams)
    results: list[ChampionProbability] = []
    for team in teams:
        team_id = team.team_id
        probability = champion_counts[team_id] / valid_simulations if team_id in alive else 0.0
        eliminator_rows = [
            {
                "opponent_team_id": opponent,
                "round": stage,
                "elimination_probability": count / valid_simulations,
            }
            for (opponent, stage), count in eliminators[team_id].most_common(3)
        ]
        matchup_rows = []
        for (opponent, stage), count in encounters[team_id].most_common(3):
            elimination_count = eliminators[team_id][(opponent, stage)]
            matchup_rows.append(
                {
                    "opponent_team_id": opponent,
                    "round": stage,
                    "encounter_probability": count / valid_simulations,
                    "elimination_probability": elimination_count / valid_simulations,
                }
            )
        common = eliminator_rows[0]["opponent_team_id"] if eliminator_rows else ""
        key = matchup_rows[0] if matchup_rows else None
        results.append(
            ChampionProbability(
                team_id=team_id,
                probability=probability,
                most_common_eliminator=common,
                potential_key_match=(
                    f"{team_id} vs {key['opponent_team_id']} ({key['round']})" if key else ""
                ),
                simulation_count=valid_simulations,
                probability_source="conditional_monte_carlo",
                is_alive=team_id in alive,
                eliminator_stats=eliminator_rows,
                key_matchups=matchup_rows,
            )
        )
    return sorted(results, key=lambda item: (-item.probability, item.team_id))


def _resolve_participants(
    row: dict[str, Any],
    winners: dict[str, str],
    incoming: dict[str, list[str]],
) -> tuple[str | None, str | None]:
    home = str(row.get("home_team_id") or "") if is_concrete_team(row.get("home_team_id")) else None
    away = str(row.get("away_team_id") or "") if is_concrete_team(row.get("away_team_id")) else None
    sources = [row.get("home_source_match_id"), row.get("away_source_match_id")]
    fallback = incoming.get(row["match_id"], [])
    if not home:
        source = str(sources[0]) if sources[0] else (fallback[0] if fallback else "")
        home = winners.get(source)
    if not away:
        source = str(sources[1]) if sources[1] else (fallback[1] if len(fallback) > 1 else "")
        away = winners.get(source)
    return home, away


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["stage"] = normalize_stage(row.get("stage"))
    result["match_id"] = str(row.get("match_id") or "")
    return result
