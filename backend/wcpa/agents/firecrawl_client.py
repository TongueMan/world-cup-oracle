"""Firecrawl REST client used only by the backend Agent evidence system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from wcpa.agents.search_policy import SearchBudget, load_search_deployment_config
from wcpa.shared.env import env_str


class FirecrawlConfigError(RuntimeError):
    """Raised when Firecrawl is requested but not configured."""


class FirecrawlCallError(RuntimeError):
    """Raised when Firecrawl returns an error or an invalid payload."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FirecrawlSearchResponse:
    search_id: str | None
    rows: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass(frozen=True)
class FirecrawlScrapeResponse:
    url: str
    title: str
    markdown: str
    metadata: dict[str, Any]
    raw: dict[str, Any]


class FirecrawlClient:
    def __init__(self, api_key: str | None = None, budget: SearchBudget | None = None):
        config = load_search_deployment_config()
        # Firecrawl Keyless can work for some deployments/endpoints, but real REST
        # calls may still return 403 depending on rollout, quota, or network policy.
        # Keep the product low-friction by allowing keyless, while honoring an
        # explicitly configured key when the operator provides one.
        configured_key = (
            api_key
            or env_str("WCPA_FIRECRAWL_API_KEY", "")
            or env_str("FIRECRAWL_API_KEY", "")
        )
        self.api_key = configured_key.strip()
        self.budget = budget or config.budget
        self.base_url = "https://api.firecrawl.dev/v2"

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def search(self, query: str, limit: int) -> FirecrawlSearchResponse:
        payload = {"query": query[:500], "limit": max(1, min(limit, self.budget.max_results))}
        data = self._post("/search", payload)
        rows = _extract_search_rows(data)
        search_id = data.get("id") if isinstance(data.get("id"), str) else None
        return FirecrawlSearchResponse(search_id=search_id, rows=rows, raw=data)

    def scrape(self, url: str) -> FirecrawlScrapeResponse:
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        data = self._post("/scrape", payload)
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        markdown = str(body.get("markdown") or "")[: self.budget.max_page_chars]
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        return FirecrawlScrapeResponse(
            url=str(metadata.get("sourceURL") or metadata.get("url") or url),
            title=str(metadata.get("title") or body.get("title") or ""),
            markdown=markdown,
            metadata=metadata,
            raw=data,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                headers=self.headers,
                json=payload,
                timeout=self.budget.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise FirecrawlCallError("Firecrawl request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            detail = _safe_error_detail(exc.response)
            if status_code == 402:
                message = "Firecrawl credits are exhausted or the account requires billing."
            elif status_code in {401, 403}:
                message = "Firecrawl authentication or access was rejected."
            elif status_code == 429:
                message = "Firecrawl rate limit was reached."
            else:
                message = f"Firecrawl returned HTTP {status_code}."
            if detail:
                message = f"{message} {detail}"
            raise FirecrawlCallError(message, status_code=status_code) from exc
        except httpx.HTTPError as exc:
            raise FirecrawlCallError("Firecrawl request failed.") from exc
        except ValueError as exc:
            raise FirecrawlCallError("Firecrawl returned invalid JSON.") from exc
        if isinstance(data, dict) and data.get("success") is False:
            raise FirecrawlCallError(str(data.get("error") or "Firecrawl request failed."))
        if not isinstance(data, dict):
            raise FirecrawlCallError("Firecrawl returned an unexpected payload.")
        return data


def _extract_search_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    payload = data.get("data")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = []
        for key in ("web", "news"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(row for row in value if isinstance(row, dict))
        return rows
    return []


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:240] if text else ""
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("error") or payload.get("message") or payload.get("detail")
    if not detail:
        return ""
    return str(detail)[:240]
