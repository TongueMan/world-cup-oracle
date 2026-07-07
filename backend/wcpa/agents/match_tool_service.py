"""Match-scoped Agent tools: analyze, report, and latest news."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wcpa.agents.agent_answer_service import build_fallback_agent_answer, generate_agent_answer
from wcpa.agents.agent_context_builder import AgentContextError, build_match_context
from wcpa.agents.agent_search_planner import SearchPlan, build_search_plan
from wcpa.agents.evidence_service import EvidencePersistenceError, EvidenceService, EvidenceSource
from wcpa.agents.firecrawl_client import FirecrawlCallError, FirecrawlConfigError
from wcpa.agents.match_analysis_inputs import build_match_data_coverage
from wcpa.agents.match_resolution import match_summary, resolve_question_match
from wcpa.agents.providers import ProviderCallError, ProviderConfigError
from wcpa.agents.scrape_service import scrape_url
from wcpa.agents.source_quality import source_with_relevance
from wcpa.agents.search_policy import evaluate_search_authorization, load_search_deployment_config
from wcpa.agents.search_service import search_web
from wcpa.agents.workflow_harness import AgentWorkflowHarness, build_evidence_packet, summarize_context
from wcpa.schemas.agent_chat import AgentLLMConfig


class AgentToolError(RuntimeError):
    """Raised for user-facing Agent tool errors."""


@dataclass(frozen=True)
class AgentToolResult:
    answer: str
    sources: list[dict[str, Any]]
    run_id: str | None
    status: str
    confirmation: dict[str, Any] | None
    diagnostics: dict[str, Any] | None
    progress: list[str]
    used_search: bool
    search_allowed: bool
    search_intents: list[str]
    missing_local_fields: list[str]
    evidence_status: str


def run_match_tool(
    match_id: str,
    tool_name: str,
    llm_config: AgentLLMConfig | None,
    question: str = "",
    session_id: str | None = None,
) -> AgentToolResult:
    if tool_name not in {"analyze", "report", "search-news", "environment"}:
        raise AgentToolError("Unsupported Agent match tool.")

    workflow = AgentWorkflowHarness(workflow_name="agent_match_tool")
    workflow.start(
        session_id=session_id or "",
        match_id=match_id,
        intent=tool_name,
        search_mode="enabled" if llm_config and llm_config.search_enabled else "local_only",
        message=question,
        input_payload={
            "matchId": match_id,
            "toolName": tool_name,
            "question": question,
            "searchEnabled": bool(llm_config.search_enabled) if llm_config else False,
        },
    )
    progress = ["读取本地比赛数据"]
    try:
        with workflow.step("build_context", {"matchId": match_id}) as step:
            context = build_match_context(match_id)
            workflow.set_context_summary(context)
            step["context"] = summarize_context(context)
    except Exception as exc:
        workflow.finish("failed", error_message=str(exc))
        raise
    resolution = resolve_question_match(question, context)
    if resolution.conflicts_current:
        current_match = context.get("match") or {}
        workflow.finish(
            "needs_confirmation",
            output_summary={"requestedTeams": resolution.requested_team_ids},
        )
        return AgentToolResult(
            answer="你提到的球队和当前打开的比赛不一致。请先确认要分析哪一场。",
            sources=[],
            run_id=None,
            status="needs_confirmation",
            confirmation={
                "currentMatch": match_summary(current_match),
                "requestedTeams": resolution.requested_team_ids,
                "candidates": resolution.candidates,
            },
            diagnostics={
                "runId": None,
                "queryPlan": {},
                "searchedCount": 0,
                "adoptedCount": 0,
                "filteredCount": 0,
                "filteredSources": [],
            },
            progress=[*progress, "发现问题中的球队与当前比赛不一致"],
            used_search=False,
            search_allowed=False,
            search_intents=[],
            missing_local_fields=[],
            evidence_status="needs_confirmation",
        )
    progress.append("解析问题对象")
    with workflow.step("resolve_intent", {"question": question, "toolName": tool_name}) as step:
        coverage = build_match_data_coverage(context)
        step["available_fields"] = coverage.available_fields
        step["missing_local_fields"] = coverage.missing_local_fields
    deployment = load_search_deployment_config()
    request_search_enabled = bool(llm_config.search_enabled) if llm_config else False
    auth = evaluate_search_authorization(tool_name, request_search_enabled, session_id)
    plan = build_search_plan(tool_name, context, coverage, deployment.budget, question)

    if tool_name == "search-news" and not auth.can_search:
        workflow.finish("failed", error_message=auth.message)
        raise AgentToolError(auth.message)

    sources: list[EvidenceSource] = []
    filtered_sources: list[dict[str, Any]] = []
    run_id: str | None = None
    used_search = False
    search_error = ""
    searched_count = 0

    if auth.can_search and plan.queries:
        progress.append("检索权威来源")
        evidence = EvidenceService()
        cached = evidence.find_cached_sources(
            match_id=match_id,
            tool_name=tool_name,
            search_intent=plan.intent,
            ttl_seconds=deployment.budget.cache_ttl_seconds,
        )
        if cached:
            run_id, sources = cached
            used_search = True
            progress.append("复用缓存证据")
        else:
            started = 0.0
            try:
                run_id, started = evidence.start_run(
                    match_id=match_id,
                    tool_name=tool_name,
                    search_intent=plan.intent,
                    provider="firecrawl",
                    search_enabled=True,
                    query_plan={"queries": plan.queries, "missing_local_fields": plan.missing_local_fields},
                    session_id=session_id,
                )
                with workflow.step("retrieve_evidence", {"queries": plan.queries, "intent": plan.intent}) as step:
                    sources, filtered_sources, searched_count = _execute_search_plan(
                        run_id,
                        match_id,
                        context,
                        plan,
                        deployment.budget,
                        evidence,
                    )
                    step["evidence"] = build_evidence_packet(
                        [source.to_response() for source in sources]
                    ).to_summary()
                    step["filtered_count"] = len(filtered_sources)
                used_search = True
                progress.append("过滤低相关来源")
                status = "success" if sources else "partial"
                evidence.finish_run(run_id, status, started)
            except (EvidencePersistenceError, FirecrawlConfigError, FirecrawlCallError) as exc:
                search_error = str(exc)
                if run_id and started:
                    evidence.finish_run(run_id, "failed", started, search_error)
                if tool_name == "search-news":
                    workflow.finish("failed", error_message=search_error)
                    raise AgentToolError(f"联网搜索失败，未生成新闻结论：{search_error}") from exc
    elif tool_name == "search-news":
        workflow.finish("failed", error_message=auth.message)
        raise AgentToolError(auth.message)

    for index, source in enumerate(sources, start=1):
        sources[index - 1] = EvidenceSource(
            title=source.title,
            url=source.url,
            domain=source.domain,
            snippet=source.snippet,
            source=source.source,
            published_at=source.published_at,
            source_quality_score=source.source_quality_score,
            relevance_score=source.relevance_score,
            source_type=source.source_type,
            adoption_reason=source.adoption_reason,
            citation_id=index,
            excerpt=source.excerpt,
        )

    progress.append("生成回答")
    answer = ""
    try:
        with workflow.step("generate_answer", {"source_count": len(sources), "used_search": used_search}) as step:
            answer = generate_agent_answer(
                tool_name=tool_name,
                context=context,
                coverage=coverage,
                sources=sources,
                used_search=used_search,
                search_error=search_error,
                llm_config=llm_config,
            )
            step["answer_chars"] = len(answer)
    except (ProviderConfigError, ProviderCallError) as exc:
        with workflow.step("generate_fallback_answer", {"reason": str(exc)}) as step:
            answer = build_fallback_agent_answer(
                tool_name=tool_name,
                context=context,
                coverage=coverage,
                sources=sources,
                used_search=used_search,
                search_error=search_error,
                reason=str(exc),
            )
            step["answer_chars"] = len(answer)

    if search_error and tool_name in {"analyze", "report"}:
        answer = f"联网补充失败：{search_error}\n\n以下为本地数据版结果。\n\n{answer}"

    status = "degraded" if search_error else ("local_only" if not used_search else "ok")
    workflow.finish(
        status,
        output_summary={"answer_chars": len(answer), "source_count": len(sources)},
        quality_payload={"evidence_status": _evidence_status(used_search, sources, search_error)},
        error_message=search_error,
    )
    return AgentToolResult(
        answer=answer,
        sources=[source.to_response() for source in sources],
        run_id=run_id,
        status=status,
        confirmation=None,
        diagnostics={
            "runId": run_id,
            "queryPlan": {"queries": plan.queries, "intent": plan.intent},
            "searchedCount": searched_count or len(sources) + len(filtered_sources),
            "adoptedCount": len(sources),
            "filteredCount": len(filtered_sources),
            "filteredSources": filtered_sources[:10],
        },
        progress=progress,
        used_search=used_search,
        search_allowed=auth.can_search,
        search_intents=[plan.intent],
        missing_local_fields=coverage.missing_local_fields,
        evidence_status=_evidence_status(used_search, sources, search_error),
    )


def _execute_search_plan(
    run_id: str,
    match_id: str,
    context: dict[str, Any],
    plan: SearchPlan,
    budget,
    evidence: EvidenceService,
) -> tuple[list[EvidenceSource], list[dict[str, Any]], int]:
    collected: list[EvidenceSource] = []
    filtered: list[dict[str, Any]] = []
    searched_count = 0
    for query in plan.queries[: budget.max_queries_per_request]:
        search_result = search_web(query, budget=budget)
        for rank, qualified in enumerate(search_result.sources, start=1):
            searched_count += 1
            scrape_status = "not_scraped"
            excerpt = qualified.snippet
            raw_payload = {"search": qualified.raw}
            if rank <= budget.scrape_top_n:
                try:
                    scraped = scrape_url(qualified.url, budget)
                    scrape_status = scraped.status if scraped.markdown else "empty"
                    excerpt = scraped.markdown or qualified.snippet
                    if scraped.title and not qualified.title:
                        qualified = qualified.__class__(
                            title=scraped.title,
                            url=qualified.url,
                            domain=qualified.domain,
                            snippet=qualified.snippet,
                            published_at=qualified.published_at,
                            source_quality_score=qualified.source_quality_score,
                            raw=qualified.raw,
                            relevance_score=qualified.relevance_score,
                            source_type=qualified.source_type,
                            adoption_reason=qualified.adoption_reason,
                            excerpt=qualified.excerpt,
                        )
                    raw_payload["scrape"] = scraped.raw
                except (FirecrawlConfigError, FirecrawlCallError) as exc:
                    scrape_status = "failed"
                    raw_payload["scrape_error"] = str(exc)
            qualified = source_with_relevance(qualified, context, excerpt)
            raw_payload.update(
                {
                    "relevance_score": qualified.relevance_score,
                    "source_type": qualified.source_type,
                    "adoption_reason": qualified.adoption_reason,
                    "excerpt": qualified.excerpt,
                }
            )
            source = EvidenceSource(
                title=qualified.title,
                url=qualified.url,
                domain=qualified.domain,
                snippet=qualified.snippet,
                source="firecrawl",
                published_at=qualified.published_at,
                source_quality_score=qualified.source_quality_score,
                relevance_score=qualified.relevance_score,
                source_type=qualified.source_type,
                adoption_reason=qualified.adoption_reason,
                excerpt=qualified.excerpt,
            )
            evidence.save_result(run_id, query, rank, source, scrape_status, raw_payload)
            if source.relevance_score < 0.7 or source.source_type == "social":
                filtered.append(
                    {
                        "title": source.title,
                        "url": source.url,
                        "domain": source.domain,
                        "relevanceScore": source.relevance_score,
                        "reason": source.adoption_reason,
                    }
                )
                continue
            evidence.save_snapshot(run_id, match_id, plan.intent, source, excerpt, source.relevance_score)
            collected.append(source)
    collected.sort(key=lambda item: (item.relevance_score, item.source_quality_score), reverse=True)
    deduped: list[EvidenceSource] = []
    seen: set[str] = set()
    for source in collected:
        key = source.url or f"{source.domain}:{source.title}".casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped, filtered, searched_count


def _evidence_status(used_search: bool, sources: list[EvidenceSource], error: str) -> str:
    if error:
        return "search_failed"
    if not used_search:
        return "local_only"
    if sources:
        return "search_success"
    return "search_empty"
