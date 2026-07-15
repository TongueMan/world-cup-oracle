"""将 Agent 的本地、API 和联网上下文接入统一预测内核。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import numpy as np

from wcpa.data.repositories.fixture_loader import load_teams
from wcpa.data.real_dataset import REAL_TEAMS_FILE
from wcpa.features.team_strength import compute_team_strength
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import (
    BookmakerOdds,
    MatchPrediction,
    PredictionContext,
    PredictionEvidence,
    SemanticProbabilitySignal,
)


def load_tournament_prediction_context(
    current_contenders: list[str] | None = None,
    artifact_id: str | None = None,
    expected_anchor: str | None = None,
) -> dict[str, Any]:
    """读取页面明确绑定的正式预测，供 Agent 解释冠军概率。"""

    from wcpa.api.deps import get_prediction_artifact_by_id

    if not artifact_id:
        return {}
    artifact = get_prediction_artifact_by_id(artifact_id, expected_anchor=expected_anchor)
    if artifact is None or not artifact.champion_probabilities:
        return {}
    names = _verified_team_names()
    rows = list(artifact.champion_probabilities)
    contenders = {item.casefold() for item in current_contenders or [] if item.strip()}
    if contenders:
        filtered = [
            row
            for row in rows
            if row.team_id.casefold() in contenders
            or names.get(row.team_id, "").casefold() in contenders
        ]
        if filtered:
            rows = filtered
        else:
            return {}
    return {
        "probability_source": "monte_carlo",
        "artifact_id": artifact.artifact_id,
        "anchor": artifact.current_tournament_state.requested_anchor if artifact.current_tournament_state else "",
        "simulation_count": max((row.simulation_count for row in rows), default=0),
        "data_verified": artifact.data_verified,
        "data_status": (
            artifact.data_quality_report.status if artifact.data_quality_report else "unknown"
        ),
        "rows": [
            {
                "team_id": row.team_id,
                "team_name": names.get(row.team_id, row.team_id),
                "champion_probability": row.probability,
                "most_common_eliminator": row.most_common_eliminator,
                "potential_key_match": row.potential_key_match,
            }
            for row in rows[:12]
        ],
    }


def load_bound_match_prediction(
    artifact_id: str | None,
    match_id: str,
    expected_anchor: str | None = None,
) -> dict[str, Any] | None:
    """Load the exact match prediction the user is looking at."""

    from wcpa.api.deps import get_prediction_artifact_by_id

    if not artifact_id:
        return None
    artifact = get_prediction_artifact_by_id(artifact_id, expected_anchor=expected_anchor)
    if artifact is None:
        return None
    prediction = next((row for row in artifact.match_predictions if row.match_id == match_id), None)
    return prediction.model_dump(mode="json") if prediction else None


def _verified_team_names() -> dict[str, str]:
    try:
        rows = json.loads(REAL_TEAMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        str(row.get("team_id")): str(row.get("name"))
        for row in rows
        if row.get("team_id") and row.get("name") and row.get("verified") is True
    }


def build_agent_match_prediction(
    context: dict[str, Any],
    sources: list[dict[str, Any]],
    search_attempted: bool,
    search_error: str = "",
) -> MatchPrediction | None:
    """从 Agent 上下文构造预测；占位对阵返回 None 交给路径推演。"""

    match_data = context.get("match") or {}
    home_id = str(
        match_data.get("home_team_id") or match_data.get("home_team_raw") or ""
    ).strip()
    away_id = str(
        match_data.get("away_team_id") or match_data.get("away_team_raw") or ""
    ).strip()
    if not home_id or not away_id or _is_placeholder(home_id) or _is_placeholder(away_id):
        return None

    teams = list(load_teams())
    home_team = _find_team(teams, home_id, str(match_data.get("home_team_raw") or ""))
    away_team = _find_team(teams, away_id, str(match_data.get("away_team_raw") or ""))
    structured = home_team is not None and away_team is not None
    evidence = _source_evidence(sources)
    odds = _bookmaker_odds(context.get("odds") or {}, home_id, away_id)
    home_terms = {home_id, str(match_data.get("home_team_raw") or "")}
    away_terms = {away_id, str(match_data.get("away_team_raw") or "")}
    if home_team:
        home_terms.update({home_team.team_id, home_team.name})
    if away_team:
        away_terms.update({away_team.team_id, away_team.name})
    semantic_signal = _semantic_signal(sources, home_terms, away_terms)
    missing_fields: list[str] = []
    if not odds:
        missing_fields.append("market_odds")
    if search_error:
        missing_fields.append("fresh_web_evidence")
    if not structured:
        missing_fields.append("structured_team_features")

    prediction_context = PredictionContext(
        odds=odds,
        evidence=evidence,
        semantic_signal=semantic_signal,
        missing_fields=missing_fields,
        structured_data_available=structured,
        lineup_data_available=_has_lineup_support(sources),
        web_search_attempted=search_attempted,
        web_search_succeeded=bool(sources),
        neutral_venue=True,
    )
    match_id = str(match_data.get("match_id") or f"agent-{home_id}-{away_id}")
    match = Match(
        match_id=match_id,
        stage=str(match_data.get("stage") or "World Cup"),
        home_team_id=home_team.team_id if home_team else home_id,
        away_team_id=away_team.team_id if away_team else away_id,
        status=str(match_data.get("status") or "scheduled"),
        source=str(match_data.get("source") or "agent_context"),
    )
    seed = int.from_bytes(hashlib.sha256(match_id.encode("utf-8")).digest()[:8], "big")
    return BaselineMatchPredictor().predict(
        match,
        home_team,
        away_team,
        compute_team_strength(home_team) if home_team else None,
        compute_team_strength(away_team) if away_team else None,
        np.random.default_rng(seed),
        allow_draw=not _is_knockout_stage(match.stage),
        context=prediction_context,
    )


def format_agent_match_prediction(
    prediction: MatchPrediction,
    home_label: str,
    away_label: str,
    source_count: int,
) -> str:
    """为无 LLM 或模型失败场景生成完整、低风险的预测回答。"""

    outcomes = [
        (home_label, prediction.home_win_prob),
        ("平局", prediction.draw_prob),
        (away_label, prediction.away_win_prob),
    ]
    tendency, _ = max(outcomes, key=lambda item: item[1])
    component_lines = [
        f"- {component.name}: 权重 {component.effective_weight:.0%}，置信度 {component.confidence:.0%}。"
        for component in prediction.probability_components
    ]
    missing = "、".join(prediction.missing_fields) or "无关键缺失"
    lines = [
        "### 结论倾向",
        f"- 当前第一倾向：**{tendency}**；数据等级 {prediction.data_grade}，置信度 {prediction.confidence:.0%}。",
        (
            f"- 常规时间概率：{home_label} {prediction.home_win_prob:.1%}，"
            f"平局 {prediction.draw_prob:.1%}，{away_label} {prediction.away_win_prob:.1%}。"
        ),
        f"- 最可能比分：{prediction.predicted_score}；期望进球 {prediction.expected_home_goals:.2f}-{prediction.expected_away_goals:.2f}。",
    ]
    if prediction.home_advancement_prob or prediction.away_advancement_prob:
        lines.append(
            f"- 最终晋级：{home_label} {prediction.home_advancement_prob:.1%}，"
            f"{away_label} {prediction.away_advancement_prob:.1%}。"
        )
    lines.extend(
        [
            "### 已确认事实与来源报道",
            f"- 已确认本次预测对象为 {home_label} vs {away_label}。",
            f"- 已采用 {source_count} 条联网来源；来源结论只通过绑定证据的组件进入概率。",
            "### 模型推断",
            *component_lines,
        ]
    )
    lines.extend(
        [
            "### 主要风险",
            f"- 缺失或待确认：{missing}。这些缺失已降低置信度，但没有中止预测。",
            *[f"- {assumption}" for assumption in prediction.assumptions[:3]],
            "### 来源与边界",
            f"- 本次结构化预测记录 {len(prediction.evidence)} 条证据或模型假设，其中联网来源 {source_count} 条。",
            "- 这是赛前概率判断，不是确定赛果，也不构成投注建议。",
        ]
    )
    return "\n".join(lines)


def _source_evidence(sources: list[dict[str, Any]]) -> list[PredictionEvidence]:
    rows: list[PredictionEvidence] = []
    for index, source in enumerate(sources, 1):
        supported = source.get("supportedClaims") or []
        supported_fields = [
            str(item.get("type") or "web_context")
            for item in supported
            if isinstance(item, dict)
        ]
        score = source.get("sourceQualityScore")
        confidence = float(score) if isinstance(score, (int, float)) else 0.6
        rows.append(
            PredictionEvidence(
                evidence_id=f"web-{source.get('citationId') or index}",
                claim=str(source.get("title") or source.get("snippet") or "联网比赛资料"),
                source_type="web",
                source_name=str(source.get("domain") or source.get("source") or "web"),
                url=str(source.get("url") or ""),
                updated_at=_parse_datetime(source.get("publishedAt")),
                freshness=0.8 if source.get("publishedAt") else 0.5,
                confidence=max(0.0, min(1.0, confidence)),
                supported_fields=supported_fields or ["web_context"],
            )
        )
    return rows


def _bookmaker_odds(
    odds_context: dict[str, Any],
    home_id: str,
    away_id: str,
) -> list[BookmakerOdds]:
    if odds_context.get("status") != "available":
        return []
    rows: list[BookmakerOdds] = []
    for market in odds_context.get("markets") or []:
        market_name = str(market.get("market") or "").casefold()
        if not any(term in market_name for term in ("winner", "fulltime")):
            continue
        values: dict[str, float] = {}
        for outcome in market.get("outcomes") or []:
            name = str(outcome.get("name") or "").strip()
            odd = outcome.get("odd")
            try:
                odd_value = float(odd)
            except (TypeError, ValueError):
                continue
            normalized = name.casefold()
            if normalized in {"home", "1"} or normalized in {home_id.casefold()}:
                values["home"] = odd_value
            elif normalized in {"draw", "x"}:
                values["draw"] = odd_value
            elif normalized in {"away", "2"} or normalized in {away_id.casefold()}:
                values["away"] = odd_value
        if values.keys() >= {"home", "draw", "away"}:
            rows.append(
                BookmakerOdds(
                    bookmaker=str(market.get("bookmaker") or odds_context.get("provider") or "市场来源"),
                    source_type="web" if odds_context.get("provider") == "firecrawl-web-odds" else "api",
                    home=values["home"],
                    draw=values["draw"],
                    away=values["away"],
                    source_name=str(odds_context.get("provider") or "API-Football"),
                    url=str(market.get("source_url") or ""),
                    updated_at=_parse_datetime(
                        odds_context.get("sourceUpdatedAt") or odds_context.get("fetchedAt")
                    ),
                )
            )
    return rows


def _semantic_signal(
    sources: list[dict[str, Any]],
    home_terms: set[str],
    away_terms: set[str],
) -> SemanticProbabilitySignal | None:
    """从明确的新闻措辞提取有上限的方向信号，不清晰时返回 None。"""

    positive_terms = (
        "favorite",
        "favoured",
        "favored",
        "expected to win",
        "advantage",
        "returns",
        "boost",
        "看好",
        "占优",
        "复出",
        "连胜",
    )
    negative_terms = (
        "ruled out",
        "injured",
        "suspended",
        "unavailable",
        "major doubt",
        "缺阵",
        "伤停",
        "停赛",
        "无法出场",
    )
    draw_terms = ("evenly matched", "too close to call", "势均力敌", "难分高下")
    normalized_home = {term.casefold() for term in home_terms if term.strip()}
    normalized_away = {term.casefold() for term in away_terms if term.strip()}
    home_signal = 0.0
    away_signal = 0.0
    draw_signal = 0.0
    evidence_ids: list[str] = []
    rationale: list[str] = []

    for index, source in enumerate(sources, 1):
        text = " ".join(
            str(source.get(field) or "") for field in ("title", "snippet", "excerpt")
        ).casefold()
        home_hit = any(term in text for term in normalized_home)
        away_hit = any(term in text for term in normalized_away)
        positive = any(term in text for term in positive_terms)
        negative = any(term in text for term in negative_terms)
        draw_hit = any(term in text for term in draw_terms)
        quality = source.get("sourceQualityScore")
        relevance = source.get("relevanceScore")
        weight = (
            (float(quality) if isinstance(quality, (int, float)) else 0.6)
            * (float(relevance) if isinstance(relevance, (int, float)) else 0.7)
        )
        direction_found = False
        if home_hit and not away_hit:
            home_signal += weight * (1 if positive else -1 if negative else 0)
            direction_found = positive or negative
        elif away_hit and not home_hit:
            away_signal += weight * (1 if positive else -1 if negative else 0)
            direction_found = positive or negative
        if draw_hit:
            draw_signal += weight
            direction_found = True
        if direction_found:
            evidence_ids.append(f"web-{source.get('citationId') or index}")
            rationale.append(str(source.get("title") or "联网来源提供明确方向信号"))

    directional_strength = abs(home_signal) + abs(away_signal) + draw_signal
    if directional_strength <= 0:
        return None
    home_delta = 0.08 * max(-1.0, min(1.0, home_signal - away_signal))
    away_delta = -home_delta
    draw_delta = 0.05 * max(0.0, min(1.0, draw_signal))
    probabilities = np.array(
        [0.375 + home_delta, 0.25 + draw_delta, 0.375 + away_delta],
        dtype=float,
    )
    probabilities = np.maximum(probabilities, 0.05)
    probabilities /= probabilities.sum()
    return SemanticProbabilitySignal(
        home_win_prob=float(probabilities[0]),
        draw_prob=float(probabilities[1]),
        away_win_prob=float(probabilities[2]),
        confidence=min(0.75, 0.35 + 0.12 * min(2.0, directional_strength)),
        rationale=rationale[:4],
        evidence_ids=list(dict.fromkeys(evidence_ids)),
    )


def _find_team(teams: list, team_id: str, raw_name: str):
    candidates = {team_id.casefold(), raw_name.casefold()} - {""}
    return next(
        (
            team
            for team in teams
            if team.team_id.casefold() in candidates or team.name.casefold() in candidates
        ),
        None,
    )


def _has_lineup_support(sources: list[dict[str, Any]]) -> bool:
    text = " ".join(
        f"{source.get('title', '')} {source.get('snippet', '')}" for source in sources
    ).casefold()
    return any(term in text for term in ("lineup", "starting xi", "首发", "阵容确认"))


def _is_placeholder(value: str) -> bool:
    text = value.strip()
    return (
        (len(text) >= 2 and text[0].upper() in {"W", "L"} and text[1:].isdigit())
        or text.upper() in {"TBD", "TBC", "UNKNOWN", "N/A", "NA"}
        or text in {"待定", "待确认", "未确定"}
    )


def _is_knockout_stage(stage: str) -> bool:
    return stage.casefold() in {
        "r32",
        "r16",
        "qf",
        "sf",
        "final",
        "thirdplace",
        "knockout",
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
