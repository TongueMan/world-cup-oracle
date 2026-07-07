"""Search authorization and budget policy for Agent web evidence."""

from __future__ import annotations

from dataclasses import dataclass

from wcpa.shared.env import env_bool, env_int, env_str


ALLOWED_SEARCH_TOOLS = {
    "chat",
    "analyze",
    "report",
    "search-news",
}


@dataclass(frozen=True)
class SearchBudget:
    max_queries_per_request: int
    max_results: int
    scrape_top_n: int
    timeout_seconds: int
    max_page_chars: int
    cache_ttl_seconds: int


@dataclass(frozen=True)
class SearchDeploymentConfig:
    enabled: bool
    provider: str
    budget: SearchBudget


@dataclass(frozen=True)
class SearchAuthorization:
    deployment_search_enabled: bool
    user_search_allowed: bool
    request_search_enabled: bool
    tool_search_allowed: bool
    provider: str | None
    message: str

    @property
    def can_search(self) -> bool:
        return (
            self.deployment_search_enabled
            and self.user_search_allowed
            and self.request_search_enabled
            and self.tool_search_allowed
        )


def load_search_deployment_config() -> SearchDeploymentConfig:
    provider = env_str("WCPA_SEARCH_PROVIDER", "firecrawl") or env_str("SEARCH_PROVIDER", "firecrawl")
    enabled = env_bool("WCPA_WEB_SEARCH_ENABLED", True) or env_bool("WEB_SEARCH_ENABLED", False)
    budget = SearchBudget(
        max_queries_per_request=min(4, max(1, env_int("WCPA_FIRECRAWL_MAX_QUERIES_PER_REQUEST", 3))),
        max_results=min(6, max(1, env_int("WCPA_FIRECRAWL_MAX_RESULTS", 5))),
        scrape_top_n=min(3, max(0, env_int("WCPA_FIRECRAWL_SCRAPE_TOP_N", 3))),
        timeout_seconds=min(15, max(3, env_int("WCPA_FIRECRAWL_TIMEOUT_SECONDS", 12))),
        max_page_chars=max(1000, env_int("WCPA_FIRECRAWL_MAX_PAGE_CHARS", 12000)),
        cache_ttl_seconds=max(0, env_int("WCPA_SEARCH_CACHE_TTL_SECONDS", 600)),
    )
    return SearchDeploymentConfig(
        enabled=enabled,
        provider=provider.strip().lower(),
        budget=budget,
    )


def user_search_allowed(_session_id: str | None = None) -> bool:
    """Placeholder for future account, package, quota, or admin policy checks."""
    return True


def evaluate_search_authorization(
    tool_name: str,
    request_search_enabled: bool,
    session_id: str | None = None,
) -> SearchAuthorization:
    config = load_search_deployment_config()
    tool_allowed = tool_name in ALLOWED_SEARCH_TOOLS
    user_allowed = user_search_allowed(session_id)
    deployment_enabled = config.enabled and config.provider == "firecrawl"
    if not config.enabled:
        message = "当前部署未启用联网搜索：请在 .env 配置 WCPA_WEB_SEARCH_ENABLED=true、WCPA_SEARCH_PROVIDER=firecrawl。"
    elif config.provider != "firecrawl":
        message = "当前部署的搜索 provider 不是 firecrawl：请设置 WCPA_SEARCH_PROVIDER=firecrawl。"
    elif not user_allowed:
        message = "当前用户没有联网搜索权限。"
    elif not request_search_enabled:
        message = "本次请求未勾选联网搜索。"
    elif not tool_allowed:
        message = "当前工具不允许联网搜索。"
    else:
        message = "本次请求允许联网搜索；Firecrawl 支持可选密钥模式，未配置密钥时会先尝试 Keyless。"
    return SearchAuthorization(
        deployment_search_enabled=deployment_enabled,
        user_search_allowed=user_allowed,
        request_search_enabled=request_search_enabled,
        tool_search_allowed=tool_allowed,
        provider=config.provider if config.provider else None,
        message=message,
    )
