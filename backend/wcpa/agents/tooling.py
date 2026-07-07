"""Agent tools: local project knowledge snippets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from wcpa.shared.paths import DOCS_DIR, PROJECT_ROOT


@dataclass(frozen=True)
class ToolEvidence:
    tool: str
    query: str
    results: list[dict[str, Any]]


class KnowledgeBaseTool:
    """Reads curated project docs and requirements as agent knowledge."""

    DEFAULT_FILES = [
        DOCS_DIR / "planning" / "世界杯冠军预测Agent完整项目落地要求说明书.md",
        DOCS_DIR / "architecture" / "Agent工作流.md",
        DOCS_DIR / "architecture" / "预测模型设计.md",
        DOCS_DIR / "references" / "数据源说明.md",
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
    # Web evidence is intentionally not gathered here. It is routed through the
    # backend Firecrawl evidence system, which enforces user opt-in, budgets,
    # persistence, and prompt-injection isolation.
    return evidence


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
