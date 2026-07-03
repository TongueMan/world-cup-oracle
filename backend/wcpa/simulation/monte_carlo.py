"""蒙特卡洛模拟 — MVP 基础版。

运行 N 次完整赛事模拟，统计冠军频率作为冠军概率分布。
"""

from collections import Counter

import numpy as np

from wcpa.schemas.team import Team
from wcpa.schemas.match import Match, MatchResult
from wcpa.prediction.match_predictor import MatchPredictor
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
