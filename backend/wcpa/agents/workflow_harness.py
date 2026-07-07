"""Product Agent workflow harness for traceable answer generation."""

from __future__ import annotations

import hashlib
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.schemas.agent_chat import AgentResearchRequest


@dataclass(frozen=True)
class EvidenceClaim:
    claim: str
    claim_type: str
    evidence: str = ""
    citation_id: int | None = None
    source_url: str = ""


@dataclass(frozen=True)
class EvidencePacket:
    sources: list[dict[str, Any]] = field(default_factory=list)
    claims: list[EvidenceClaim] = field(default_factory=list)
    unsupported_unknowns: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "source_count": len(self.sources),
            "claim_count": len(self.claims),
            "claims": [claim.__dict__ for claim in self.claims[:20]],
            "unsupported_unknowns": self.unsupported_unknowns[:20],
        }


@dataclass(frozen=True)
class StructuredAgentAnswer:
    confirmed_facts: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)
    predictions: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "confirmed_fact_count": len(self.confirmed_facts),
            "unknown_count": len(self.unknowns),
            "inference_count": len(self.inferences),
            "prediction_count": len(self.predictions),
            "citation_count": len(self.citations),
            "warning_count": len(self.warnings),
        }


class AgentWorkflowHarness:
    """Trace-first workflow harness used by online answers and offline evaluation."""

    def __init__(
        self,
        repository: PostgresRepository | None = None,
        workflow_name: str = "agent_research",
        run_id: str | None = None,
    ):
        self.repository = repository or PostgresRepository()
        self.workflow_name = workflow_name
        self.run_id = run_id or f"awf_{uuid.uuid4().hex}"
        self.started_at = datetime.now(timezone.utc)
        self._started_monotonic = time.monotonic()
        self._context_summary: dict[str, Any] = {}

    @classmethod
    def from_research_request(
        cls,
        request: AgentResearchRequest,
        repository: PostgresRepository | None = None,
    ) -> "AgentWorkflowHarness":
        harness = cls(repository=repository, workflow_name="agent_research")
        harness.start(
            session_id=str((request.context.data or {}).get("sessionId") or ""),
            match_id=request.context.current_match_id or str((request.context.data or {}).get("match_id") or ""),
            intent=request.tool_intent,
            search_mode=request.search_mode,
            message=request.message,
            input_payload=_safe_research_request_payload(request),
        )
        return harness

    def start(
        self,
        session_id: str,
        match_id: str,
        intent: str,
        search_mode: str,
        message: str,
        input_payload: dict[str, Any],
    ) -> None:
        self.repository.create_agent_workflow_run(
            run_id=self.run_id,
            workflow_name=self.workflow_name,
            session_id=session_id,
            match_id=match_id,
            intent=intent,
            search_mode=search_mode,
            message_hash=_hash_text(message),
            input_payload=input_payload,
            started_at=self.started_at,
        )

    @contextmanager
    def step(self, step_name: str, input_payload: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()
        output_payload: dict[str, Any] = {}
        try:
            yield output_payload
        except Exception as exc:
            self.record_step(
                step_name=step_name,
                status="failed",
                started_at=started_at,
                started_monotonic=started_monotonic,
                input_payload=input_payload or {},
                output_payload=output_payload,
                error_message=str(exc),
            )
            raise
        self.record_step(
            step_name=step_name,
            status="ok",
            started_at=started_at,
            started_monotonic=started_monotonic,
            input_payload=input_payload or {},
            output_payload=output_payload,
        )

    def record_step(
        self,
        step_name: str,
        status: str,
        started_at: datetime,
        started_monotonic: float,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        error_message: str = "",
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        latency_ms = int((time.monotonic() - started_monotonic) * 1000)
        self.repository.save_agent_workflow_step(
            run_id=self.run_id,
            step_name=step_name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            input_payload=input_payload,
            output_payload=_compact_payload(output_payload),
            error_message=error_message,
        )

    def set_context_summary(self, context: dict[str, Any]) -> None:
        self._context_summary = summarize_context(context)

    def finish(
        self,
        status: str,
        output_summary: dict[str, Any] | None = None,
        quality_payload: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        latency_ms = int((time.monotonic() - self._started_monotonic) * 1000)
        self.repository.finish_agent_workflow_run(
            run_id=self.run_id,
            status=status,
            finished_at=finished_at,
            latency_ms=latency_ms,
            context_summary=self._context_summary,
            output_summary=output_summary or {},
            quality_payload=quality_payload or {},
            error_message=error_message,
        )


def build_evidence_packet(sources: list[dict[str, Any]], unknowns: list[str] | None = None) -> EvidencePacket:
    claims: list[EvidenceClaim] = []
    for source in sources:
        citation_id = source.get("citationId")
        for claim in source.get("supportedClaims") or []:
            claims.append(
                EvidenceClaim(
                    claim=str(claim.get("claim") or ""),
                    claim_type=str(claim.get("type") or ""),
                    evidence=str(claim.get("evidence") or ""),
                    citation_id=int(citation_id) if citation_id else None,
                    source_url=str(source.get("url") or ""),
                )
            )
    return EvidencePacket(sources=sources, claims=claims, unsupported_unknowns=unknowns or [])


def summarize_context(context: dict[str, Any]) -> dict[str, Any]:
    match = context.get("match") or {}
    environment = context.get("environment") or {}
    venue = environment.get("venue") if isinstance(environment.get("venue"), dict) else {}
    bracket = context.get("bracket") or {}
    return {
        "match_id": match.get("match_id"),
        "stage": match.get("stage"),
        "status": match.get("status"),
        "home_team": match.get("home_team_raw") or match.get("home_team_id"),
        "away_team": match.get("away_team_raw") or match.get("away_team_id"),
        "kickoff_time": match.get("kickoff_time"),
        "venue_id": venue.get("venue_id"),
        "venue_name": venue.get("venue_name"),
        "environment_status": environment.get("data_status"),
        "has_placeholders": bracket.get("has_placeholders", False),
        "placeholder_count": len(bracket.get("placeholders") or []),
    }


def _safe_research_request_payload(request: AgentResearchRequest) -> dict[str, Any]:
    config = request.llm_config.model_dump(by_alias=True)
    if config.get("apiKey"):
        config["apiKey"] = "***"
    return {
        "message": request.message,
        "context": request.context.model_dump(by_alias=True),
        "history_count": len(request.history),
        "llmConfig": config,
        "searchMode": request.search_mode,
        "toolIntent": request.tool_intent,
    }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload)
    if len(text) <= 20000:
        return payload
    return {"truncated": True, "preview": text[:4000], "original_chars": len(text)}

