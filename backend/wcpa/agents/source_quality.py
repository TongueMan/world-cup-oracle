"""Source filtering and lightweight quality scoring for web evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from urllib.parse import urlparse
from typing import Any


PREFERRED_DOMAINS = {
    "fifa.com",
    "espn.com",
    "bbc.com",
    "bbc.co.uk",
    "reuters.com",
    "theguardian.com",
    "skysports.com",
    "uefa.com",
    "cbssports.com",
    "apnews.com",
    "nytimes.com",
    "theathletic.com",
    "foxsports.com",
    "si.com",
    "standard.co.uk",
    "the-independent.com",
    "sports.yahoo.com",
    "theanalyst.com",
    "rotowire.com",
}

OFFICIAL_DOMAINS = {"fifa.com", "uefa.com"}
TEAM_OFFICIAL_DOMAINS = {
    "afa.com.ar",
    "fff.fr",
    "thefa.com",
    "cbf.com.br",
    "sefutbol.com",
    "dfb.de",
    "onsoranje.nl",
    "fpf.pt",
    "ussoccer.com",
}
WIRE_DOMAINS = {"reuters.com", "apnews.com"}
VIDEO_DOMAIN_HINTS = {"youtube.com", "youtu.be", "foxsports.com/video"}
SOCIAL_DOMAIN_HINTS = {"facebook.com", "x.com", "twitter.com", "instagram.com", "tiktok.com"}

BLOCKED_DOMAIN_HINTS = {
    "bet",
    "casino",
    "coupon",
    "download",
    "mirror",
    "pirate",
}


@dataclass(frozen=True)
class QualifiedSource:
    title: str
    url: str
    domain: str
    snippet: str
    published_at: str | None
    source_quality_score: float
    raw: dict
    relevance_score: float = 0.0
    source_type: str = "media"
    adoption_reason: str = ""
    excerpt: str = ""


def normalize_domain(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def source_quality_score(url: str) -> float:
    domain = normalize_domain(url)
    if not domain:
        return 0.0
    if any(hint in domain for hint in BLOCKED_DOMAIN_HINTS):
        return 0.05
    if any(domain == item or domain.endswith("." + item) for item in OFFICIAL_DOMAINS | TEAM_OFFICIAL_DOMAINS):
        return 0.98
    if any(domain == item or domain.endswith("." + item) for item in PREFERRED_DOMAINS):
        return 0.95
    if domain.endswith((".edu", ".gov")):
        return 0.85
    return 0.55


def source_type_for_domain(domain: str) -> str:
    if any(domain == item or domain.endswith("." + item) for item in OFFICIAL_DOMAINS | TEAM_OFFICIAL_DOMAINS):
        return "official"
    if any(domain == item or domain.endswith("." + item) for item in WIRE_DOMAINS):
        return "wire"
    if any(hint in domain for hint in VIDEO_DOMAIN_HINTS):
        return "video"
    if any(hint in domain for hint in SOCIAL_DOMAIN_HINTS):
        return "social"
    return "media"


def qualify_sources(rows: list[dict], limit: int) -> list[QualifiedSource]:
    seen: set[str] = set()
    qualified: list[QualifiedSource] = []
    for row in rows:
        url = str(row.get("url") or row.get("link") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        score = source_quality_score(url)
        if score < 0.1:
            continue
        qualified.append(
            QualifiedSource(
                title=str(row.get("title") or row.get("name") or "Untitled").strip(),
                url=url,
                domain=normalize_domain(url),
                snippet=str(row.get("snippet") or row.get("description") or row.get("content") or "").strip(),
                published_at=row.get("date") if isinstance(row.get("date"), str) else None,
                source_quality_score=score,
                raw=row,
                source_type=source_type_for_domain(normalize_domain(url)),
            )
        )
    qualified.sort(key=lambda item: item.source_quality_score, reverse=True)
    return qualified[:limit]


def score_match_relevance(source: QualifiedSource, context: dict[str, Any]) -> tuple[float, str]:
    match = context.get("match") or {}
    environment = context.get("environment") or {}
    intent = str(context.get("intent") or "").casefold()
    haystack = " ".join([source.title, source.snippet, source.url, source.excerpt]).casefold()
    home_terms = _team_terms(match, "home")
    away_terms = _team_terms(match, "away")
    home_hit = any(term and term.casefold() in haystack for term in home_terms)
    away_hit = any(term and term.casefold() in haystack for term in away_terms)
    worldcup_hit = any(term in haystack for term in ("world cup", "fifa", "世界杯"))
    venue_terms = _venue_terms(environment)
    venue_hit = any(term and term.casefold() in haystack for term in venue_terms)
    weather_hit = any(term in haystack for term in ("weather", "forecast", "temperature", "rain", "wind", "天气", "降雨", "气温", "风速"))
    pitch_hit = any(term in haystack for term in ("pitch", "grass", "turf", "surface", "草皮", "天然草", "人工草"))
    bracket_hit = any(term in haystack for term in ("bracket", "knockout", "round of 16", "quarterfinal", "semifinal", "final", "淘汰赛", "晋级路径", "决赛"))
    post_match_hit = any(
        term in haystack
        for term in (
            "match report", "post-match", "post match", "as it happened", "full-time", "final score",
            "reaction", "highlights", "goals", "scorer", "scored", "beat", "beaten", "defeated",
            "won", "victory", "进球", "战报", "赛后", "击败", "战胜", "晋级",
        )
    )
    stage = str(match.get("stage") or "")
    stage_hit = bool(stage and stage.casefold() in haystack)
    score = 0.0
    environment_intent = intent == "weather_environment" or weather_hit or pitch_hit
    bracket_intent = bool(context.get("bracket", {}).get("has_placeholders"))
    if intent == "post_match_report":
        if home_hit:
            score += 0.25
        if away_hit:
            score += 0.25
        if worldcup_hit:
            score += 0.1
        if post_match_hit:
            score += 0.3
        if stage_hit:
            score += 0.05
    elif environment_intent:
        if venue_hit:
            score += 0.45
        if weather_hit or pitch_hit:
            score += 0.25
        if worldcup_hit:
            score += 0.15
        if home_hit or away_hit:
            score += 0.1
    elif bracket_intent:
        if bracket_hit:
            score += 0.35
        if worldcup_hit:
            score += 0.25
        if stage_hit:
            score += 0.15
        if home_hit or away_hit:
            score += 0.15
    else:
        if home_hit:
            score += 0.35
        if away_hit:
            score += 0.35
        if worldcup_hit:
            score += 0.15
        if stage_hit:
            score += 0.05
    if source.source_type in {"official", "wire"}:
        score += 0.05
    if environment_intent and source.source_quality_score >= 0.9 and (weather_hit or pitch_hit or venue_hit):
        score += 0.1
    if bracket_intent and source.source_quality_score >= 0.9 and bracket_hit:
        score += 0.1
    if source.source_type == "social":
        score -= 0.15
    score = round(max(0.0, min(1.0, score)), 4)
    if intent == "post_match_report" and home_hit and away_hit and post_match_hit:
        reason = "匹配双方球队和赛后事件语境"
    elif intent == "post_match_report" and home_hit and away_hit:
        reason = "匹配双方球队，但缺少明确赛后事件信号"
    elif environment_intent and venue_hit:
        reason = "匹配场馆/环境问题"
    elif environment_intent and (weather_hit or pitch_hit):
        reason = "匹配天气或草皮信息"
    elif bracket_intent and bracket_hit:
        reason = "匹配淘汰赛路径语境"
    elif home_hit and away_hit:
        reason = "匹配双方球队"
    elif home_hit or away_hit:
        reason = "仅匹配一方球队，默认不采用"
    else:
        reason = "未匹配当前比赛双方"
    if worldcup_hit and home_hit and away_hit:
        reason += "，且匹配世界杯语境"
    return score, reason


def source_with_relevance(source: QualifiedSource, context: dict[str, Any], excerpt: str = "") -> QualifiedSource:
    candidate = replace(source, excerpt=excerpt[:3600])
    score, reason = score_match_relevance(candidate, context)
    return replace(candidate, relevance_score=score, adoption_reason=reason)


def _venue_terms(environment: dict[str, Any]) -> list[str]:
    venue = environment.get("venue") if isinstance(environment.get("venue"), dict) else {}
    terms = [
        str(venue.get("venue_id") or ""),
        str(venue.get("venue_name") or ""),
        str(venue.get("tournament_name") or ""),
        str(venue.get("host_city") or ""),
        str(venue.get("city") or ""),
    ]
    terms.extend(str(item) for item in venue.get("aliases") or [])
    terms.extend(str(item) for item in venue.get("source_venue_ids") or [])
    return [term for term in terms if term]


def _team_terms(match: dict[str, Any], side: str) -> list[str]:
    team_id = str(match.get(f"{side}_team_id") or "")
    raw = str(match.get(f"{side}_team_raw") or "")
    terms = [team_id, raw]
    aliases = {
        "SUI": ["Switzerland", "Swiss", "瑞士"],
        "ALG": ["Algeria", "阿尔及利亚"],
        "COL": ["Colombia", "哥伦比亚"],
        "GHA": ["Ghana", "加纳"],
        "ARG": ["Argentina", "阿根廷"],
        "ENG": ["England", "英格兰"],
        "FRA": ["France", "法国"],
        "BRA": ["Brazil", "巴西"],
        "NOR": ["Norway", "挪威"],
        "USA": ["United States", "US", "USA", "美国"],
        "MAR": ["Morocco", "摩洛哥"],
        "CAN": ["Canada", "加拿大"],
        "POR": ["Portugal", "葡萄牙"],
        "ESP": ["Spain", "西班牙"],
    }
    terms.extend(aliases.get(team_id, []))
    raw_key = raw.casefold()
    for alias_values in aliases.values():
        if any(raw_key == alias.casefold() for alias in alias_values):
            terms.extend(alias_values)
            break
    return [term for term in terms if term and not term.startswith(("W", "L"))]
