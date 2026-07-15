"""基于单场概率的锦标赛 Monte Carlo。"""

from collections import Counter, defaultdict

import numpy as np

from wcpa.schemas.artifact import ChampionProbability
from wcpa.schemas.team import Team
from wcpa.schemas.match import Match, MatchResult
from wcpa.schemas.prediction import MatchPrediction
from wcpa.prediction.match_predictor import MatchPredictor
from wcpa.prediction.poisson_model import sample_score_from_matrix, score_probability_matrix
from wcpa.simulation.group_standings import compute_group_standings
from wcpa.simulation.knockout_bracket import (
    generate_initial_bracket,
    advance_bracket,
)


def run_monte_carlo(
    teams: list[Team],
    matches: list[Match],
    predictor: MatchPredictor,
    features: dict,
    n_sims: int = 100,
    seed: int = 42,
) -> dict[str, float]:
    """运行蒙特卡洛模拟，返回冠军概率分布。

    Args:
        teams: 球队列表。
        matches: 小组赛比赛列表。
        predictor: 单场预测器。
        features: ``{team_id: TeamFeatures}`` 特征字典。
        n_sims: 模拟次数。
        seed: 随机种子。

    Returns:
        ``{team_id: champion_prob}`` 概率分布。
    """
    rng = np.random.default_rng(seed)
    champion_counts: Counter = Counter()

    # 获取分组
    groups: dict[str, set[str]] = {}
    for m in matches:
        if m.stage == "group" and m.group:
            groups.setdefault(m.group, set()).add(m.home_team_id)
            groups.setdefault(m.group, set()).add(m.away_team_id)

    team_map = {t.team_id: t for t in teams}

    for _sim_idx in range(n_sims):
        sim_rng = np.random.default_rng(rng.integers(0, 2**31))

        # 1. 预测小组赛
        all_standings = []
        for group_name, team_ids in sorted(groups.items()):
            group_matches = [m for m in matches if m.group == group_name]
            match_map = {m.match_id: m for m in group_matches}
            raw_results: list[MatchResult] = []
            for m in group_matches:
                home = team_map[m.home_team_id]
                away = team_map[m.away_team_id]
                pred = predictor.predict(
                    m,
                    home,
                    away,
                    features[m.home_team_id],
                    features[m.away_team_id],
                    sim_rng,
                    allow_draw=True,
                    sample_result=True,
                )
                hs, as_ = map(int, pred.predicted_score.split("-"))
                mr = MatchResult(
                    match_id=m.match_id,
                    home_score=hs,
                    away_score=as_,
                    winner_team_id=pred.winner_team_id,
                )
                raw_results.append(mr)

            standing = compute_group_standings(
                group_name, list(team_ids), raw_results, sim_rng, match_map
            )
            all_standings.append(standing)

        # 2. 生成淘汰赛 bracket
        bracket = generate_initial_bracket(all_standings, sim_rng)

        # 3. 逐轮推进
        for round_name in ["QF", "SF", "Final"]:
            round_slots = [s for s in bracket.slots if s.round == round_name]
            round_results: dict[str, MatchResult] = {}
            for slot in round_slots:
                if slot.home_team_id is None or slot.away_team_id is None:
                    continue
                home = team_map[slot.home_team_id]
                away = team_map[slot.away_team_id]
                m = Match(
                    match_id=slot.match_id,
                    stage=round_name,
                    home_team_id=slot.home_team_id,
                    away_team_id=slot.away_team_id,
                )
                pred = predictor.predict(
                    m,
                    home,
                    away,
                    features[slot.home_team_id],
                    features[slot.away_team_id],
                    sim_rng,
                    allow_draw=False,
                    sample_result=True,
                )
                hs, as_ = map(int, pred.predicted_score.split("-"))
                winner = pred.winner_team_id
                if winner is None:
                    winner = slot.home_team_id if hs > as_ else slot.away_team_id
                round_results[slot.match_id] = MatchResult(
                    match_id=slot.match_id,
                    home_score=hs,
                    away_score=as_,
                    winner_team_id=winner,
                    went_to_penalties=(hs == as_),
                )

            bracket = advance_bracket(bracket, round_name, round_results, sim_rng)

        if bracket.champion_team_id:
            champion_counts[bracket.champion_team_id] += 1

    # 计算概率
    total = sum(champion_counts.values())
    if total == 0:
        return {}
    return {
        team_id: count / total
        for team_id, count in champion_counts.most_common()
    }


