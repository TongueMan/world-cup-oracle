"""赛事模拟编排器 — 串联完整预测流水线。

流程: 加载数据 → 构建特征 → 预测小组赛 → 小组排名 → 淘汰赛 bracket → 逐轮推进 → 组装 artifact
"""

from datetime import datetime, timezone

from wcpa.schemas.team import Team
from wcpa.schemas.match import Match, MatchResult
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.tournament import GroupStanding
from wcpa.schemas.artifact import TournamentPrediction, TeamFeatures
from wcpa.data.repositories.fixture_loader import (
    load_teams,
    load_matches,
)
from wcpa.features.feature_builder import build_features
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.simulation.group_standings import compute_group_standings
from wcpa.simulation.knockout_bracket import (
    generate_initial_bracket,
    advance_bracket,
)
from wcpa.shared.random_utils import create_rng, derive_rng
from wcpa.shared.paths import PREDICTIONS_DIR


class TournamentSimulator:
    """赛事模拟编排器。

    用 ``TournamentSimulator(seed=42).run()`` 运行完整预测流水线。
    """

    def __init__(self, seed: int = 42, mode: str = "professional"):
        self.seed = seed
        self.mode = mode
        self.rng = create_rng(seed)
        self.predictor = BaselineMatchPredictor()

    def run(self) -> TournamentPrediction:
        """运行完整预测流水线，返回 ``TournamentPrediction`` artifact。"""
        # 1. 加载数据
        teams = load_teams()
        matches = load_matches()

        team_map: dict[str, Team] = {t.team_id: t for t in teams}

        # 2. 构建特征
        features: dict[str, TeamFeatures] = build_features(teams)

        # 3. 预测小组赛
        match_predictions: list[MatchPrediction] = []
        match_results: list[MatchResult] = []

        # 按组分组
        groups: dict[str, list[Match]] = {}
        for m in matches:
            if m.stage == "group" and m.group:
                groups.setdefault(m.group, []).append(m)

        all_standings: list[GroupStanding] = []
        for group_name, group_matches in sorted(groups.items()):
            group_results: list[MatchResult] = []
            group_team_ids: set[str] = set()
            match_map: dict[str, Match] = {m.match_id: m for m in group_matches}

            for m in group_matches:
                home = team_map[m.home_team_id]
                away = team_map[m.away_team_id]

                pred_rng = derive_rng(self.rng, f"match_{m.match_id}")
                pred = self.predictor.predict(
                    m,
                    home,
                    away,
                    features[m.home_team_id],
                    features[m.away_team_id],
                    pred_rng,
                    allow_draw=True,
                    sample_result=True,
                )
                match_predictions.append(pred)

                hs, as_ = map(int, pred.predicted_score.split("-"))
                mr = MatchResult(
                    match_id=m.match_id,
                    home_score=hs,
                    away_score=as_,
                    winner_team_id=pred.winner_team_id,
                )
                match_results.append(mr)
                group_results.append(mr)
                group_team_ids.add(m.home_team_id)
                group_team_ids.add(m.away_team_id)

            # 计算小组排名
            standings_rng = derive_rng(self.rng, f"standings_{group_name}")
            standing = compute_group_standings(
                group_name,
                list(group_team_ids),
                group_results,
                standings_rng,
                match_map,
            )
            all_standings.append(standing)

        # 4. 生成淘汰赛 bracket
        bracket_rng = derive_rng(self.rng, "bracket")
        bracket = generate_initial_bracket(all_standings, bracket_rng)

        # 5. 逐轮推进淘汰赛
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

                match_rng = derive_rng(self.rng, f"match_{slot.match_id}")
                pred = self.predictor.predict(
                    m,
                    home,
                    away,
                    features[slot.home_team_id],
                    features[slot.away_team_id],
                    match_rng,
                    allow_draw=False,
                    sample_result=True,
                )
                match_predictions.append(pred)

                hs, as_ = map(int, pred.predicted_score.split("-"))
                mr = MatchResult(
                    match_id=slot.match_id,
                    home_score=hs,
                    away_score=as_,
                    winner_team_id=pred.winner_team_id,
                    went_to_penalties=(hs == as_),
                )
                match_results.append(mr)
                round_results[slot.match_id] = mr

            bracket = advance_bracket(bracket, round_name, round_results, bracket_rng)

        # 6. 获取四强 (SF 阶段的 4 支队伍)
        semifinalists: list[str] = []
        for slot in bracket.slots:
            if slot.round == "SF":
                if slot.home_team_id:
                    semifinalists.append(slot.home_team_id)
                if slot.away_team_id:
                    semifinalists.append(slot.away_team_id)

        # 7. 组装 artifact
        artifact = TournamentPrediction(
            edition="2026",
            seed=self.seed,
            mode=self.mode,
            artifact_version="6.0.0",
            config_hash="",
            generated_at=datetime.now(timezone.utc),
            group_standings=all_standings,
            bracket=bracket,
            match_predictions=match_predictions,
            match_results=[mr.model_dump() for mr in match_results],
            champion_team_id=bracket.champion_team_id,
            runner_up_team_id=bracket.runner_up_team_id,
            semifinalists=semifinalists,
            rational_champion=bracket.champion_team_id,
        )

        return artifact

    def run_and_save(self) -> TournamentPrediction:
        """运行预测并保存 artifact 到 ``outputs/predictions/`` 目录。"""
        artifact = self.run()

        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

        output_path = PREDICTIONS_DIR / "baseline-tournament-run.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(artifact.model_dump_json(indent=2))

        return artifact
