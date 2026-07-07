"""Quality gates for product-grade research answers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


FORBIDDEN_PATTERNS = [
    r"https?://\S+",
    r"\brun_id\b",
    r"\bpayload\b",
    r"\bJSON\b",
    r"字段名",
    r"基于以下",
]


@dataclass(frozen=True)
class QualityReport:
    total: int
    dimensions: dict[str, int]
    passed: bool
    issues: list[str]


def evaluate_research_answer(
    *,
    answer: str,
    sources: list[dict[str, Any]],
    context: dict[str, Any],
    min_total: int = 24,
    source_required: bool = True,
    match_required: bool = True,
    structure_required: bool = True,
    concise_allowed: bool = False,
) -> QualityReport:
    dimensions: dict[str, int] = {}
    issues: list[str] = []

    dimensions["match_accuracy"] = _match_accuracy(answer, context, issues, match_required)
    dimensions["source_quality"] = _source_quality(sources, issues, source_required)
    dimensions["citation_coverage"] = _citation_coverage(answer, sources, issues, source_required)
    dimensions["structure"] = _structure_score(answer, issues, structure_required)
    dimensions["fact_safety"] = _fact_safety(answer, issues)
    dimensions["readability"] = _readability(answer, issues, concise_allowed)

    total = sum(dimensions.values())
    passed = total >= min_total and not _has_forbidden(answer)
    return QualityReport(total=total, dimensions=dimensions, passed=passed, issues=issues)


def _match_accuracy(answer: str, context: dict[str, Any], issues: list[str], match_required: bool) -> int:
    match = context.get("match") or {}
    home = str(match.get("home_team_raw") or match.get("home_team_id") or "")
    away = str(match.get("away_team_raw") or match.get("away_team_id") or "")
    if not match_required:
        return 5
    if not home or not away:
        return 4
    score = 0
    if home and home in answer:
        score += 2
    if away and away in answer:
        score += 2
    if score < 4:
        issues.append("回答没有清晰覆盖当前比赛双方。")
    return min(5, score + 1)


def _source_quality(sources: list[dict[str, Any]], issues: list[str], source_required: bool) -> int:
    if not sources and not source_required:
        return 5
    adopted = [source for source in sources if float(source.get("relevanceScore") or 0) >= 0.65]
    if len(adopted) >= 6:
        return 5
    if len(adopted) >= 4:
        return 4
    if len(adopted) >= 2:
        issues.append("采用来源少于产品级回答要求。")
        return 3
    issues.append("缺少足够高相关来源。")
    return 1 if sources else 0


def _citation_coverage(answer: str, sources: list[dict[str, Any]], issues: list[str], source_required: bool) -> int:
    citations = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    by_id = {int(source.get("citationId") or 0): source for source in sources if source.get("citationId")}
    available = set(by_id)
    if not source_required and not citations:
        return 5
    if not sources:
        issues.append("没有来源，无法形成引用覆盖。")
        return 0
    if citations and citations.issubset(available):
        if not _citations_supported_by_claims(answer, by_id, issues):
            return 2
        if len(citations) >= min(4, len(available)):
            return 5
        return 4
    issues.append("正文引用角标缺失或无法映射到来源。")
    return 2 if citations else 0


def _citations_supported_by_claims(answer: str, sources_by_id: dict[int, dict[str, Any]], issues: list[str]) -> bool:
    claim_sources = {
        citation_id: source
        for citation_id, source in sources_by_id.items()
        if source.get("supportedClaims")
    }
    if not claim_sources:
        return True
    ok = True
    cited_sentences = re.findall(r"([^。！？\n]*[。！？]?\s*\[(\d+)\])", answer)
    for sentence, raw_id in cited_sentences:
        citation_id = int(raw_id)
        source = sources_by_id.get(citation_id)
        claims = source.get("supportedClaims") if source else None
        if not claims:
            issues.append(f"引用 [{citation_id}] 没有关联 supportedClaims。")
            ok = False
            continue
        if not _sentence_matches_claims(sentence, claims):
            issues.append(f"引用 [{citation_id}] 的句子未明显匹配该来源支持点。")
            ok = False
    return ok


def _sentence_matches_claims(sentence: str, claims: list[dict[str, Any]]) -> bool:
    sentence_terms = _claim_terms(sentence)
    if not sentence_terms:
        return True
    for claim in claims:
        claim_text = " ".join(str(claim.get(key) or "") for key in ("claim", "evidence"))
        claim_terms = _claim_terms(claim_text)
        if sentence_terms & claim_terms:
            return True
    return False


def _claim_terms(text: str) -> set[str]:
    lowered = text.casefold()
    aliases = {
        "balogun": ["balogun", "巴洛贡", "弗拉林"],
        "pulisic": ["pulisic", "普利西奇", "克里斯蒂安"],
        "available": ["available", "can play", "eligible", "可出战", "可以出战", "可供选择", "获准"],
        "unavailable": ["unavailable", "ruled out", "cannot play", "无法出战", "缺阵", "不能出战"],
        "belgium": ["belgium", "比利时"],
        "senegal": ["senegal", "塞内加尔"],
        "venue": ["lumen", "seattle", "metlife", "sofi", "场馆", "球场"],
        "weather": ["weather", "forecast", "天气", "气温", "降雨"],
        "pitch": ["pitch", "grass", "turf", "草皮", "人工草", "天然草"],
        "bracket": ["bracket", "knockout", "quarterfinal", "semifinal", "final", "淘汰赛", "半决赛", "决赛", "占位符"],
    }
    terms = {name for name, variants in aliases.items() if any(variant in lowered for variant in variants)}
    if re.search(r"3\s*[-–]\s*2", lowered):
        terms.add("score_3_2")
    return terms


def _structure_score(answer: str, issues: list[str], structure_required: bool) -> int:
    if not structure_required and answer.strip():
        return 5
    headings = len(re.findall(r"(^|\n)(#{1,3}\s+|[^\n]{2,16}[:：])", answer))
    bullets = len(re.findall(r"(^|\n)\s*[-*]\s+", answer))
    if headings >= 4 and bullets >= 3:
        return 5
    if headings >= 3:
        return 4
    issues.append("回答结构不够清晰。")
    return 2


def _fact_safety(answer: str, issues: list[str]) -> int:
    if _has_forbidden(answer):
        issues.append("回答包含裸 URL、run_id、JSON 或内部字段。")
        return 0
    if "无法确认" in answer or "不确定" in answer or "缺少" in answer:
        return 5
    return 4


def _readability(answer: str, issues: list[str], concise_allowed: bool) -> int:
    length = len(answer.strip())
    if concise_allowed and length >= 10:
        return 5
    if 450 <= length <= 2200:
        return 5
    if 280 <= length < 450:
        issues.append("回答偏短，分析深度不足。")
        return 3
    if length > 2600:
        issues.append("回答过长，阅读成本偏高。")
        return 4
    issues.append("回答过短。")
    return 1


def _has_forbidden(answer: str) -> bool:
    return any(re.search(pattern, answer, re.IGNORECASE) for pattern in FORBIDDEN_PATTERNS)
