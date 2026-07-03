"""淘汰赛 bracket 生成与推进。

MVP 赛制: 4 组 × 4 队 → 每组 top2 = 8 队 → QF(4场) → SF(2场) → Final(1场)
"""

import numpy as np

from wcpa.schemas.tournament import GroupStanding, KnockoutSlot, Bracket
from wcpa.schemas.match import MatchResult


def generate_initial_bracket(
    group_standings: list[GroupStanding],
    rng: np.random.Generator,
) -> Bracket:
    """从小组排名生成 8 强对阵 (QF)。

    对阵规则（交叉）::

        QF1: A1 vs B2
        QF2: B1 vs A2
        QF3: C1 vs D2
        QF4: D1 vs C2

        SF1: QF_W1 vs QF_W2
        SF2: QF_W3 vs QF_W4

        Final: SF_W1 vs SF_W2
    """
    standings_map = {gs.group: gs for gs in group_standings}

    def get_team(group: str, rank: int) -> str:
        gs = standings_map[group]
        return gs.rows[rank - 1].team_id

    qf_slots = [
        KnockoutSlot(
            round="QF",
            match_id="K-QF-001",
            home_team_id=get_team("A", 1),
            away_team_id=get_team("B", 2),
            home_source="GroupA_1",
            away_source="GroupB_2",
        ),
        KnockoutSlot(
            round="QF",
            match_id="K-QF-002",
            home_team_id=get_team("B", 1),
            away_team_id=get_team("A", 2),
            home_source="GroupB_1",
            away_source="GroupA_2",
        ),
        KnockoutSlot(
            round="QF",
            match_id="K-QF-003",
            home_team_id=get_team("C", 1),
            away_team_id=get_team("D", 2),
            home_source="GroupC_1",
            away_source="GroupD_2",
        ),
        KnockoutSlot(
            round="QF",
            match_id="K-QF-004",
            home_team_id=get_team("D", 1),
            away_team_id=get_team("C", 2),
            home_source="GroupD_1",
            away_source="GroupC_2",
        ),
    ]

    sf_slots = [
        KnockoutSlot(
            round="SF",
            match_id="K-SF-001",
            home_source="QF_W1",
            away_source="QF_W2",
        ),
        KnockoutSlot(
            round="SF",
            match_id="K-SF-002",
            home_source="QF_W3",
            away_source="QF_W4",
        ),
    ]

    final_slot = KnockoutSlot(
        round="Final",
        match_id="K-F-001",
        home_source="SF_W1",
        away_source="SF_W2",
    )

    return Bracket(slots=qf_slots + sf_slots + [final_slot])


def advance_bracket(
    bracket: Bracket,
    round_name: str,
    results: dict[str, MatchResult],
    rng: np.random.Generator,
) -> Bracket:
    """根据本轮结果推进 bracket 到下一轮。

    Args:
        bracket: 当前 bracket。
        round_name: 刚完成的轮次 (QF/SF/Final)。
        results: 本轮所有比赛的 ``{match_id: MatchResult}`` 映射。
        rng: 随机数生成器 (保留接口一致性)。
    """
    all_slots = list(bracket.slots)

    # 1. 更新本轮 slots 的比分和胜者
    for i, slot in enumerate(all_slots):
        if slot.round == round_name and slot.match_id in results:
            r = results[slot.match_id]
            all_slots[i] = slot.model_copy(
                update={
                    "home_score": r.home_score,
                    "away_score": r.away_score,
                    "winner_team_id": r.winner_team_id,
                    "went_to_penalties": r.went_to_penalties,
                }
            )

    # 2. 构建胜者映射: "{round}_W{n}" -> winner_team_id
    current_slots = [s for s in all_slots if s.round == round_name]
    winners_map: dict[str, str | None] = {}
    for idx, cs in enumerate(current_slots):
        source_key = f"{round_name}_W{idx + 1}"
        winners_map[source_key] = cs.winner_team_id

    # 3. 确定下一轮
    next_round = {"QF": "SF", "SF": "Final"}.get(round_name)

    if next_round is None:
        # Final 已完成 — 设置冠军和亚军
        final_slot = next(s for s in all_slots if s.round == "Final")
        champion = final_slot.winner_team_id
        runner_up = None
        if champion and final_slot.home_team_id and final_slot.away_team_id:
            runner_up = (
                final_slot.away_team_id
                if champion == final_slot.home_team_id
                else final_slot.home_team_id
            )
        return Bracket(
            slots=all_slots,
            champion_team_id=champion,
            runner_up_team_id=runner_up,
        )

    # 4. 填充下一轮的队伍
    for i, slot in enumerate(all_slots):
        if slot.round != next_round:
            continue
        home_filled = winners_map.get(slot.home_source)
        away_filled = winners_map.get(slot.away_source)
        if home_filled is not None or away_filled is not None:
            all_slots[i] = slot.model_copy(
                update={
                    "home_team_id": home_filled or slot.home_team_id,
                    "away_team_id": away_filled or slot.away_team_id,
                }
            )

    return Bracket(slots=all_slots)
