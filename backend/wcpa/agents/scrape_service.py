"""Unified Agent web scrape service."""

from __future__ import annotations

from dataclasses import dataclass

from wcpa.agents.firecrawl_client import FirecrawlClient
from wcpa.agents.search_policy import SearchBudget, load_search_deployment_config


@dataclass(frozen=True)
class ScrapeServiceResult:
    url: str
    title: str
    markdown: str
    metadata: dict
    raw: dict
    status: str = "success"


def scrape_url(url: str, budget: SearchBudget | None = None) -> ScrapeServiceResult:
    config = load_search_deployment_config()
    active_budget = budget or config.budget
    client = FirecrawlClient("", active_budget)
    response = client.scrape(url)
    return ScrapeServiceResult(
        url=response.url,
        title=response.title,
        markdown=response.markdown,
        metadata=response.metadata,
        raw=response.raw,
    )
