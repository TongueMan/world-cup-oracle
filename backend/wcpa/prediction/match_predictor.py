"""单场预测器：Protocol 接口 + 基线实现。"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np

from wcpa.schemas.match import Match
from wcpa.schemas.team import Team
from wcpa.schemas.artifact import TeamFeatures
from wcpa.schemas.prediction import MatchPrediction
from wcpa.prediction.score_model import generate_score
from wcpa.prediction.confidence import compute_confidence


class MatchPredictor(Protocol):
    """可替换的单场预测器接口。"""

    def predict(
        self,
        match: Match,
        home: Team,
        away: Team,
        home_features: TeamFeatures,
        away_features: TeamFeatures,
        rng: np.random.Generator,
        allow_draw: bool = True,
    ) -> MatchPrediction:
        ...


class BaselineMatchPredictor:
    """基线预测器：基于 team_strength + Poisson 比分生成。"""

    def __init__(
        self, weights: dict | None = None, score_config: dict | None = None
    ):
        if weights is None:
            from wcpa.shared.config_loader import load_config

            cfg = load_config("model-weights")
            self.weights = cfg["team_strength"]
            self.score_config = cfg["score_model"]
        else:
            self.weights = weights
            self.score_config = score_config or {}

    def _compute_probabilities(
        self, home_strength: float, away_strength: float
    ) -> tuple[float, float, float]:
        """用 logistic 函数估计胜平负概率。"""
        diff = home_strength - away_strength

        # 胜率
        home_win_prob = 1 / (1 + math.exp(-diff * 8))
        away_win_prob = 1 / (1 + math.exp(diff * 8))

        # 平局概率（实力差越小越大）
        draw_prob = (1 - home_win_prob - away_win_prob) * 0.5 + 0.15
        draw_prob = max(0.05, min(0.40, draw_prob))

        # 归一化
        total = home_win_prob + draw_prob + away_win_prob
        return home_win_prob / total, draw_prob / total, away_win_prob / total

    def _generate_reason_codes(
        self, home: TeamFeatures, away: TeamFeatures, home_win: bool
    ) -> list[str]:
        """从特征差异生成 reason_codes。"""
        codes: list[str] = []
        if abs(home.normalized_fifa_rank - away.normalized_fifa_rank) > 0.1:
            codes.append("ranking_gap")
        if abs(home.recent_form - away.recent_form) > 0.1:
            codes.append("recent_form")
        if abs(home.attack - away.attack) > 0.1:
            codes.append("attack_advantage")
        if abs(home.defense - away.defense) > 0.1:
            codes.append("defense_advantage")
        if abs(home.team_strength - away.team_strength) > 0.2:
            codes.append("strength_gap")
        return codes if codes else ["balanced_matchup"]

    def predict(
        self,
        match: Match,
        home: Team,
        away: Team,
        home_features: TeamFeatures,
        away_features: TeamFeatures,
        rng: np.random.Generator,
        allow_draw: bool = True,
    ) -> MatchPrediction:
        """预测单场比赛。"""
        # 1. 计算胜平负概率
        home_win_prob, draw_prob, away_win_prob = self._compute_probabilities(
            home_features.team_strength, away_features.team_strength
        )

        # 2. 生成比分
        home_score, away_score = generate_score(
            home_features, away_features, rng, self.score_config
        )

        # 3. 确定胜者
        if home_score > away_score:
            winner = match.home_team_id
        elif away_score > home_score:
            winner = match.away_team_id
        else:
            # 平局
            if allow_draw:
                winner = None
            else:
                # 淘汰赛：加时赛/点球
                from wcpa.shared.config_loader import load_config

                sim_cfg = load_config("simulation")
                penalty_home_prob = sim_cfg["knockout_tiebreaker"][
                    "penalty_home_win_prob"
                ]

                if rng.random() < penalty_home_prob:
                    winner = match.home_team_id
                    home_score += 1  # 加时/点球进球
                else:
                    winner = match.away_team_id
                    away_score += 1

        # 4. 计算置信度
        prob_max = max(home_win_prob, draw_prob, away_win_prob)
        strength_diff = (
            home_features.team_strength - away_features.team_strength
        )
        confidence = compute_confidence(abs(strength_diff), prob_max)

        # 5. 生成 reason_codes
        reason_codes = self._generate_reason_codes(
            home_features, away_features, winner == match.home_team_id
        )

        return MatchPrediction(
            match_id=match.match_id,
            home_win_prob=round(home_win_prob, 4),
            draw_prob=round(draw_prob, 4),
            away_win_prob=round(away_win_prob, 4),
            predicted_score=f"{home_score}-{away_score}",
            winner_team_id=winner,
            confidence=round(confidence, 4),
            upset_index=0.0,
            consensus_type="rational_lead",
            reason_codes=reason_codes,
        )
