"""淘汰赛 bracket 测试。"""
import pytest
import numpy as np
from wcpa.simulation.knockout_bracket import generate_initial_bracket, advance_bracket
from wcpa.schemas.tournament import GroupStanding, GroupStandingRow
from wcpa.schemas.match import MatchResult


def _make_standings():
    """创建 4 组 mock 排名。"""
    standings = []
    for g, teams in [("A", ["BRA", "ARG"]), ("B", ["FRA", "ENG"]), ("C", ["GER", "ESP"]), ("D", ["POR", "NED"])]:
        rows = [
            GroupStandingRow(team_id=teams[0], points=9, rank=1, played=3, won=3, goals_for=6, goals_against=1, goal_difference=5),
            GroupStandingRow(team_id=teams[1], points=6, rank=2, played=3, won=2, goals_for=4, goals_against=3, goal_difference=1),
        ]
        standings.append(GroupStanding(group=g, rows=rows))
    return standings


def test_bracket_generation():
    """8 队 QF 对阵生成正确。"""
    rng = np.random.default_rng(42)
    standings = _make_standings()
    bracket = generate_initial_bracket(standings, rng)

    qf_slots = [s for s in bracket.slots if s.round == "QF"]
    assert len(qf_slots) == 4

    # A1 vs B2, B1 vs A2, C1 vs D2, D1 vs C2
    assert qf_slots[0].home_team_id == "BRA"  # A1
    assert qf_slots[0].away_team_id == "ENG"  # B2
    assert qf_slots[1].home_team_id == "FRA"  # B1
    assert qf_slots[1].away_team_id == "ARG"  # A2
    assert qf_slots[2].home_team_id == "GER"  # C1
    assert qf_slots[2].away_team_id == "NED"  # D2
    assert qf_slots[3].home_team_id == "POR"  # D1
    assert qf_slots[3].away_team_id == "ESP"  # C2


def test_bracket_has_sf_and_final():
    """bracket 包含 SF 和 Final 槽位。"""
    rng = np.random.default_rng(42)
    bracket = generate_initial_bracket(_make_standings(), rng)

    sf_slots = [s for s in bracket.slots if s.round == "SF"]
    final_slots = [s for s in bracket.slots if s.round == "Final"]
    assert len(sf_slots) == 2
    assert len(final_slots) == 1

    # SF 和 Final 初始为 None
    for s in sf_slots + final_slots:
        assert s.home_team_id is None
        assert s.away_team_id is None


def test_bracket_advancement():
    """bracket 推进正确。"""
    rng = np.random.default_rng(42)
    bracket = generate_initial_bracket(_make_standings(), rng)

    # QF 结果: 全部 home 胜
    qf_results = {
        "K-QF-001": MatchResult(match_id="K-QF-001",
                               home_score=2, away_score=1, winner_team_id="BRA"),
        "K-QF-002": MatchResult(match_id="K-QF-002",
                               home_score=1, away_score=0, winner_team_id="FRA"),
        "K-QF-003": MatchResult(match_id="K-QF-003",
                               home_score=3, away_score=1, winner_team_id="GER"),
        "K-QF-004": MatchResult(match_id="K-QF-004",
                               home_score=2, away_score=2, winner_team_id="POR",
                               went_to_penalties=True),
    }

    bracket = advance_bracket(bracket, "QF", qf_results, rng)

    # SF 应填充
    sf_slots = [s for s in bracket.slots if s.round == "SF"]
    assert sf_slots[0].home_team_id == "BRA"  # QF W1
    assert sf_slots[0].away_team_id == "FRA"  # QF W2
    assert sf_slots[1].home_team_id == "GER"  # QF W3
    assert sf_slots[1].away_team_id == "POR"  # QF W4


def test_bracket_champion():
    """从 QF 到 Final 产生冠军。"""
    rng = np.random.default_rng(42)
    bracket = generate_initial_bracket(_make_standings(), rng)

    # QF
    qf_results = {
        "K-QF-001": MatchResult(match_id="K-QF-001",
                               home_score=2, away_score=1, winner_team_id="BRA"),
        "K-QF-002": MatchResult(match_id="K-QF-002",
                               home_score=1, away_score=0, winner_team_id="FRA"),
        "K-QF-003": MatchResult(match_id="K-QF-003",
                               home_score=3, away_score=1, winner_team_id="GER"),
        "K-QF-004": MatchResult(match_id="K-QF-004",
                               home_score=1, away_score=0, winner_team_id="POR"),
    }
    bracket = advance_bracket(bracket, "QF", qf_results, rng)

    # SF
    sf_results = {
        "K-SF-001": MatchResult(match_id="K-SF-001",
                               home_score=2, away_score=1, winner_team_id="BRA"),
        "K-SF-002": MatchResult(match_id="K-SF-002",
                               home_score=1, away_score=0, winner_team_id="GER"),
    }
    bracket = advance_bracket(bracket, "SF", sf_results, rng)

    # Final
    final_results = {
        "K-F-001": MatchResult(match_id="K-F-001",
                             home_score=1, away_score=0, winner_team_id="BRA"),
    }
    bracket = advance_bracket(bracket, "Final", final_results, rng)

    assert bracket.champion_team_id == "BRA"
    assert bracket.runner_up_team_id == "GER"
