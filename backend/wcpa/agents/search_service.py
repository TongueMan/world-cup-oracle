"""Unified Agent web search service."""

from __future__ import annotations

from dataclasses import dataclass

from wcpa.agents.firecrawl_client import FirecrawlClient
from wcpa.agents.search_policy import SearchBudget, load_search_deployment_config
from wcpa.agents.source_quality import QualifiedSource, qualify_sources


@dataclass(frozen=True)
class SearchServiceResult:
    query: str
    search_id: str | None
    sources: list[QualifiedSource]
    raw: dict


def search_web(query: str, limit: int | None = None, budget: SearchBudget | None = None) -> SearchServiceResult:
    config = load_search_deployment_config()
    active_budget = budget or config.budget
    client = FirecrawlClient("", active_budget)
    max_results = limit or active_budget.max_results
    response = client.search(query, max_results)
    return SearchServiceResult(
        query=query,
        search_id=response.search_id,
        sources=qualify_sources(response.rows, max_results),
        raw=response.raw,
    )