def run_world_cup_monte_carlo(
    teams: list[Team],
    matches: list[Match],
    predictor: MatchPredictor,
    features: dict,
    n_sims: int = 1000,
    seed: int = 42,
) -> list[ChampionProbability]:
    """模拟 48 队世界杯路径并返回每支球队的逐轮概率。

    预测器只为同一潜在对阵计算一次概率，模拟阶段从缓存的比分分布抽样。
    这样既保证冠军概率由单场模型驱动，也避免重复构造昂贵的解释对象。
    """

    if n_sims < 1:
        raise ValueError("n_sims must be at least 1")

    team_map = {team.team_id: team for team in teams}
    group_matches: dict[str, list[Match]] = defaultdict(list)
    for match in matches:
        if match.stage == "group" and match.group:
            group_matches[match.group].append(match)
    if not group_matches:
        return []

    root_rng = np.random.default_rng(seed)
    champion_counts: Counter[str] = Counter()
    eliminators: dict[str, Counter[str]] = defaultdict(Counter)
    opponents: dict[str, Counter[str]] = defaultdict(Counter)
    prediction_cache: dict[tuple[str, str, bool], MatchPrediction] = {}
    matrix_cache: dict[tuple[float, float], np.ndarray] = {}

    def prediction_for(home_id: str, away_id: str, allow_draw: bool):
        key = (home_id, away_id, allow_draw)
        if key not in prediction_cache:
            prediction_cache[key] = predictor.predict(
                Match(
                    match_id=f"MC-{home_id}-{away_id}",
                    stage="group" if allow_draw else "knockout",
                    home_team_id=home_id,
                    away_team_id=away_id,
                    source="monte_carlo",
                ),
                team_map.get(home_id),
                team_map.get(away_id),
                features.get(home_id),
                features.get(away_id),
                np.random.default_rng(seed),
                allow_draw=allow_draw,
            )
        return prediction_cache[key]

    def sampled_result(match: Match, sim_rng: np.random.Generator, allow_draw: bool) -> MatchResult:
        actual = _actual_result(match)
        if actual is not None:
            return actual

        prediction = prediction_for(match.home_team_id, match.away_team_id, allow_draw)
        matrix_key = (
            round(float(prediction.expected_home_goals), 6),
            round(float(prediction.expected_away_goals), 6),
        )
        if matrix_key not in matrix_cache:
            matrix_cache[matrix_key] = score_probability_matrix(*matrix_key)
        home_score, away_score = sample_score_from_matrix(matrix_cache[matrix_key], sim_rng)

        if home_score > away_score:
            winner = match.home_team_id
        elif away_score > home_score:
            winner = match.away_team_id
        elif allow_draw:
            winner = None
        else:
            conditional_home = (
                prediction.extra_time_home_win_prob
                + prediction.extra_time_draw_prob * prediction.penalty_home_win_prob
            )
            conditional_away = (
                prediction.extra_time_away_win_prob
                + prediction.extra_time_draw_prob * prediction.penalty_away_win_prob
            )
            total = conditional_home + conditional_away
            conditional_home = conditional_home / total if total else 0.5
            winner = match.home_team_id if sim_rng.random() < conditional_home else match.away_team_id
        return MatchResult(
            match_id=match.match_id,
            home_score=home_score,
            away_score=away_score,
            winner_team_id=winner,
            went_to_extra_time=not allow_draw and home_score == away_score,
            went_to_penalties=not allow_draw and home_score == away_score,
            source="monte_carlo",
        )

    rounds = [("R32", 16), ("R16", 8), ("QF", 4), ("SF", 2), ("Final", 1)]

    for simulation_index in range(n_sims):
        sim_rng = np.random.default_rng(root_rng.integers(0, 2**63 - 1))
        standings = []
        for group_name, fixtures in sorted(group_matches.items()):
            team_ids = sorted(
                {match.home_team_id for match in fixtures}
                | {match.away_team_id for match in fixtures}
            )
            results = [sampled_result(match, sim_rng, True) for match in fixtures]
            standings.append(
                compute_group_standings(
                    group_name,
                    team_ids,
                    results,
                    sim_rng,
                    {match.match_id: match for match in fixtures},
                )
            )

        qualified = _qualified_teams(standings)
        if len(qualified) < 2:
            continue
        queue = list(qualified)

        for round_name, expected_match_count in rounds:
            match_count = min(expected_match_count, len(queue) // 2)
            if match_count < 1:
                break
            next_queue: list[str] = []
            pairings = [(queue[index], queue[-index - 1]) for index in range(match_count)]
            for match_index, (home_id, away_id) in enumerate(pairings, 1):
                opponents[home_id][away_id] += 1
                opponents[away_id][home_id] += 1
                result = sampled_result(
                    Match(
                        match_id=f"MC-{simulation_index}-{round_name}-{match_index}",
                        stage=round_name,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        source="monte_carlo",
                    ),
                    sim_rng,
                    False,
                )
                winner = result.winner_team_id or home_id
                loser = away_id if winner == home_id else home_id
                eliminators[loser][winner] += 1
                next_queue.append(winner)
            if round_name == "Final":
                champion_counts.update(next_queue)
            queue = next_queue

    valid_simulations = sum(champion_counts.values())
    if valid_simulations == 0:
        return []

    rows: list[ChampionProbability] = []
    for team in teams:
        team_id = team.team_id
        champion_probability = champion_counts[team_id] / valid_simulations
        common_eliminator = eliminators[team_id].most_common(1)
        common_opponent = opponents[team_id].most_common(1)
        rows.append(
            ChampionProbability(
                team_id=team_id,
                probability=champion_probability,
                most_common_eliminator=common_eliminator[0][0] if common_eliminator else "",
                potential_key_match=(
                    f"{team_id} vs {common_opponent[0][0]}" if common_opponent else ""
                ),
                simulation_count=valid_simulations,
                probability_source="monte_carlo",
            )
        )
    return sorted(rows, key=lambda item: (-item.probability, item.team_id))


def _qualified_teams(standings: list) -> list[str]:
    """48 队赛制：每组前二与 8 个成绩最好的第三名晋级。"""

    first_two: list[str] = []
    thirds = []
    for standing in standings:
        if len(standing.rows) < 3:
            continue
        first_two.extend([standing.rows[0].team_id, standing.rows[1].team_id])
        thirds.append(standing.rows[2])
    best_thirds = sorted(
        thirds,
        key=lambda row: (-row.points, -row.goal_difference, -row.goals_for, row.team_id),
    )[:8]
    return first_two + [row.team_id for row in best_thirds]


def _actual_result(match: Match) -> MatchResult | None:
    """将有完整比分的 final 比赛转换为锁定结果。"""

    if match.status != "final" or match.home_score is None or match.away_score is None:
        return None
    winner = match.winner_team_id
    if winner is None and match.home_score != match.away_score:
        winner = (
            match.home_team_id if match.home_score > match.away_score else match.away_team_id
        )
    return MatchResult(
        match_id=match.match_id,
        home_score=match.home_score,
        away_score=match.away_score,
        winner_team_id=winner,
        went_to_penalties=match.went_to_penalties,
        is_actual=True,
        source=match.source,
    )
