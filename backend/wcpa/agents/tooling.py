"""Agent tools: web evidence and local project knowledge snippets."""

from __future__ import annotations

import base64
import html as html_lib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from wcpa.shared.paths import DOCS_DIR, PROJECT_ROOT


@dataclass(frozen=True)
class ToolEvidence:
    tool: str
    query: str
    results: list[dict[str, Any]]


class WebSearchTool:
    """Lightweight Bing HTML search used to gather public evidence snippets."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> ToolEvidence:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 WorldCupOracle-Agent/1.0"},
                follow_redirects=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
            results = self._parse_results(response.text, limit)
        except Exception as exc:
            results = [{"title": "search_unavailable", "url": url, "snippet": str(exc)}]
        return ToolEvidence(tool="web_search", query=query, results=results)

    def _parse_results(self, html_text: str, limit: int) -> list[dict[str, str]]:
        blocks = re.findall(r'<li class="b_algo".*?</li>', html_text, flags=re.S)
        rows: list[dict[str, str]] = []
        for block in blocks:
            title_match = re.search(r"<h2.*?><a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", block, re.S)
            snippet_match = re.search(r"<p>(.*?)</p>", block, re.S)
            if not title_match:
                continue
            title = _strip_html(title_match.group(2))
            href = _decode_bing_url(html_lib.unescape(title_match.group(1)))
            snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
            if not title:
                continue
            rows.append({"title": title, "url": href, "snippet": snippet})
            if len(rows) >= limit:
                break
        return rows


class KnowledgeBaseTool:
    """Reads curated project docs and requirements as agent knowledge."""

    DEFAULT_FILES = [
        PROJECT_ROOT / "世界杯冠军预测Agent完整项目落地要求说明书.md",
        DOCS_DIR / "agent-workflow.md",
        DOCS_DIR / "model-design.md",
        DOCS_DIR / "data-sources.md",
    ]

    def retrieve(self, agent_name: str, limit_chars: int = 2200) -> ToolEvidence:
        chunks: list[dict[str, str]] = []
        keywords = _agent_keywords(agent_name)
        for path in self.DEFAULT_FILES:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = sum(text.lower().count(keyword.lower()) for keyword in keywords)
            if score <= 0 and agent_name not in {"Data Analyst Agent", "Judge Agent"}:
                continue
            chunks.append(
                {
                    "title": path.name,
                    "url": str(path),
                    "snippet": text[:limit_chars],
                }
            )
            if len(chunks) >= 3:
                break
        return ToolEvidence(tool="knowledge_base", query=agent_name, results=chunks)


def gather_agent_evidence(agent_name: str, context_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Gather tool evidence before prompting the model."""
    home = context_payload.get("home_team", {}).get("name") or context_payload.get("match", {}).get("home_team_id", "")
    away = context_payload.get("away_team", {}).get("name") or context_payload.get("match", {}).get("away_team_id", "")
    base_query = f"2026 FIFA World Cup {home} {away} team news lineup tactics"
    if agent_name == "Narrative Agent":
        base_query = f"2026 FIFA World Cup {home} {away} morale pressure news fans"
    elif agent_name == "Tactical Analyst Agent":
        base_query = f"2026 FIFA World Cup {home} {away} tactics lineup preview"
    elif agent_name == "Data Analyst Agent":
        base_query = f"{home} {away} FIFA ranking Elo recent form 2026 World Cup"

    evidence = [
        KnowledgeBaseTool().retrieve(agent_name).__dict__,
    ]
    if agent_name in {
        "Data Analyst Agent",
        "Tactical Analyst Agent",
        "Narrative Agent",
        "Judge Agent",
    }:
        evidence.append(WebSearchTool().search(base_query).__dict__)
    return evidence


def _strip_html(value: str) -> str:
    value = re.sub(r"<.*?>", "", value, flags=re.S)
    value = html_lib.unescape(value)
    value = value.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", value).strip()


def _decode_bing_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    encoded = query.get("u", [""])[0]
    if encoded.startswith("a1"):
        payload = encoded[2:]
        padding = "=" * (-len(payload) % 4)
        try:
            return base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        except Exception:
            return unquote(url)
    return unquote(url)


def _agent_keywords(agent_name: str) -> list[str]:
    if "Tactical" in agent_name:
        return ["战术", "攻防", "阵型", "克制"]
    if "Narrative" in agent_name:
        return ["叙事", "士气", "压力", "黑马"]
    if "Tarot" in agent_name:
        return ["塔罗", "象征", "转折"]
    if "I-Ching" in agent_name:
        return ["卦象", "易经", "险局"]
    if "Astrology" in agent_name:
        return ["星象", "四元素", "情绪"]
    return ["Agent", "预测", "数据", "模型"]
