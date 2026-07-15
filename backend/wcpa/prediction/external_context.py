"""External evidence assembly for formal prediction runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from wcpa.agents.odds_service import ApiFootballOddsService
from wcpa.agents.prediction_bridge import _bookmaker_odds, _semantic_signal
from wcpa.agents.search import SearchCallError, SearchConfigError, search_web
from wcpa.schemas.artifact import DataSourceStatus
from wcpa.schemas.prediction import (
    PredictionContext,
    PredictionEvidence,
    ProbabilityAdjustment,
)
from wcpa.shared.env import env_bool, env_int
from wcpa.worldcup.environment import WorldCupEnvironmentService


@dataclass(frozen=True)
class ExternalContextResult:
    context: PredictionContext
    source_statuses: list[DataSourceStatus] = field(default_factory=list)


class ExternalPredictionContextBuilder:
    """Build a model-safe context from odds, web evidence, and environment data."""

    def __init__(
        self,
        odds_service: ApiFootballOddsService | None = None,
        environment_service: WorldCupEnvironmentService | None = None,
    ) -> None:
        self.odds_service = odds_service or ApiFootballOddsService()
        self.environment_service = environment_service or WorldCupEnvironmentService()
        self.search_enabled = env_bool(
            "WCPA_PREDICTION_WEB_EVIDENCE_ENABLED",
            env_bool("WCPA_WEB_SEARCH_ENABLED", True),
        )
        self.search_limit = max(1, min(6, env_int("WCPA_PREDICTION_WEB_EVIDENCE_RESULTS", 4)))
        self.max_queries = max(1, min(3, env_int("WCPA_PREDICTION_WEB_EVIDENCE_QUERIES", 2)))

    def build(self, match: dict[str, Any], home_id: str, away_id: str) -> ExternalContextResult:
        source_statuses: list[DataSourceStatus] = []
        odds_context = self._odds(match, source_statuses)
        odds = _bookmaker_odds(odds_context, home_id, away_id)
        environment = self._environment(match, source_statuses)
        sources = self._web_sources(match, home_id, away_id, source_statuses)
        evidence = self._evidence_from_sources(sources)
        evidence.extend(self._environment_evidence(match, environment))
        adjustments = self._adjustments(sources, evidence, home_id, away_id, environment)
        evidence = _annotate_evidence_usage(evidence, adjustments, home_id, away_id)
        home_terms = _team_terms(home_id, match.get("home_team_raw"))
        away_terms = _team_terms(away_id, match.get("away_team_raw"))
        semantic_signal = _semantic_signal(sources, home_terms, away_terms)
        missing_fields: list[str] = []
        if not odds:
            missing_fields.append("market_odds")
        if not _has_supported_field(evidence, "lineup") and not _has_supported_field(evidence, "injury"):
            missing_fields.append("confirmed_lineup_or_injuries")
        if self.search_enabled and not sources:
            missing_fields.append("fresh_web_evidence")

        context = PredictionContext(
            odds=odds,
            evidence=evidence,
            semantic_signal=semantic_signal,
            adjustments=adjustments,
            missing_fields=missing_fields,
            structured_data_available=True,
            lineup_data_available=_has_supported_field(evidence, "lineup")
            or _has_supported_field(evidence, "injury"),
            web_search_attempted=self.search_enabled,
            web_search_succeeded=bool(sources),
            neutral_venue=True,
        )
        return ExternalContextResult(context=context, source_statuses=source_statuses)

    def _odds(self, match: dict[str, Any], statuses: list[DataSourceStatus]) -> dict[str, Any]:
        try:
            payload = self.odds_service.get_match_odds(match)
        except Exception as exc:
            payload = {
                "provider": "api-football",
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        status = str(payload.get("status") or "unknown")
        records = len(payload.get("markets") or []) if status == "available" else 0
        statuses.append(
            DataSourceStatus(
                source_key=f"api_football_odds:{match.get('match_id')}",
                status="available" if status == "available" else status,
                credibility="B" if status == "available" else "D",
                fetched_at=_parse_datetime(payload.get("fetchedAt")) or datetime.now(timezone.utc),
                records=records,
                message=_odds_message(status, payload),
            )
        )
        if status != "available" and self.search_enabled:
            web_payload = self._web_odds(match, statuses)
            if web_payload.get("status") == "available":
                return web_payload
        return payload

    def _web_odds(self, match: dict[str, Any], statuses: list[DataSourceStatus]) -> dict[str, Any]:
        home_id = str(match.get("home_team_id") or "")
        away_id = str(match.get("away_team_id") or "")
        home_terms = _team_terms(home_id, match.get("home_team_raw"))
        away_terms = _team_terms(away_id, match.get("away_team_raw"))
        home_name = str(match.get("home_team_raw") or home_id)
        away_name = str(match.get("away_team_raw") or away_id)
        queries = [
            f"{home_id} {away_id} Draw moneyline World Cup odds",
            f"{home_name} {away_name} 90-minute moneyline draw odds",
        ]
        sources = []
        errors: list[str] = []
        for query in queries:
            try:
                sources.extend(search_web(query, limit=6))
            except (SearchConfigError, SearchCallError) as exc:
                errors.append(str(exc))
        if not sources:
            reason = "; ".join(errors[:2]) or "联网搜索未返回赔率来源。"
            statuses.append(
                DataSourceStatus(
                    source_key=f"web_market_odds:{match.get('match_id')}",
                    status="failed",
                    credibility="D",
                    records=0,
                    message=reason,
                )
            )
            return {"provider": "firecrawl-web-odds", "status": "failed", "reason": reason}
        markets = []
        seen_urls: set[str] = set()
        for source in sources:
            if source.url in seen_urls:
                continue
            text = " ".join((source.title, source.snippet, source.excerpt or ""))
            odds = _extract_web_match_winner(text, home_terms, away_terms)
            if odds is None:
                continue
            seen_urls.add(source.url)
            markets.append(
                {
                    "bookmaker": source.domain or source.source or "web",
                    "market": "Match Winner",
                    "source_url": source.url,
                    "outcomes": [
                        {"name": "Home", "odd": odds[0]},
                        {"name": "Draw", "odd": odds[1]},
                        {"name": "Away", "odd": odds[2]},
                    ],
                }
            )
        status = "available" if markets else "empty"
        statuses.append(
            DataSourceStatus(
                source_key=f"web_market_odds:{match.get('match_id')}",
                status=status,
                credibility="B" if markets else "D",
                fetched_at=datetime.now(timezone.utc),
                records=len(markets),
                message=(
                    f"API-Sports 当前套餐不可用，已从可追溯网页来源提取 {len(markets)} 组胜平负赔率。"
                    if markets
                    else "联网搜索未提取到完整且可校验的胜平负三项赔率。"
                ),
            )
        )
        return {
            "provider": "firecrawl-web-odds",
            "status": status,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "markets": markets,
        }

    def _environment(self, match: dict[str, Any], statuses: list[DataSourceStatus]) -> dict[str, Any]:
        match_id = str(match.get("match_id") or "")
        try:
            environment = self.environment_service.get_match_environment(match_id)
        except Exception as exc:
            environment = {"data_status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
        status = str(environment.get("data_status") or "unknown")
        statuses.append(
            DataSourceStatus(
                source_key=f"match_environment:{match_id}",
                status="available" if status == "ok" else status,
                credibility="B" if status in {"ok", "partial"} else "D",
                fetched_at=_parse_datetime(environment.get("fetched_at")),
                records=1 if status in {"ok", "partial"} else 0,
                message=str(environment.get("summary") or environment.get("reason") or "比赛环境信息"),
            )
        )
        return environment

    def _web_sources(
        self,
        match: dict[str, Any],
        home_id: str,
        away_id: str,
        statuses: list[DataSourceStatus],
    ) -> list[dict[str, Any]]:
        if not self.search_enabled:
            statuses.append(
                DataSourceStatus(
                    source_key=f"web_evidence:{match.get('match_id')}",
                    status="unconfigured",
                    credibility="D",
                    records=0,
                    message="正式预测联网证据检索未启用。",
                )
            )
            return []
        queries = _queries(match, home_id, away_id)[: self.max_queries]
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for query in queries:
            try:
                results = search_web(query, limit=self.search_limit)
            except SearchConfigError as exc:
                errors.append(str(exc))
                break
            except SearchCallError as exc:
                errors.append(str(exc))
                continue
            for index, source in enumerate(results, 1):
                payload = source.model_dump(by_alias=True)
                payload.setdefault("citationId", len(rows) + index)
                rows.append(payload)
        adopted = _dedupe_sources(rows)
        status = "available" if adopted else "empty" if not errors else "failed"
        statuses.append(
            DataSourceStatus(
                source_key=f"web_evidence:{match.get('match_id')}",
                status=status,
                credibility="B" if adopted else "D",
                fetched_at=datetime.now(timezone.utc),
                records=len(adopted),
                message=(
                    f"已检索 {len(queries)} 组赛前证据查询，采用 {len(adopted)} 条可靠来源。"
                    if adopted
                    else "; ".join(errors[:2]) or "联网搜索未返回可采用来源。"
                ),
            )
        )
        return adopted

    @staticmethod
    def _evidence_from_sources(sources: list[dict[str, Any]]) -> list[PredictionEvidence]:
        evidence: list[PredictionEvidence] = []
        for index, source in enumerate(sources, 1):
            text = _source_text(source)
            fields = _supported_fields(text)
            quality = float(source.get("sourceQualityScore") or 0.55)
            source_type = str(source.get("sourceType") or "media")
            reliability = _source_reliability(source_type, quality)
            detail = _source_detail(source)
            affected = _affected_teams(text)
            evidence.append(
                PredictionEvidence(
                    evidence_id=f"web-{source.get('citationId') or index}",
                    claim=str(source.get("title") or source.get("snippet") or "赛前外部资料"),
                    source_type="web",
                    source_name=str(source.get("domain") or source.get("source") or "web"),
                    url=str(source.get("url") or ""),
                    updated_at=_parse_datetime(source.get("publishedAt")),
                    freshness=0.85 if source.get("publishedAt") else 0.55,
                    confidence=reliability,
                    supported_fields=fields or ["web_context"],
                    detail=detail,
                    affected_team_ids=affected,
                    impact_summary=_context_impact(fields, text, affected),
                    model_usage="context_only",
                )
            )
        return evidence

    @staticmethod
    def _environment_evidence(match: dict[str, Any], environment: dict[str, Any]) -> list[PredictionEvidence]:
        status = str(environment.get("data_status") or "")
        if status not in {"ok", "partial", "venue_confirmed_weather_unavailable"}:
            return []
        return [
            PredictionEvidence(
                evidence_id=f"environment-{match.get('match_id')}",
                claim=str(environment.get("summary") or environment.get("reason") or "场馆与环境信息已记录。"),
                source_type="api" if environment.get("source") else "database",
                source_name=str(environment.get("source") or "match_environment"),
                url=str(environment.get("source_url") or ""),
                updated_at=_parse_datetime(environment.get("fetched_at")),
                freshness=0.65,
                confidence=0.65 if status == "ok" else 0.45,
                supported_fields=["environment"],
                detail=_environment_detail(environment),
                affected_team_ids=[
                    str(team_id)
                    for team_id in (match.get("home_team_id"), match.get("away_team_id"))
                    if team_id
                ],
                impact_summary=(
                    "环境指标达到修正阈值，将小幅提高平局和比赛波动。"
                    if (_environment_difficulty(environment) or 0) >= 0.35
                    else "环境信息已核验，但未达到修改胜平负概率的阈值。"
                ),
                model_usage=(
                    "applied" if (_environment_difficulty(environment) or 0) >= 0.35 else "context_only"
                ),
            )
        ]

    @staticmethod
    def _adjustments(
        sources: list[dict[str, Any]],
        evidence: list[PredictionEvidence],
        home_id: str,
        away_id: str,
        environment: dict[str, Any],
    ) -> list[ProbabilityAdjustment]:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        adjustments: list[ProbabilityAdjustment] = []
        home_terms = _team_terms(home_id, "")
        away_terms = _team_terms(away_id, "")
        for source in sources:
            text = _source_text(source)
            quality = _source_reliability(str(source.get("sourceType") or "media"), float(source.get("sourceQualityScore") or 0.55))
            if quality < 0.70:
                continue
            evidence_id = f"web-{source.get('citationId') or len(adjustments) + 1}"
            if evidence_id not in evidence_by_id:
                continue
            factor = _adjustment_factor(text)
            if factor is None:
                continue
            positive_hit = _contains_any(text, POSITIVE_TERMS)
            negative_hit = _contains_any(text, NEGATIVE_TERMS)
            if not positive_hit and not negative_hit:
                continue
            home_hit = _contains_any(text, home_terms)
            away_hit = _contains_any(text, away_terms)
            if home_hit == away_hit:
                continue
            magnitude = 0.025 if factor in {"lineup", "suspension"} else 0.015
            direction = -1 if negative_hit else 1
            signed = magnitude * direction
            if home_hit:
                deltas = (signed, 0.0, -signed)
            else:
                deltas = (-signed, 0.0, signed)
            adjustments.append(
                ProbabilityAdjustment(
                    factor=factor,
                    home_delta=deltas[0],
                    draw_delta=deltas[1],
                    away_delta=deltas[2],
                    confidence=min(0.85, quality),
                    rationale=str(source.get("title") or "可靠赛前来源提供方向性信息"),
                    evidence_ids=[evidence_id],
                )
            )
        difficulty = _environment_difficulty(environment)
        if difficulty is not None and difficulty >= 0.35:
            adjustments.append(
                ProbabilityAdjustment(
                    factor="environment",
                    home_delta=-0.005,
                    draw_delta=0.01,
                    away_delta=-0.005,
                    confidence=min(0.75, 0.45 + difficulty * 0.3),
                    rationale=str(environment.get("summary") or "环境压力可能提高比赛波动。"),
                    evidence_ids=[],
                )
            )
        return adjustments[:4]


NEGATIVE_TERMS = (
    "injured",
    "injury",
    "ruled out",
    "suspended",
    "unavailable",
    "doubt",
    "伤",
    "缺阵",
    "停赛",
    "无法出场",
    "累计黄牌",
)

POSITIVE_TERMS = (
    "available",
    "returns",
    "fit",
    "cleared",
    "boost",
    "strengthened",
    "复出",
    "恢复",
    "可以出场",
    "确认首发",
    "利好",
)


def _queries(match: dict[str, Any], home_id: str, away_id: str) -> list[str]:
    home = str(match.get("home_team_raw") or home_id)
    away = str(match.get("away_team_raw") or away_id)
    return [
        f"{home} {away} World Cup team news injuries suspensions lineup",
        f"{home} {away} FIFA World Cup press conference yellow cards weather",
        f"{home} vs {away} World Cup tactical preview latest news",
    ]


def _dedupe_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        url = str(row.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        quality = float(row.get("sourceQualityScore") or 0.0)
        source_type = str(row.get("sourceType") or "")
        if quality < 0.70 and source_type not in {"official", "wire"}:
            continue
        row["citationId"] = len(result) + 1
        result.append(row)
    return result[:8]


def _source_text(source: dict[str, Any]) -> str:
    return " ".join(
        str(source.get(key) or "") for key in ("title", "snippet", "excerpt", "domain")
    ).casefold()


def _source_detail(source: dict[str, Any]) -> str:
    values = []
    for key in ("excerpt", "snippet"):
        value = re.sub(r"\s+", " ", str(source.get(key) or "")).strip()
        if value and value not in values:
            values.append(value)
    return " ".join(values)[:700]


def _affected_teams(text: str) -> list[str]:
    return [
        team_id
        for team_id in ("ARG", "BRA", "ENG", "ESP", "FRA", "GER", "NED", "POR", "USA")
        if _contains_any(text, _team_terms(team_id, ""))
    ]


def _context_impact(fields: list[str], text: str, affected: list[str]) -> str:
    subject = "、".join(affected) if affected else "本场比赛"
    if _contains_any(text, NEGATIVE_TERMS):
        return f"来源包含对{subject}不利的阵容或纪律线索；只有事实和影响方向足够明确时才会修改概率。"
    if _contains_any(text, POSITIVE_TERMS):
        return f"来源包含对{subject}有利的阵容线索；只有事实和影响方向足够明确时才会修改概率。"
    if "tactical" in fields:
        return "该来源用于解释双方战术对位，没有形成可量化的方向性修正。"
    return "该来源作为赛前背景保留，没有直接修改概率。"


def _environment_detail(environment: dict[str, Any]) -> str:
    venue = environment.get("venue") if isinstance(environment.get("venue"), dict) else {}
    weather = environment.get("weather") if isinstance(environment.get("weather"), dict) else {}
    parts = []
    venue_name = venue.get("venue_name") or venue.get("tournament_name")
    if venue_name:
        parts.append(f"场馆：{venue_name}")
    values = (
        ("气温", weather.get("temperature_c"), "°C"),
        ("体感", weather.get("apparent_temperature_c"), "°C"),
        ("湿度", weather.get("humidity_pct"), "%"),
        ("降雨概率", weather.get("rain_probability"), "%"),
        ("风速", weather.get("wind_speed_kmh"), "km/h"),
    )
    for label, value, unit in values:
        if value is not None:
            parts.append(f"{label}：{value:g}{unit}")
    return "；".join(parts) + ("。" if parts else "")


def _annotate_evidence_usage(
    evidence: list[PredictionEvidence],
    adjustments: list[ProbabilityAdjustment],
    home_id: str,
    away_id: str,
) -> list[PredictionEvidence]:
    by_id = {
        evidence_id: adjustment
        for adjustment in adjustments
        for evidence_id in adjustment.evidence_ids
    }
    result = []
    for item in evidence:
        adjustment = by_id.get(item.evidence_id)
        if adjustment is None:
            result.append(item)
            continue
        direction = []
        if adjustment.home_delta:
            direction.append(f"{home_id} {adjustment.home_delta:+.1%}")
        if adjustment.away_delta:
            direction.append(f"{away_id} {adjustment.away_delta:+.1%}")
        result.append(item.model_copy(update={
            "model_usage": "applied",
            "impact_summary": f"已作为{adjustment.factor}修正进入单场概率（{'，'.join(direction)}，再按证据置信度缩放）。",
        }))
    return result


def _supported_fields(text: str) -> list[str]:
    fields = []
    if _contains_any(text, ("lineup", "starting xi", "首发", "阵容")):
        fields.append("lineup")
    if _contains_any(text, ("injury", "injured", "ruled out", "伤停", "缺阵", "受伤")):
        fields.append("injury")
    if _contains_any(text, ("suspended", "yellow card", "booking", "停赛", "黄牌")):
        fields.append("discipline")
    if _contains_any(text, ("weather", "rain", "wind", "temperature", "pitch", "天气", "降雨", "风", "草皮")):
        fields.append("environment")
    if _contains_any(text, ("tactical", "formation", "pressing", "counterattack", "strategy", "strategies", "scouting report", "战术", "阵型", "逼抢", "反击")):
        fields.append("tactical")
    if _contains_any(text, ("favorite", "favoured", "favored", "advantage", "看好", "占优")):
        fields.append("web_semantic")
    return fields


def _adjustment_factor(text: str) -> str | None:
    if _contains_any(text, ("suspended", "yellow card", "booking", "停赛", "黄牌")):
        return "suspension"
    if _contains_any(text, ("lineup", "starting xi", "injury", "injured", "ruled out", "首发", "阵容", "伤停", "缺阵")):
        return "lineup"
    if _contains_any(text, ("tactical", "formation", "pressing", "counterattack", "strategy", "strategies", "scouting report", "战术", "阵型", "逼抢", "反击")):
        return "tactical"
    return None


def _source_reliability(source_type: str, quality: float) -> float:
    if source_type in {"official", "wire"}:
        return max(0.80, min(0.98, quality))
    return max(0.0, min(0.85, quality))


def _contains_any(text: str, terms: tuple[str, ...] | set[str]) -> bool:
    return any(term.casefold() in text for term in terms if term)


def _team_terms(team_id: str, raw_name: Any) -> set[str]:
    terms = {team_id, str(raw_name or "")}
    aliases = {
        "ARG": {"argentina", "阿根廷"},
        "BRA": {"brazil", "巴西"},
        "ENG": {"england", "英格兰"},
        "ESP": {"spain", "西班牙"},
        "FRA": {"france", "法国"},
        "GER": {"germany", "德国"},
        "NED": {"netherlands", "holland", "荷兰"},
        "POR": {"portugal", "葡萄牙"},
        "USA": {"united states", "usa", "美国"},
    }
    terms.update(aliases.get(team_id.upper(), set()))
    return {term.casefold() for term in terms if term and not str(term).startswith(("W", "L"))}


def _has_supported_field(evidence: list[PredictionEvidence], field: str) -> bool:
    return any(field in item.supported_fields for item in evidence)


def _environment_difficulty(environment: dict[str, Any]) -> float | None:
    features = environment.get("features") if isinstance(environment.get("features"), dict) else {}
    value = features.get("environment_difficulty_index") or environment.get("environment_difficulty_index")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_web_match_winner(
    text: str,
    home_terms: set[str],
    away_terms: set[str],
) -> tuple[float, float, float] | None:
    normalized = text.casefold()
    home = _labelled_odd(normalized, home_terms | {"home"})
    draw = _labelled_odd(normalized, {"draw", "tie", "平局"})
    away = _labelled_odd(normalized, away_terms | {"away"})
    if home is None or draw is None or away is None:
        return None
    if min(home, draw, away) <= 1.0 or max(home, draw, away) > 30:
        return None
    return home, draw, away


def _labelled_odd(text: str, labels: set[str]) -> float | None:
    for label in sorted((item for item in labels if len(item) >= 2), key=len, reverse=True):
        match = re.search(
            rf"(?:^|\b){re.escape(label.casefold())}(?:\s+(?:win|winner|moneyline|odds|to advance))?\s*[:\-]?\s*([+]\d+|-\d+|\d+/\d+|\d+\.\d+)(?:\b|$)",
            text,
        )
        if not match:
            continue
        value = match.group(1)
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            if float(denominator) <= 0:
                continue
            return 1 + float(numerator) / float(denominator)
        number = float(value)
        if value.startswith("+"):
            return 1 + number / 100
        if value.startswith("-"):
            return 1 + 100 / abs(number)
        return number
    return None


def _odds_message(status: str, payload: dict[str, Any]) -> str:
    if status == "available":
        return "API-Football 返回赛前盘口，已作为市场概率信号候选。"
    if status == "unconfigured":
        return "API-Football 赔率源未配置 API key。"
    if status == "unmatched":
        return "赔率源已配置，但未匹配到该场比赛的 API-Football fixture。"
    if status == "empty":
        return "赔率源已配置，但该场未返回可用盘口。"
    return str(payload.get("reason") or "赔率源暂不可用。")


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
