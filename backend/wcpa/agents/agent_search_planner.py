"""Create bounded search plans from Agent actions and local data gaps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wcpa.agents.agent_context_builder import match_label
from wcpa.agents.match_analysis_inputs import MatchDataCoverage
from wcpa.agents.search_policy import SearchBudget


TEAM_SEARCH_ALIASES = {
    "阿根廷": "Argentina",
    "澳大利亚": "Australia",
    "比利时": "Belgium",
    "巴西": "Brazil",
    "加拿大": "Canada",
    "克罗地亚": "Croatia",
    "丹麦": "Denmark",
    "厄瓜多尔": "Ecuador",
    "英格兰": "England",
    "法国": "France",
    "德国": "Germany",
    "加纳": "Ghana",
    "伊朗": "Iran",
    "意大利": "Italy",
    "日本": "Japan",
    "韩国": "South Korea",
    "墨西哥": "Mexico",
    "摩洛哥": "Morocco",
    "荷兰": "Netherlands",
    "巴拉圭": "Paraguay",
    "葡萄牙": "Portugal",
    "塞内加尔": "Senegal",
    "塞尔维亚": "Serbia",
    "西班牙": "Spain",
    "瑞士": "Switzerland",
    "乌拉圭": "Uruguay",
    "美国": "United States",
    "威尔士": "Wales",
}


@dataclass(frozen=True)
class SearchPlan:
    intent: str
    queries: list[str]
    missing_local_fields: list[str]


def build_search_plan(
    tool_name: str,
    context: dict[str, Any],
    coverage: MatchDataCoverage,
    budget: SearchBudget,
    question: str = "",
) -> SearchPlan:
    match = context.get("match") or {}
    stage = match.get("stage") or "World Cup"
    status = str(match.get("status") or "").lower()
    label = _search_label(context)
    base = f"2026 FIFA World Cup {label} {stage}"

    if tool_name == "search-news":
        intent = "latest_news"
        queries = [f"{base} latest team news injuries lineup preview"]
    elif tool_name == "report":
        intent = _report_intent(match.get("status"))
        queries = _report_queries(base, status)
    elif tool_name == "analyze":
        intent = "match_analysis"
        queries = _analysis_queries(base, coverage.search_worthy_missing_fields, question, status)
    else:
        intent = "general_chat"
        queries = [f"{base} {question}".strip()]

    bounded = []
    for query in queries:
        clean = " ".join(query.split())[:500]
        if clean and clean not in bounded:
            bounded.append(clean)
        if len(bounded) >= budget.max_queries_per_request:
            break
    return SearchPlan(
        intent=intent,
        queries=bounded,
        missing_local_fields=coverage.missing_local_fields,
    )


def _analysis_queries(base: str, missing: list[str], question: str, status: str) -> list[str]:
    if status in {"complete", "completed", "final", "closed"}:
        queries = []
        if question:
            queries.append(f"{base} {question} match report goals highlights scorers")
        queries.extend(
            [
                f"{base} match report goals highlights scorers",
                f"{base} match stats possession shots on target",
                f"{base} post match reaction coach press conference",
            ]
        )
        return queries

    if status == "live":
        return [
            f"{base} live updates key events goals cards",
            f"{base} live stats possession shots on target",
            f"{base} team news injuries lineup",
        ]

    queries = []
    if any(field in missing for field in ("injury_news", "lineup_prediction")):
        queries.append(f"{base} injuries expected lineup team news")
    if "referee_assignment" in missing:
        queries.append(f"{base} referee assignment")
    if "technical_stats" in missing:
        queries.append(f"{base} match stats possession shots on target")
    if question:
        queries.append(f"{base} {question}")
    return queries or [f"{base} match preview team news"]


def _report_queries(base: str, status: str) -> list[str]:
    if status in {"complete", "completed", "final", "closed"}:
        return [
            f"{base} match report goals highlights scorers",
            f"{base} match stats possession shots on target",
            f"{base} post match reaction coach press conference",
        ]
    if status == "live":
        return [
            f"{base} live updates key events goals cards",
            f"{base} live stats possession shots on target",
            f"{base} live tactical analysis",
        ]
    return [
        f"{base} injuries expected lineup team news",
        f"{base} referee assignment preview",
        f"{base} tactical preview coach press conference",
    ]


def _report_intent(status: str | None) -> str:
    if status in {"complete", "final"}:
        return "post_match_report"
    if status == "live":
        return "live_match_brief"
    return "pre_match_report"


def _search_label(context: dict[str, Any]) -> str:
    match = context.get("match") or {}
    home = _team_search_name(match.get("home_team_raw") or match.get("home_team_id") or "TBD")
    away = _team_search_name(match.get("away_team_raw") or match.get("away_team_id") or "TBD")
    local = match_label(context)
    english = f"{home} vs {away}"
    if english == local:
        return local
    return f"{english} {local}"


def _team_search_name(value: Any) -> str:
    text = str(value or "").strip()
    return TEAM_SEARCH_ALIASES.get(text, text)
