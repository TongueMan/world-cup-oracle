"""Deploy-time configured web search tool for Agent chat."""

from __future__ import annotations

from wcpa.agents.firecrawl_client import FirecrawlCallError, FirecrawlConfigError
from wcpa.agents.search_policy import load_search_deployment_config
from wcpa.agents.search_service import search_web as service_search_web
from wcpa.schemas.agent_chat import AgentSearchCapability, SearchResult


class SearchConfigError(RuntimeError):
    """Raised when search is requested but not configured."""


class SearchCallError(RuntimeError):
    """Raised when the configured search provider fails."""


def search_capability() -> AgentSearchCapability:
    config = load_search_deployment_config()
    if not config.enabled:
        return AgentSearchCapability(
            enabled=False,
            provider=None,
            message="当前部署未启用联网搜索：请在 .env 配置 WCPA_WEB_SEARCH_ENABLED=true、WCPA_SEARCH_PROVIDER=firecrawl。",
        )
    if config.provider != "firecrawl":
        return AgentSearchCapability(
            enabled=False,
            provider=None,
            message="当前部署的搜索 provider 不是 firecrawl：请设置 WCPA_SEARCH_PROVIDER=firecrawl。",
        )
    return AgentSearchCapability(
        enabled=True,
        provider="firecrawl",
        message="联网搜索已由后端 Firecrawl provider 启用；有 Firecrawl 密钥时使用密钥，未配置时先尝试 Keyless。",
    )


def search_web(query: str, limit: int = 5) -> list[SearchResult]:
    capability = search_capability()
    if not capability.enabled:
        raise SearchConfigError(capability.message)
    try:
        result = service_search_web(query, limit=limit)
    except FirecrawlConfigError as exc:
        raise SearchConfigError(str(exc)) from exc
    except FirecrawlCallError as exc:
        raise SearchCallError(str(exc)) from exc
    return [
        SearchResult(
            title=source.title,
            url=source.url,
            snippet=source.snippet,
            source="firecrawl",
            domain=source.domain,
            publishedAt=source.published_at,
            sourceQualityScore=source.source_quality_score,
            relevanceScore=source.relevance_score,
            sourceType=source.source_type,
            adoptionReason=source.adoption_reason,
            excerpt=source.excerpt,
        )
        for source in result.sources
    ]
