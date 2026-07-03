"""Agent-led web retrieval for World Cup evidence.

This is intentionally different from a page-specific crawler: agents ask
football questions, gather public evidence snippets, and expose those snippets
as auditable source snapshots for later structured extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from wcpa.agents.tooling import WebSearchTool
from wcpa.data.sources.web_collectors import SourceSnapshot
from wcpa.schemas.artifact import DataSourceStatus


@dataclass(frozen=True)
class AgentRetrievalQuestion:
    source_key: str
    query: str
    credibility: str
    purpose: str


DEFAULT_AGENT_QUESTIONS = [
    AgentRetrievalQuestion(
        source_key="agent_search_qualified_teams",
        query="2026 FIFA World Cup qualified teams official list",
        credibility="B",
        purpose="Find teams already qualified for the 2026 World Cup.",
    ),
    AgentRetrievalQuestion(
        source_key="agent_search_match_schedule",
        query="2026 FIFA World Cup schedule fixtures stadiums match list",
        credibility="B",
        purpose="Find public schedule and fixture evidence.",
    ),
    AgentRetrievalQuestion(
        source_key="agent_search_fifa_rankings",
        query="FIFA men's world ranking national teams July 2026",
        credibility="B",
        purpose="Find current FIFA ranking evidence for model features.",
    ),
    AgentRetrievalQuestion(
        source_key="agent_search_team_form",
        query="2026 World Cup national team recent form injuries squad news",
        credibility="C",
        purpose="Find form, injuries, squad and tactical context.",
    ),
]


class AgentEvidenceRetriever:
    """Runs broad agent web searches and returns auditable snapshots."""

    def __init__(self, timeout: float = 12.0):
        self.search_tool = WebSearchTool(timeout=timeout)

    def collect_all(self) -> list[SourceSnapshot]:
        return [self._collect(question) for question in DEFAULT_AGENT_QUESTIONS]

    def _collect(self, question: AgentRetrievalQuestion) -> SourceSnapshot:
        fetched_at = datetime.now(timezone.utc)
        evidence = self.search_tool.search(question.query, limit=6)
        results = evidence.results
        unavailable = len(results) == 1 and results[0].get("title") == "search_unavailable"
        status = "error" if unavailable else "ok"
        records = 0 if unavailable else len(results)
        message = (
            f"Agent web retrieval; query='{question.query}'; "
            f"evidence_results={records}; purpose={question.purpose}"
        )
        raw: dict[str, Any] = {
            "agent_tool": evidence.tool,
            "query": evidence.query,
            "purpose": question.purpose,
            "results": results,
            "retrieval_mode": "agent_web_search",
        }
        return SourceSnapshot(
            source_key=question.source_key,
            url=f"agent://web-search/{question.source_key}",
            status=DataSourceStatus(
                source_key=question.source_key,
                status=status,
                credibility=question.credibility,
                fetched_at=fetched_at,
                records=records,
                message=message,
            ),
            raw=raw,
        )
