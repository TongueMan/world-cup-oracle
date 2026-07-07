"""Persistence helpers for Agent web evidence runs."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from wcpa.data.repositories.postgres_repository import PostgresRepository


class EvidencePersistenceError(RuntimeError):
    """Raised when evidence must be persisted but no durable store is available."""


@dataclass(frozen=True)
class EvidenceSource:
    title: str
    url: str
    domain: str
    snippet: str
    source: str
    published_at: str | None = None
    source_quality_score: float = 0.0
    relevance_score: float = 0.0
    source_type: str = "media"
    adoption_reason: str = ""
    citation_id: int | None = None
    excerpt: str = ""

    def to_response(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "source": self.source,
            "publishedAt": self.published_at,
            "sourceQualityScore": self.source_quality_score,
            "relevanceScore": self.relevance_score,
            "sourceType": self.source_type,
            "adoptionReason": self.adoption_reason,
            "citationId": self.citation_id,
            "excerpt": self.excerpt,
        }


class EvidenceService:
    def __init__(self, repository: PostgresRepository | None = None):
        self.repository = repository or PostgresRepository()

    def require_persistence(self) -> None:
        if not self.repository.enabled:
            raise EvidencePersistenceError("联网搜索需要可用的 PostgreSQL，以便保存 run_id 和证据。")
        self.repository.init_schema()

    def find_cached_sources(
        self,
        match_id: str,
        tool_name: str,
        search_intent: str,
        ttl_seconds: int,
    ) -> tuple[str, list[EvidenceSource]] | None:
        if ttl_seconds <= 0 or not self.repository.enabled:
            return None
        run_id = self.repository.find_recent_success_agent_search_run(
            match_id=match_id,
            tool_name=tool_name,
            search_intent=search_intent,
            ttl_seconds=ttl_seconds,
        )
        if not run_id:
            return None
        rows = self.repository.load_agent_search_sources(run_id)
        return (
            run_id,
            [
                EvidenceSource(
                    title=row.get("title", ""),
                    url=row.get("url", ""),
                    domain=row.get("domain", ""),
                    snippet=row.get("snippet", ""),
                    source="firecrawl",
                    published_at=row.get("published_at"),
                    source_quality_score=float(row.get("source_quality_score") or 0.0),
                    relevance_score=float(row.get("raw_payload", {}).get("relevance_score") or 0.0)
                    if isinstance(row.get("raw_payload"), dict)
                    else 0.0,
                    source_type=str(row.get("raw_payload", {}).get("source_type") or "media")
                    if isinstance(row.get("raw_payload"), dict)
                    else "media",
                    adoption_reason=str(row.get("raw_payload", {}).get("adoption_reason") or "")
                    if isinstance(row.get("raw_payload"), dict)
                    else "",
                    citation_id=index,
                    excerpt=str(row.get("raw_payload", {}).get("excerpt") or "")
                    if isinstance(row.get("raw_payload"), dict)
                    else "",
                )
                for index, row in enumerate(rows, start=1)
            ],
        )

    def start_run(
        self,
        match_id: str,
        tool_name: str,
        search_intent: str,
        provider: str,
        search_enabled: bool,
        query_plan: dict[str, Any],
        session_id: str | None = None,
    ) -> tuple[str, float]:
        self.require_persistence()
        run_id = uuid.uuid4().hex
        started = time.perf_counter()
        self.repository.create_agent_search_run(
            run_id=run_id,
            session_id=session_id or "",
            match_id=match_id,
            tool_name=tool_name,
            search_intent=search_intent,
            provider=provider,
            search_enabled=search_enabled,
            query_plan=query_plan,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        return run_id, started

    def finish_run(
        self,
        run_id: str,
        status: str,
        started: float,
        error_message: str = "",
    ) -> None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.repository.finish_agent_search_run(
            run_id=run_id,
            status=status,
            error_message=error_message,
            finished_at=datetime.now(timezone.utc),
            latency_ms=latency_ms,
        )

    def save_result(
        self,
        run_id: str,
        query: str,
        rank: int,
        source: EvidenceSource,
        scrape_status: str,
        raw_payload: dict[str, Any],
    ) -> None:
        self.repository.save_agent_search_result(
            run_id=run_id,
            query=query,
            title=source.title,
            url=source.url,
            domain=source.domain,
            snippet=source.snippet,
            rank=rank,
            published_at=source.published_at,
            fetched_at=datetime.now(timezone.utc),
            scrape_status=scrape_status,
            source_quality_score=source.source_quality_score,
            raw_payload=raw_payload,
        )

    def save_snapshot(
        self,
        run_id: str,
        match_id: str,
        evidence_type: str,
        source: EvidenceSource,
        excerpt: str,
        confidence: float,
    ) -> None:
        self.repository.save_agent_evidence_snapshot(
            run_id=run_id,
            match_id=match_id,
            evidence_type=evidence_type,
            claim=source.snippet or source.title,
            source_url=source.url,
            source_title=source.title,
            source_excerpt=excerpt[:2000],
            confidence=confidence,
            extracted_at=datetime.now(timezone.utc),
        )
