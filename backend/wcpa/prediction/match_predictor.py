"""可降级的多源融合单场预测器。"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np

from wcpa.features.team_strength import compute_team_strength
from wcpa.prediction.confidence import compute_confidence
from wcpa.prediction.evidence import (
    assess_data_grade,
    confidence_cap_for,
    degradation_assumptions,
)
from wcpa.prediction.market_model import aggregate_bookmaker_odds
from wcpa.prediction.poisson_model import (
    most_likely_score,
    outcome_probabilities,
    sample_score_from_matrix,
    score_probability_matrix,
    top_scorelines,
)
from wcpa.schemas.artifact import TeamFeatures
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import (
    MatchPrediction,
    PredictionContext,
    PredictionEvidence,
    ProbabilityAdjustment,
    ProbabilityComponent,
    ScorelineProbability,
)
from wcpa.schemas.team import Team
from wcpa.shared.config_loader import load_config


ProbabilityTriple = tuple[float, float, float]


class MatchPredictor(Protocol):
    """可替换的单场预测器接口。"""

    def predict(
        self,
        match: Match,
        home: Team | None,
        away: Team | None,
        home_features: TeamFeatures | None,
        away_features: TeamFeatures | None,
        rng: np.random.Generator,
        allow_draw: bool = True,
        context: PredictionContext | None = None,
        sample_result: bool = False,
    ) -> MatchPrediction:
        ...


class MultiSourceMatchPredictor:
    """融合市场、实力、进球、联网语义和中性先验的 V1 预测器。"""

    def __init__(
        self,
        weights: dict | None = None,
        score_config: dict | None = None,
    ):
        model_cfg = load_config("model-weights")
        simulation_cfg = load_config("simulation")
        self.weights = weights or model_cfg["team_strength"]
        self.score_config = score_config or model_cfg["score_model"]
        self.fusion_config = model_cfg.get("prediction_fusion", {})
        self.extra_time_factor = simulation_cfg["knockout_tiebreaker"].get(
            "extra_time_goal_expectation_factor", 1 / 3
        )

    @staticmethod
    def _normalize(values: tuple[float, float, float] | np.ndarray) -> ProbabilityTriple:
        array = np.maximum(np.array(values, dtype=float), 0.000001)
        array /= array.sum()
        return tuple(float(value) for value in array)

    @staticmethod
    def _rounded_probabilities(values: ProbabilityTriple) -> ProbabilityTriple:
        home = round(values[0], 4)
        draw = round(values[1], 4)
        away = round(1.0 - home - draw, 4)
        return home, draw, away

    def _strength_probabilities(
        self,
        home_strength: float,
        away_strength: float,
    ) -> ProbabilityTriple:
        diff = home_strength - away_strength
        home_raw = 1 / (1 + math.exp(-diff * 8))
        away_raw = 1 / (1 + math.exp(diff * 8))
        draw_raw = max(0.10, min(0.34, 0.30 * math.exp(-1.8 * abs(diff))))
        return self._normalize((home_raw, draw_raw, away_raw))

    @staticmethod
    def _neutral_features(team_id: str) -> TeamFeatures:
        return TeamFeatures(
            team_id=team_id,
            team_strength=0.5,
            normalized_fifa_rank=0.5,
            normalized_elo=0.5,
            recent_form=0.5,
            attack=0.65,
            defense=0.65,
            world_cup_experience=0.5,
            squad_health=0.5,
        )

    def _resolve_features(
        self,
        team: Team | None,
        features: TeamFeatures | None,
        team_id: str,
    ) -> tuple[TeamFeatures, bool]:
        if features is not None:
            return features, True
        if team is not None:
            return compute_team_strength(team, self.weights), True
        return self._neutral_features(team_id), False

    def _fusion_template(
        self,
        has_market: bool,
        has_structured: bool,
        has_semantic: bool,
    ) -> dict[str, float]:
        if has_market:
            scenario = "market_available"
            fallback = {"market": 0.40, "strength": 0.25, "goals": 0.20, "web_semantic": 0.15}
        elif has_structured:
            scenario = "structured_no_market"
            fallback = {"strength": 0.40, "goals": 0.25, "web_semantic": 0.25, "neutral_prior": 0.10}
        elif has_semantic:
            scenario = "weak_structured_web_strong"
            fallback = {"strength": 0.35, "web_semantic": 0.45, "neutral_prior": 0.20}
        else:
            scenario = "extreme_missing"
            fallback = {"strength": 0.35, "neutral_prior": 0.65}
        return dict(self.fusion_config.get("scenarios", {}).get(scenario, fallback))

    @staticmethod
    def _model_evidence(evidence_id: str, claim: str, field: str, confidence: float) -> PredictionEvidence:
        return PredictionEvidence(
            evidence_id=evidence_id,
            claim=claim,
            source_type="model_prior",
            source_name=field,
            freshness=1.0,
            confidence=confidence,
            supported_fields=[field],
            impact_summary="该模型分量已进入本场融合概率。",
            model_usage="model_input",
        )

    def _apply_adjustments(
        self,
        probabilities: ProbabilityTriple,
        adjustments: list[ProbabilityAdjustment],
        evidence: list[PredictionEvidence],
    ) -> tuple[ProbabilityTriple, list[ProbabilityAdjustment]]:
        evidence_map = {item.evidence_id: item for item in evidence}
        deltas = np.zeros(3, dtype=float)
        applied: list[ProbabilityAdjustment] = []
        for adjustment in adjustments:
            conflict_factor = 1.0
            if any(evidence_map.get(item) and evidence_map[item].conflicts for item in adjustment.evidence_ids):
                conflict_factor = 0.5
            scale = adjustment.confidence * conflict_factor
            deltas += np.array(
                [adjustment.home_delta, adjustment.draw_delta, adjustment.away_delta]
            ) * scale
            applied.append(adjustment)
        max_adjustment = float(self.fusion_config.get("max_total_adjustment", 0.12))
        deltas = np.clip(deltas, -max_adjustment, max_adjustment)
        adjusted = np.maximum(np.array(probabilities) + deltas, 0.000001)
        adjusted /= adjusted.sum()
        return tuple(float(value) for value in adjusted), applied

    @staticmethod
    def _agreement(components: list[dict], fused: ProbabilityTriple) -> float:
        if len(components) < 2:
            return 0.55
        distances = [
            float(np.abs(np.array(component["probabilities"]) - np.array(fused)).mean())
            for component in components
        ]
        return max(0.0, min(1.0, 1 - 2.5 * float(np.mean(distances))))

    @staticmethod
    def _reason_codes(
        home: TeamFeatures,
        away: TeamFeatures,
        context: PredictionContext,
    ) -> list[str]:
        codes: list[str] = []
        if abs(home.normalized_fifa_rank - away.normalized_fifa_rank) > 0.1:
            codes.append("ranking_gap")
        if abs(home.recent_form - away.recent_form) > 0.1:
            codes.append("recent_form")
        if abs(home.attack - away.attack) > 0.1:
            codes.append("attack_advantage")
        if abs(home.defense - away.defense) > 0.1:
            codes.append("defense_advantage")
        if context.odds:
            codes.append("market_consensus")
        if context.semantic_signal:
            codes.append("fresh_semantic_evidence")
        codes.extend(f"context_{item.factor}" for item in context.adjustments)
        return list(dict.fromkeys(codes)) or ["balanced_matchup"]

    def predict(
        self,
        match: Match,
        home: Team | None,
        away: Team | None,
        home_features: TeamFeatures | None,
        away_features: TeamFeatures | None,
        rng: np.random.Generator,
        allow_draw: bool = True,
        context: PredictionContext | None = None,
        sample_result: bool = False,
    ) -> MatchPrediction:
        """始终返回预测；缺失数据通过等级、权重和置信度降级。"""

        home_features, has_home_features = self._resolve_features(
            home, home_features, match.home_team_id
        )
        away_features, has_away_features = self._resolve_features(
            away, away_features, match.away_team_id
        )
        has_structured = has_home_features and has_away_features
        context = context or PredictionContext(structured_data_available=has_structured)
        grade, missing_fields = assess_data_grade(context, has_structured)
        confidence_cap = confidence_cap_for(grade)

        evidence = list(context.evidence)
        evidence.append(
            self._model_evidence(
                "model-strength",
                "球队实力特征用于胜平负基础概率。",
                "probability_components.strength",
                0.75 if has_structured else 0.25,
            )
        )

        strength_probabilities = self._strength_probabilities(
            home_features.team_strength,
            away_features.team_strength,
        )
        components: list[dict] = [
            {
                "name": "strength",
                "probabilities": strength_probabilities,
                "confidence": 0.75 if has_structured else 0.25,
                "evidence_ids": ["model-strength"],
            }
        ]

        home_advantage = 0.0 if context.neutral_venue else float(
            self.score_config.get("home_advantage", 0.15)
        )
        from wcpa.prediction.poisson_model import estimate_lambda

        lambda_home, lambda_away = estimate_lambda(
            home_features.attack,
            away_features.defense,
            away_features.attack,
            home_features.defense,
            base_goals=float(self.score_config.get("base_goals", 1.35)),
            home_advantage=home_advantage,
            clamp_min=float(self.score_config.get("lambda_clamp_min", 0.1)),
            clamp_max=float(self.score_config.get("lambda_clamp_max", 5.0)),
        )
        max_goals = int(self.score_config.get("max_goals", 10))
        score_matrix = score_probability_matrix(lambda_home, lambda_away, max_goals=max_goals)
        goal_probabilities = outcome_probabilities(score_matrix)
        if has_structured:
            evidence.append(
                self._model_evidence(
                    "model-goals",
                    "双方攻防特征用于 Poisson 比分分布。",
                    "probability_components.goals",
                    0.68,
                )
            )
            components.append(
                {
                    "name": "goals",
                    "probabilities": goal_probabilities,
                    "confidence": 0.68,
                    "evidence_ids": ["model-goals"],
                }
            )

        market = aggregate_bookmaker_odds(context.odds)
        if market is not None:
            market_evidence_ids: list[str] = []
            for index, quote in enumerate(context.odds, 1):
                evidence_id = f"market-{index}"
                market_evidence_ids.append(evidence_id)
                evidence.append(
                    PredictionEvidence(
                        evidence_id=evidence_id,
                        claim=f"{quote.bookmaker} 胜平负赔率已去水并进入市场聚合。",
                        source_type=quote.source_type,
                        source_name=quote.source_name or quote.bookmaker,
                        url=quote.url,
                        updated_at=quote.updated_at,
                        freshness=quote.freshness,
                        confidence=quote.confidence,
                        supported_fields=["probability_components.market"],
                        detail=(
                            f"十进制赔率：主胜 {quote.home:.2f}，平局 {quote.draw:.2f}，客胜 {quote.away:.2f}。"
                        ),
                        affected_team_ids=[match.home_team_id, match.away_team_id],
                        impact_summary="赔率已去除水位后作为市场分量进入本场融合概率。",
                        model_usage="model_input",
                    )
                )
            components.append(
                {
                    "name": "market",
                    "probabilities": market.probabilities,
                    "confidence": market.confidence,
                    "evidence_ids": market_evidence_ids,
                }
            )

        if context.semantic_signal is not None:
            signal = context.semantic_signal
            support_factor = 1.0 if signal.evidence_ids else 0.6
            components.append(
                {
                    "name": "web_semantic",
                    "probabilities": (
                        signal.home_win_prob,
                        signal.draw_prob,
                        signal.away_win_prob,
                    ),
                    "confidence": signal.confidence * support_factor,
                    "evidence_ids": signal.evidence_ids,
                }
            )

        neutral_config = self.fusion_config.get("neutral_prior", {})
        components.append(
            {
                "name": "neutral_prior",
                "probabilities": (
                    float(neutral_config.get("home", 0.375)),
                    float(neutral_config.get("draw", 0.25)),
                    float(neutral_config.get("away", 0.375)),
                ),
                "confidence": 1.0,
                "evidence_ids": [],
            }
        )

        template = self._fusion_template(
            has_market=market is not None,
            has_structured=context.structured_data_available and has_structured,
            has_semantic=context.semantic_signal is not None,
        )
        active_components = [item for item in components if template.get(item["name"], 0) > 0]
        raw_weights = [template[item["name"]] * item["confidence"] for item in active_components]
        weight_total = sum(raw_weights) or 1.0
        effective_weights = [value / weight_total for value in raw_weights]

        fused_array = np.zeros(3, dtype=float)
        component_models: list[ProbabilityComponent] = []
        for component, effective_weight in zip(active_components, effective_weights):
            fused_array += np.array(component["probabilities"]) * effective_weight
            component_probability = self._rounded_probabilities(
                self._normalize(component["probabilities"])
            )
            component_models.append(
                ProbabilityComponent(
                    name=component["name"],
                    home_win_prob=component_probability[0],
                    draw_prob=component_probability[1],
                    away_win_prob=component_probability[2],
                    confidence=round(component["confidence"], 4),
                    base_weight=template[component["name"]],
                    effective_weight=round(effective_weight, 4),
                    evidence_ids=component["evidence_ids"],
                )
            )

        fused = self._normalize(fused_array)
        fused, applied_adjustments = self._apply_adjustments(
            fused, context.adjustments, evidence
        )
        rounded_outcomes = self._rounded_probabilities(fused)

        et_matrix = score_probability_matrix(
            lambda_home * self.extra_time_factor,
            lambda_away * self.extra_time_factor,
            max_goals=max_goals,
        )
        et_home, et_draw, et_away = outcome_probabilities(et_matrix)
        penalty_home = context.penalty_home_win_prob if context.penalty_home_win_prob is not None else 0.5
        home_advance = fused[0] + fused[1] * (et_home + et_draw * penalty_home)
        away_advance = fused[2] + fused[1] * (et_away + et_draw * (1 - penalty_home))
        home_advance, _, away_advance = self._normalize((home_advance, 0.0, away_advance))

        if sample_result:
            home_score, away_score = sample_score_from_matrix(score_matrix, rng)
        else:
            home_score, away_score = most_likely_score(score_matrix)

        if home_score > away_score:
            winner = match.home_team_id
        elif away_score > home_score:
            winner = match.away_team_id
        elif allow_draw:
            winner = None
        elif sample_result:
            winner = match.home_team_id if rng.random() < home_advance else match.away_team_id
        else:
            winner = match.home_team_id if home_advance >= away_advance else match.away_team_id

        agreement = self._agreement(active_components, fused)
        component_confidence = sum(
            weight * component["confidence"]
            for weight, component in zip(effective_weights, active_components)
        )
        strength_diff = abs(home_features.team_strength - away_features.team_strength)
        concentration_confidence = compute_confidence(strength_diff, max(fused))
        raw_confidence = (
            0.40 * concentration_confidence
            + 0.35 * agreement
            + 0.25 * component_confidence
        )
        confidence = min(confidence_cap, max(0.1, raw_confidence))

        score_distribution = [
            ScorelineProbability(
                home_goals=home_goals,
                away_goals=away_goals,
                probability=round(probability, 5),
            )
            for home_goals, away_goals, probability in top_scorelines(score_matrix)
        ]
        assumptions = degradation_assumptions(grade, missing_fields)
        if context.neutral_venue:
            assumptions.append("世界杯对阵按中立场地处理，不默认赋予赛程主队主场优势。")
        if context.penalty_home_win_prob is None and not allow_draw:
            assumptions.append("缺少点球专项数据，点球大战使用 50/50 中性先验。")

        return MatchPrediction(
            match_id=match.match_id,
            home_win_prob=rounded_outcomes[0],
            draw_prob=rounded_outcomes[1],
            away_win_prob=rounded_outcomes[2],
            predicted_score=f"{home_score}-{away_score}",
            winner_team_id=winner,
            confidence=round(confidence, 4),
            confidence_cap=confidence_cap,
            data_grade=grade,
            missing_fields=missing_fields,
            assumptions=assumptions,
            evidence=evidence,
            probability_components=component_models,
            applied_adjustments=applied_adjustments,
            expected_home_goals=round(lambda_home, 4),
            expected_away_goals=round(lambda_away, 4),
            score_distribution=score_distribution,
            extra_time_prob=0.0 if allow_draw else rounded_outcomes[1],
            penalty_prob=0.0 if allow_draw else round(fused[1] * et_draw, 4),
            extra_time_home_win_prob=round(et_home, 4),
            extra_time_draw_prob=round(et_draw, 4),
            extra_time_away_win_prob=round(et_away, 4),
            penalty_home_win_prob=round(penalty_home, 4),
            penalty_away_win_prob=round(1 - penalty_home, 4),
            home_advancement_prob=0.0 if allow_draw else round(home_advance, 4),
            away_advancement_prob=0.0 if allow_draw else round(1 - round(home_advance, 4), 4),
            upset_index=0.0,
            consensus_type="multi_source_fusion",
            reason_codes=self._reason_codes(home_features, away_features, context),
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            source="multi_source_fusion",
        )


class BaselineMatchPredictor(MultiSourceMatchPredictor):
    """向后兼容名称；实现已升级为多源融合预测器。"""
