"""小组赛积分排序。"""

import numpy as np

from wcpa.schemas.match import Match, MatchResult
from wcpa.schemas.tournament import GroupStanding, GroupStandingRow


def compute_group_standings(
    group: str,
    team_ids: list[str],
    results: list[MatchResult],
    rng: np.random.Generator,
    match_map: dict[str, Match] | None = None,
    tiebreakers: list[str] | None = None,
) -> GroupStanding:
    """计算小组积分排名。

    排序优先级: 积分 → 净胜球 → 进球数 → 随机兜底 (可复现)。
    MVP 跳过相互战绩 (head_to_head)。

    Args:
        group: 组名 (A/B/C/D)。
        team_ids: 该组所有球队 ID。
        results: 该组所有比赛结果。
        rng: 随机数生成器 (用于 tiebreaker 兜底)。
        match_map: ``{match_id: Match}`` 映射，用于获取 home/away team_id。
                   MatchResult schema 不含 team_id 字段，必须通过此映射查找。
        tiebreakers: 排序规则列表 (MVP 仅用前 4 项)。
    """
    if tiebreakers is None:
        tiebreakers = ["points", "goal_difference", "goals_for", "seed"]

    # 初始化每队统计
    stats: dict[str, dict] = {
        tid: {
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
        }
        for tid in team_ids
    }

    # 遍历比赛结果
    for r in results:
        # MatchResult 不含 team_id，通过 match_map 查找
        if match_map and r.match_id in match_map:
            m = match_map[r.match_id]
            h, a = m.home_team_id, m.away_team_id
        else:
            continue

        if h not in stats or a not in stats:
            continue

        stats[h]["played"] += 1
        stats[a]["played"] += 1
        stats[h]["goals_for"] += r.home_score
        stats[h]["goals_against"] += r.away_score
        stats[a]["goals_for"] += r.away_score
        stats[a]["goals_against"] += r.home_score

        if r.home_score > r.away_score:
            stats[h]["won"] += 1
            stats[h]["points"] += 3
            stats[a]["lost"] += 1
        elif r.away_score > r.home_score:
            stats[a]["won"] += 1
            stats[a]["points"] += 3
            stats[h]["lost"] += 1
        else:
            stats[h]["drawn"] += 1
            stats[a]["drawn"] += 1
            stats[h]["points"] += 1
            stats[a]["points"] += 1

    # 计算净胜球
    for tid in team_ids:
        stats[tid]["goal_difference"] = (
            stats[tid]["goals_for"] - stats[tid]["goals_against"]
        )

    # 排序: 积分 → 净胜球 → 进球数 → 随机兜底
    def sort_key(tid: str):
        s = stats[tid]
        return (
            -s["points"],
            -s["goal_difference"],
            -s["goals_for"],
            -rng.random(),
        )

    sorted_teams = sorted(team_ids, key=sort_key)

    rows = []
    for rank, tid in enumerate(sorted_teams, 1):
        s = stats[tid]
        rows.append(
            GroupStandingRow(
                team_id=tid,
                played=s["played"],
                won=s["won"],
                drawn=s["drawn"],
                lost=s["lost"],
                goals_for=s["goals_for"],
                goals_against=s["goals_against"],
                goal_difference=s["goal_difference"],
                points=s["points"],
                rank=rank,
            )
        )

    return GroupStanding(group=group, rows=rows)
