"""预测流水线集成测试。"""
from wcpa.simulation.tournament_simulator import TournamentSimulator


def test_full_pipeline():
    """从 fixture 到冠军输出的完整流程。"""
    sim = TournamentSimulator(seed=42, mode="professional")
    artifact = sim.run()

    # 冠军存在
    assert artifact.champion_team_id is not None
    assert artifact.runner_up_team_id is not None

    # 小组排名完整
    assert len(artifact.group_standings) == 4  # 4 组
    for gs in artifact.group_standings:
        assert len(gs.rows) == 4  # 每组 4 队
        for i, row in enumerate(gs.rows):
            assert row.rank == i + 1

    # bracket 完整
    assert artifact.bracket is not None
    qf = [s for s in artifact.bracket.slots if s.round == "QF"]
    sf = [s for s in artifact.bracket.slots if s.round == "SF"]
    final = [s for s in artifact.bracket.slots if s.round == "Final"]
    assert len(qf) == 4
    assert len(sf) == 2
    assert len(final) == 1

    # 所有淘汰赛都有 winner
    for s in artifact.bracket.slots:
        assert s.winner_team_id is not None, f"{s.match_id} has no winner"

    # Final 的 winner 是冠军
    final_slot = final[0]
    assert final_slot.winner_team_id == artifact.champion_team_id

    # 比赛预测总数 = 24 小组 + 7 淘汰赛 = 31
    assert len(artifact.match_predictions) == 31


def test_reproducibility():
    """固定 seed 两次运行结果一致。"""
    sim1 = TournamentSimulator(seed=42)
    sim2 = TournamentSimulator(seed=42)

    a1 = sim1.run()
    a2 = sim2.run()

    assert a1.champion_team_id == a2.champion_team_id
    assert a1.runner_up_team_id == a2.runner_up_team_id

    # 比分一致
    for p1, p2 in zip(a1.match_predictions, a2.match_predictions):
        assert p1.predicted_score == p2.predicted_score
        assert p1.winner_team_id == p2.winner_team_id


def test_different_seeds_different_results():
    """不同 seed 应大概率产生不同结果。"""
    a1 = TournamentSimulator(seed=42).run()
    a2 = TournamentSimulator(seed=999).run()

    # 至少有些比赛比分不同
    diff_count = sum(1 for p1, p2 in zip(a1.match_predictions, a2.match_predictions)
                    if p1.predicted_score != p2.predicted_score)
    assert diff_count > 0, "Different seeds should produce different results"


def test_no_empty_advancement():
    """不断轮、不空晋级。"""
    artifact = TournamentSimulator(seed=42).run()

    # 所有淘汰赛 slot 都应有两队
    for s in artifact.bracket.slots:
        assert s.home_team_id is not None, f"{s.match_id}: home_team_id is None"
        assert s.away_team_id is not None, f"{s.match_id}: away_team_id is None"
