"""小组积分排序测试。"""
import pytest
import numpy as np
from wcpa.simulation.group_standings import compute_group_standings
from wcpa.schemas.match import Match, MatchResult


def _build_match_map(specs):
    """从 (match_id, home, away) 元组列表构建 match_map。

    MatchResult schema 不含 team_id 字段，必须通过 match_map 查找。
    """
    matches = [
        Match(match_id=mid, stage="group", group="X",
              home_team_id=home, away_team_id=away)
        for mid, home, away in specs
    ]
    return {m.match_id: m for m in matches}


def test_points_calculation():
    """积分: 胜3 平1 负0。"""
    match_map = _build_match_map([
        ("m1", "A", "B"),
        ("m2", "A", "C"),
        ("m3", "B", "C"),
    ])
    results = [
        MatchResult(match_id="m1", home_score=2, away_score=1, winner_team_id="A"),
        MatchResult(match_id="m2", home_score=0, away_score=0, winner_team_id=None),
        MatchResult(match_id="m3", home_score=1, away_score=3, winner_team_id="C"),
    ]
    rng = np.random.default_rng(42)
    standing = compute_group_standings("X", ["A", "B", "C"], results, rng, match_map=match_map)

    # A: 胜1 平1 = 4分, B: 负2 = 0分, C: 平1 胜1 = 4分
    a_row = next(r for r in standing.rows if r.team_id == "A")
    c_row = next(r for r in standing.rows if r.team_id == "C")
    b_row = next(r for r in standing.rows if r.team_id == "B")

    assert a_row.points == 4
    assert c_row.points == 4
    assert b_row.points == 0

    # A 和 C 同分(4)，A 净胜球 +1，C 净胜球 +2，C 应排前
    assert c_row.rank < a_row.rank
    # B 0 分排最后
    assert b_row.rank == 3


def test_goal_difference_tiebreaker():
    """同积分时按净胜球排序。"""
    match_map = _build_match_map([
        ("m1", "X", "Y"),
        ("m2", "Z", "W"),
    ])
    results = [
        MatchResult(match_id="m1", home_score=3, away_score=0, winner_team_id="X"),
        MatchResult(match_id="m2", home_score=1, away_score=0, winner_team_id="Z"),
    ]
    rng = np.random.default_rng(42)
    standing = compute_group_standings("G", ["X", "Y", "Z", "W"], results, rng, match_map=match_map)

    x_row = next(r for r in standing.rows if r.team_id == "X")
    z_row = next(r for r in standing.rows if r.team_id == "Z")
    # X 和 Z 都 3 分，X 净胜球 +3 > Z 净胜球 +1
    assert x_row.rank < z_row.rank


def test_goals_for_tiebreaker():
    """同积分同净胜球时按进球数排序。"""
    match_map = _build_match_map([
        ("m1", "P", "Q"),
        ("m2", "R", "S"),
    ])
    results = [
        MatchResult(match_id="m1", home_score=5, away_score=2, winner_team_id="P"),
        MatchResult(match_id="m2", home_score=3, away_score=0, winner_team_id="R"),
    ]
    rng = np.random.default_rng(42)
    standing = compute_group_standings("G", ["P", "Q", "R", "S"], results, rng, match_map=match_map)

    p_row = next(r for r in standing.rows if r.team_id == "P")
    r_row = next(r for r in standing.rows if r.team_id == "R")
    # P 和 R 都 3 分，净胜球都 +3，P 进 5 > R 进 3
    assert p_row.rank < r_row.rank


def test_seed_tiebreaker_stability():
    """同分同净胜球同进球数时，seed 兜底应稳定。"""
    match_map = _build_match_map([
        ("m1", "A", "B"),
        ("m2", "C", "D"),
    ])
    results = [
        MatchResult(match_id="m1", home_score=1, away_score=0, winner_team_id="A"),
        MatchResult(match_id="m2", home_score=1, away_score=0, winner_team_id="C"),
    ]
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)

    s1 = compute_group_standings("G", ["A", "B", "C", "D"], results, rng1, match_map=match_map)
    s2 = compute_group_standings("G", ["A", "B", "C", "D"], results, rng2, match_map=match_map)

    # 同 seed 应得相同结果
    assert [r.team_id for r in s1.rows] == [r.team_id for r in s2.rows]


def test_empty_results():
    """空比赛列表返回 0 场。"""
    rng = np.random.default_rng(42)
    standing = compute_group_standings("G", ["A", "B", "C", "D"], [], rng)

    for row in standing.rows:
        assert row.played == 0
        assert row.points == 0
