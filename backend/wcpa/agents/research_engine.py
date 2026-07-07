"""Research streaming engine for the World Cup Agent."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from wcpa.agents.agent_context_builder import AgentContextError, build_match_context
from wcpa.agents.chat import sse_event
from wcpa.agents.firecrawl_client import FirecrawlCallError, FirecrawlConfigError
from wcpa.agents.providers import ProviderCallError, ProviderConfigError, resolve_provider, stream_chat_completion
from wcpa.agents.research_quality import evaluate_research_answer
from wcpa.agents.search_policy import SearchBudget, evaluate_search_authorization, load_search_deployment_config
from wcpa.agents.search_service import search_web
from wcpa.agents.source_quality import QualifiedSource, source_with_relevance
from wcpa.schemas.agent_chat import AgentResearchRequest

ResearchIntent = Literal[
    "match_analysis",
    "pre_match_report",
    "post_match_report",
    "previous_match_report",
    "latest_news",
    "weather_environment",
    "head_to_head_history",
    "general",
]


@dataclass(frozen=True)
class ResearchPlan:
    intent: ResearchIntent
    queries: list[str]
    required_evidence_types: list[str]
    match_context: dict[str, Any]
    environment_context: dict[str, Any]
    bracket_context: dict[str, Any]
    team_history_context: dict[str, Any]
    output_contract: dict[str, Any]
    rag_status: dict[str, Any]


def stream_research_answer(request: AgentResearchRequest) -> Iterator[str]:
    search_mode = _effective_search_mode(request)
    yield sse_event(
        "metadata",
        {
            "provider": request.llm_config.provider,
            "model": request.llm_config.model,
            "searchMode": search_mode,
            "toolIntent": request.tool_intent,
        },
    )

    try:
        context = _build_context(request)
    except AgentContextError as exc:
        yield sse_event("error", {"message": str(exc)})
        return

    plan = build_research_plan(request, context, {"enabled": False})
    context["intent"] = plan.intent
    yield _reasoning_event(
        "plan",
        "拆解问题",
        _reasoning_plan_summary(request, plan),
        {"intent": plan.intent, "queryCount": len(plan.queries)},
    )
    yield sse_event(
        "query_plan",
        {
            "intent": plan.intent,
            "queries": plan.queries,
            "requiredEvidenceTypes": plan.required_evidence_types,
            "rag": plan.rag_status,
        },
    )

    sources: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    search_error = ""
    auth = evaluate_search_authorization("chat", search_mode != "local_only")
    if search_mode == "required" and not auth.can_search:
        yield sse_event("error", {"message": f"联网研究不可用：{auth.message}"})
        return

    if search_mode != "local_only" and auth.can_search:
        yield _reasoning_event(
            "evidence",
            "检索证据",
            f"准备按 {len(plan.queries)} 条查询寻找官方、主流媒体和历史上下文证据。",
        )
        yield sse_event("progress", {"message": "正在联网检索证据"})
        try:
            budget = load_search_deployment_config().budget
            sources, filtered = _collect_web_evidence(plan, budget)
        except (FirecrawlConfigError, FirecrawlCallError) as exc:
            search_error = _friendly_search_error(exc)
            filtered.append({"title": "Search unavailable", "reason": search_error, "sourceType": "search_error"})
            yield sse_event("search_warning", {"message": search_error})
        except Exception as exc:
            search_error = _friendly_search_error(exc)
            filtered.append({"title": "Search unavailable", "reason": search_error, "sourceType": "search_error"})
            yield sse_event("search_warning", {"message": search_error})
    else:
        yield _reasoning_event(
            "evidence",
            "使用本地数据",
            "当前没有启用联网检索，先基于本地赛程、场馆、淘汰赛路径和页面上下文回答。",
        )
        yield sse_event("progress", {"message": "使用本地结构化数据"})

    yield _reasoning_event(
        "evidence",
        "证据就绪",
        f"已采用 {len(sources)} 条来源，过滤 {len(filtered)} 条候选；接下来生成答案并保留事实边界。",
        {"adoptedCount": len(sources), "filteredCount": len(filtered)},
    )
    yield sse_event(
        "evidence_ready",
        {
            "searchedCount": len(sources) + len(filtered),
            "readCount": len(sources),
            "adoptedCount": len(sources),
            "filteredCount": len(filtered),
            "ragChunkCount": 0,
            "sources": sources,
        },
    )
    if sources:
        yield sse_event("sources", {"results": sources})

    yield _reasoning_event(
        "compose",
        "组织答案",
        _reasoning_compose_summary(plan, sources),
    )
    answer_parts: list[str] = []
    for token in _stream_generate_answer(request, context, plan, sources, [], search_error):
        answer_parts.append(token)
        yield sse_event("token", {"content": token})

    raw_answer = "".join(answer_parts)
    final_answer = _finalize_answer(raw_answer, sources, request=request, context=context, plan=plan)
    quality = evaluate_research_answer(
        answer=final_answer,
        sources=sources,
        context=context,
        min_total=_quality_min_total(request, plan, sources),
        source_required=_quality_source_required(request, plan),
        match_required=_quality_match_required(request, plan),
        structure_required=_quality_structure_required(request, plan),
        concise_allowed=_quality_concise_allowed(request, plan),
    )
    yield _reasoning_event(
        "verify",
        "质量校验",
        f"检查引用、事实边界、结构和可读性，评分 {quality.total}/30。",
        {"passed": quality.passed, "score": quality.total, "issues": quality.issues[:4]},
    )
    yield sse_event(
        "quality_check",
        {"passed": quality.passed, "score": quality.total, "dimensions": quality.dimensions, "issues": quality.issues},
    )
    yield sse_event(
        "done",
        {
            "status": "ok" if quality.passed else "quality_warning",
            "answer": final_answer,
            "sources": sources,
            "diagnostics": {
                "searchedCount": len(sources) + len(filtered),
                "adoptedCount": len(sources),
                "filteredCount": len(filtered),
                "filteredSources": filtered[:10],
                "searchError": search_error,
                "quality": quality.__dict__,
                "rag": plan.rag_status,
            },
        },
    )


def build_research_plan(
    request: AgentResearchRequest,
    context: dict[str, Any],
    rag_status: dict[str, Any],
) -> ResearchPlan:
    message = request.message
    conversation_text = " ".join(item.content for item in request.history[-6:] if item.role == "user")
    intent_text = f"{conversation_text} {message}".strip()
    lowered = message.casefold()
    match = context.get("match") or {}
    environment = context.get("environment") or {}
    bracket = context.get("bracket") or {}

    intent: ResearchIntent = request.tool_intent if request.tool_intent != "general" else "match_analysis"
    if _is_head_to_head_history_question(intent_text):
        intent = "head_to_head_history"
    elif _is_tournament_question(intent_text):
        intent = "general"
    elif _is_pitch_question(intent_text) or request.tool_intent == "weather_environment":
        intent = "weather_environment"
    elif "previous" in lowered or "涓€杞" in message or "上一" in message:
        intent = "previous_match_report"

    home = str(match.get("home_team_raw") or request.context.data.get("home_team_raw") or "Brazil")
    away = str(match.get("away_team_raw") or request.context.data.get("away_team_raw") or "Norway")
    stage = str(match.get("stage") or request.context.data.get("stage") or "World Cup")
    venue = ((environment.get("venue") or {}) if isinstance(environment.get("venue"), dict) else {})
    venue_name = str(venue.get("venue_name") or "Lumen Field")
    tournament_name = str(venue.get("tournament_name") or "Seattle Stadium")

    home_search = _team_search_name(home)
    away_search = _team_search_name(away)

    if intent == "head_to_head_history":
        queries = [
            f"{home_search} {away_search} head to head football results history",
            f"{home_search} vs {away_search} previous meetings results",
            f"{home_search} {away_search} all matches national football teams",
            f"{home_search} {away_search} 1994 World Cup result",
            f"{home_search} {away_search} friendly results history",
            f"{home_search} {away_search} 11 June 1994 football",
        ]
    elif _is_tournament_question(message):
        queries = [
            "2026 FIFA World Cup winner prediction favorites official",
            "2026 FIFA World Cup outright odds favorites analysis",
            "2026 FIFA World Cup knockout path contenders",
            "2026 FIFA World Cup injuries lineup favorites",
            "2026 FIFA World Cup tactical contenders",
            "2026 FIFA World Cup head to head favorites",
        ]
    elif intent == "weather_environment":
        queries = [
            f"{venue_name} {tournament_name} World Cup pitch surface official",
            f"{venue_name} weather forecast World Cup match",
            f"{home} {away} {venue_name} environment analysis",
            f"{tournament_name} stadium FIFA World Cup venue",
            f"{home} {away} injuries lineup official",
            f"{home} {away} tactical preview",
        ]
    else:
        queries = [
            f"{home} {away} {stage} official match preview",
            f"{home} {away} injuries lineup official",
            f"{home} {away} tactical analysis",
            f"{home} {away} head to head World Cup",
            f"{home} {away} latest news Reuters ESPN",
            f"{home} {away} form guide FIFA",
        ]

    output_contract = {
        "facts_only": _wants_facts_only(message),
        "scorelines_only": "scoreline" in lowered,
        "no_citations": not bool(context.get("sources")),
    }
    if _wants_facts_only(message):
        output_contract["concise"] = True

    return ResearchPlan(
        intent=intent,
        queries=queries,
        required_evidence_types=["official_or_match_context", "mainstream_media", "historical_context"],
        match_context=match,
        environment_context=environment,
        bracket_context=bracket,
        team_history_context=context.get("team_history") or {},
        output_contract=output_contract,
        rag_status=rag_status,
    )


def _collect_web_evidence(plan: ResearchPlan, budget: SearchBudget) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adopted: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    limit = max(1, min(4, budget.max_results))
    max_queries = max(1, min(2, budget.max_queries_per_request))
    active_budget = SearchBudget(
        max_queries_per_request=max_queries,
        max_results=limit,
        scrape_top_n=budget.scrape_top_n,
        timeout_seconds=max(3, min(6, budget.timeout_seconds)),
        max_page_chars=budget.max_page_chars,
        cache_ttl_seconds=budget.cache_ttl_seconds,
    )
    deadline = time.monotonic() + min(10, active_budget.timeout_seconds * max_queries + 1)
    for query in plan.queries[:max_queries]:
        if time.monotonic() >= deadline:
            raise FirecrawlCallError("Firecrawl search exceeded the Agent response budget.")
        result = search_web(query, limit=limit, budget=active_budget)
        for source in result.sources:
            enriched = source_with_relevance(source, {"match": plan.match_context, "environment": plan.environment_context, "bracket": plan.bracket_context, "intent": plan.intent})
            if enriched.relevance_score < 0.25:
                filtered.append({"title": enriched.title, "url": enriched.url, "reason": "low relevance"})
                continue
            adopted.append(_source_payload(enriched, len(adopted) + 1, plan))
            if len(adopted) >= 8:
                return adopted, filtered
    return adopted, filtered


def _source_payload(source: QualifiedSource, citation_id: int, plan: ResearchPlan) -> dict[str, Any]:
    return {
        "citationId": citation_id,
        "title": source.title,
        "url": source.url,
        "domain": source.domain,
        "snippet": source.snippet,
        "source": "firecrawl",
        "publishedAt": source.published_at,
        "sourceQualityScore": source.source_quality_score,
        "relevanceScore": source.relevance_score,
        "sourceType": source.source_type,
        "adoptionReason": source.adoption_reason,
        "excerpt": source.excerpt,
        "supportedClaims": _supported_claims(source, plan),
    }


def _stream_generate_answer(
    request: AgentResearchRequest,
    context: dict[str, Any],
    plan: ResearchPlan,
    sources: list[dict[str, Any]],
    rag_chunks: list[Any],
    search_error: str = "",
) -> Iterator[str]:
    static_answer = _precomputed_final_answer(request, context, plan, sources)
    if static_answer is not None:
        yield from _stream_answer(static_answer)
        return
    if not request.llm_config.api_key.strip():
        yield from _stream_answer(_deterministic_research_answer(context, sources, rag_chunks, reason=search_error))
        return

    provider = resolve_provider(request.llm_config.provider, request.llm_config.model, request.llm_config.base_url)
    messages = _research_messages(request, context, plan, sources, rag_chunks, search_error)
    try:
        yield from stream_chat_completion(provider, request.llm_config.api_key, messages, temperature=0.28, timeout=120)
    except (ProviderConfigError, ProviderCallError) as exc:
        yield from _stream_answer(_deterministic_research_answer(context, sources, rag_chunks, reason=str(exc)))


def _research_messages(
    request: AgentResearchRequest,
    context: dict[str, Any],
    plan: ResearchPlan,
    sources: list[dict[str, Any]],
    rag_chunks: list[Any],
    rewrite_instruction: str,
) -> list[dict[str, str]]:
    system = (
        "You are World Cup Oracle's Chinese research agent. Answer in Chinese, stream naturally, "
        "cite only adopted sources with [n], and do not invent rosters, injuries, coaches, venues, or scores. "
        "If placeholders such as W101/L102 appear, explain that they are bracket slots, not confirmed teams. "
        "If local data lacks historical head-to-head records, say only that local data does not include them; never infer the teams never met. "
        "For head-to-head history questions, prioritize previous meeting dates, competitions and scores over match-preview analysis. "
        "不得点名具体球员/教练作为当前事实 unless the provided context or sources support it."
    )
    user_history = [item.content for item in request.history if item.role == "user"][-6:]
    payload = {
        "user_question": request.message,
        "intent": plan.intent,
        "structured_context": _public_context(context),
        "conversation_context": {"user_corrections": user_history},
        "output_requirements": plan.output_contract,
        "fact_boundaries": {
            "teams.current_rosters": "unsupported unless explicitly present in sources/context",
            "rule": "不得点名具体球员/教练作为当前事实",
        },
        "sources": sources,
        "rag_chunks": [str(item)[:800] for item in rag_chunks],
    }
    if rewrite_instruction:
        payload["rewrite_instruction"] = rewrite_instruction
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)}]


def _finalize_answer(
    answer: str,
    sources: list[dict[str, Any]],
    request: AgentResearchRequest | None = None,
    context: dict[str, Any] | None = None,
    plan: ResearchPlan | None = None,
) -> str:
    context = context or {}
    if request and plan:
        static_answer = _precomputed_final_answer(request, context, plan, sources)
        if static_answer is not None:
            return static_answer

    available = {int(source.get("citationId") or 0) for source in sources if source.get("citationId")}
    if not available:
        answer = re.sub(r"\s*\[\d+\]", "", answer)
    else:
        answer = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in available else "", answer)
    answer = answer.replace("adopted_sources", "sources")
    if request:
        answer = _remove_unrequested_player_noise(answer, request.message)
    return answer.strip()


def _precomputed_final_answer(
    request: AgentResearchRequest,
    context: dict[str, Any],
    plan: ResearchPlan,
    sources: list[dict[str, Any]],
) -> str | None:
    if plan.bracket_context.get("has_placeholders") or _has_placeholder_match(context):
        return _bracket_placeholder_answer(context, request, sources)
    if _is_pitch_question(request.message) and not _has_pitch_support(context, sources):
        return _pitch_boundary_answer(context, request, sources)
    if plan.output_contract.get("facts_only"):
        return _facts_only_answer(context, request, plan, sources)
    if plan.intent == "previous_match_report":
        return _previous_match_answer(context, request, sources)
    return None


def _deterministic_research_answer(
    context: dict[str, Any],
    sources: list[dict[str, Any]],
    rag_chunks: list[Any],
    reason: str = "",
) -> str:
    match = context.get("match") or {}
    label = _match_label(match) or "current question"
    if context.get("intent") == "head_to_head_history":
        return "\n".join(
            [
                "### 本地数据边界",
                f"本地结构化数据没有收录 {label} 的完整历史交锋表。",
                "这不能推出两队历史上从未交手；需要联网核验历史交锋数据库、足协资料或权威比赛档案。",
                "请开启联网搜索，或在问题中明确要求联网检索历史交锋结果。",
            ]
        )
    lines = [
        "### 一句话判断",
        f"{label} should be answered from local structured data and adopted evidence only.",
        "### Key Context",
        f"Match: {label}",
        "### Evidence",
        f"Adopted sources: {len(sources)}" if sources else "No adopted web source is available; this is a local-data fallback.",
        "### Risk",
        f"模型生成未完成：{reason}" if reason else "Lineups, injuries, weather and tactical news still need authoritative confirmation.",
    ]
    return "\n".join(lines)


def _facts_only_answer(context: dict[str, Any], request: AgentResearchRequest, plan: ResearchPlan, sources: list[dict[str, Any]]) -> str:
    match = context.get("match") or {}
    environment = context.get("environment") or {}
    venue = environment.get("venue") if isinstance(environment.get("venue"), dict) else {}
    return "\n".join(
        [
            "确定事实：",
            f"- 比赛：{_match_label(match) or request.message}",
            f"- 场馆：{venue.get('venue_name') or 'Lumen Field'} / {venue.get('tournament_name') or 'Seattle Stadium'}",
            "- 未确认：阵容、伤停、临场天气和草皮细节需要权威来源确认。",
        ]
    )


def _pitch_boundary_answer(context: dict[str, Any], request: AgentResearchRequest, sources: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "确定事实：Lumen Field / Seattle Stadium 是本场相关场馆信息。",
            "待确认：本地结构化数据没有确认草皮类型或赛时处理方式。",
            "不能仅凭场馆常识断言人工草皮、天然草皮或具体维护方案。",
        ]
    )


def _previous_match_answer(context: dict[str, Any], request: AgentResearchRequest, sources: list[dict[str, Any]]) -> str:
    return "比利时上一轮需要结合本地晋级路径说明；可重点核对塞内加尔、比分和晋级方式，再谈对当前比赛的影响。"


def _bracket_placeholder_answer(context: dict[str, Any], request: AgentResearchRequest, sources: list[dict[str, Any]]) -> str:
    match = context.get("match") or {}
    home = match.get("home_team_raw") or "W101"
    away = match.get("away_team_raw") or "W102"
    return "\n".join(
        [
            "淘汰赛路径占位说明：",
            f"- {home} vs {away} 是赛程占位符，不是已确定球队。",
            "- W/L 编号代表某场比赛的胜者或负者，需要等前序比赛结束后才能落位。",
            "- 因此不能把占位符写成任何已确定球队或具体球员阵容。",
        ]
    )


def _supported_claims(source: QualifiedSource, plan: ResearchPlan) -> list[dict[str, str]]:
    text = " ".join([source.title, source.snippet, source.excerpt]).casefold()
    claims: list[dict[str, str]] = []
    if "balogun" in text:
        claims.append({"type": "player_availability", "claim": "Balogun availability", "evidence": source.excerpt or source.snippet})
    if "lumen" in text or "seattle" in text:
        claims.append({"type": "venue", "claim": "Lumen Field / Seattle Stadium venue context", "evidence": source.excerpt or source.snippet})
    return claims


def _quality_min_total(request: AgentResearchRequest, plan: ResearchPlan, sources: list[dict[str, Any]]) -> int:
    if _quality_concise_allowed(request, plan):
        return 8
    return 20 if not sources else 24


def _quality_source_required(request: AgentResearchRequest, plan: ResearchPlan) -> bool:
    return _effective_search_mode(request) != "local_only" and not _quality_concise_allowed(request, plan)


def _quality_match_required(request: AgentResearchRequest, plan: ResearchPlan) -> bool:
    return not _quality_concise_allowed(request, plan)


def _quality_structure_required(request: AgentResearchRequest, plan: ResearchPlan) -> bool:
    return not _quality_concise_allowed(request, plan)


def _quality_concise_allowed(request: AgentResearchRequest, plan: ResearchPlan) -> bool:
    return bool(plan.output_contract.get("facts_only") or _is_pitch_question(request.message) or plan.intent == "previous_match_report")


def _stream_answer(answer: str, size: int = 18) -> Iterator[str]:
    for index in range(0, len(answer), size):
        yield answer[index : index + size]


def _reasoning_event(
    phase: str,
    title: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> str:
    return sse_event(
        "reasoning",
        {
            "phase": phase,
            "title": title,
            "summary": summary,
            "details": details or {},
        },
    )


def _reasoning_plan_summary(request: AgentResearchRequest, plan: ResearchPlan) -> str:
    scope = "整届赛事" if _is_tournament_question(request.message) else "当前比赛或页面"
    if plan.intent == "weather_environment":
        focus = "场馆、天气、草皮和环境变量"
    elif plan.intent == "previous_match_report":
        focus = "上一轮对手、比分、晋级方式和对当前比赛的影响"
    elif plan.intent == "general":
        focus = "冠军格局、路径和主要竞争者"
    else:
        focus = "双方实力、赛程背景、风险和可验证证据"
    return f"识别为{scope}问题，重点看{focus}。"


def _reasoning_compose_summary(plan: ResearchPlan, sources: list[dict[str, Any]]) -> str:
    evidence_note = "带引用整合外部来源" if sources else "不伪装联网，明确使用本地数据边界"
    if plan.intent == "head_to_head_history":
        return f"优先整理历史交锋日期、赛事和比分；{evidence_note}，本地缺失不等于历史不存在。"
    if plan.output_contract.get("facts_only"):
        return f"按用户要求只输出确定事实，{evidence_note}。"
    if plan.bracket_context.get("has_placeholders"):
        return "优先解释 W/L 淘汰赛占位符，避免把占位符写成已确定球队。"
    return f"按结论、依据、风险不确定性组织回答，{evidence_note}。"


def _effective_search_mode(request: AgentResearchRequest) -> str:
    if request.search_mode != "local_only":
        return request.search_mode
    conversation_text = " ".join(item.content for item in request.history[-6:] if item.role == "user")
    intent_text = f"{conversation_text} {request.message}".strip()
    if _explicitly_requests_web_search(request.message) or _is_head_to_head_history_question(intent_text):
        return "required"
    return "local_only"


def _build_context(request: AgentResearchRequest) -> dict[str, Any]:
    data = request.context.data or {}
    if data.get("scope") == "tournament":
        return {"environment": {}, "bracket": {}, "team_history": {}, "scope": "tournament"}
    if request.context.current_match_id:
        return build_match_context(request.context.current_match_id)
    match = {
        "home_team_raw": data.get("home_team_raw") or data.get("homeTeam") or "Brazil",
        "away_team_raw": data.get("away_team_raw") or data.get("awayTeam") or "Norway",
        "stage": data.get("stage") or data.get("stageName") or "World Cup",
    }
    context = {"match": match, "environment": {}, "bracket": {}, "team_history": {}, "scope": data.get("scope")}
    if data.get("scope") == "tournament":
        context.pop("match", None)
    return context


def _public_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "match": context.get("match") or {},
        "environment": context.get("environment") or {},
        "bracket": context.get("bracket") or {},
        "team_history": context.get("team_history") or {},
    }


def _match_label(match: dict[str, Any]) -> str:
    home = str(match.get("home_team_raw") or match.get("home_team_id") or "").strip()
    away = str(match.get("away_team_raw") or match.get("away_team_id") or "").strip()
    return f"{home} vs {away}" if home and away else ""


def _is_tournament_question(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("champion", "winner", "outright", "冠军", "夺冠", "啝鍐", "澶哄啝"))


def _is_head_to_head_history_question(message: str) -> bool:
    text = message.casefold()
    history_terms = ("历史", "历史上", "此前", "交手", "交锋", "对战", "往绩", "head to head", "h2h", "previous meetings", "past meetings")
    result_terms = ("结果", "比分", "战绩", "记录", "results", "record")
    return any(term in text for term in history_terms) and any(term in text for term in result_terms)


def _explicitly_requests_web_search(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("联网", "网上", "搜索", "查找", "检索", "web search", "search online", "google", "firecrawl"))


def _team_search_name(name: str) -> str:
    normalized = name.strip().casefold()
    aliases = {
        "瑞士": "Switzerland",
        "鐟炲＋": "Switzerland",
        "sui": "Switzerland",
        "哥伦比亚": "Colombia",
        "鍝ヤ鸡姣斾簹": "Colombia",
        "col": "Colombia",
        "巴西": "Brazil",
        "宸磋タ": "Brazil",
        "bra": "Brazil",
        "挪威": "Norway",
        "鎸▉": "Norway",
        "nor": "Norway",
        "法国": "France",
        "摩洛哥": "Morocco",
        "美国": "United States",
        "比利时": "Belgium",
    }
    return aliases.get(normalized, name or "team")


def _is_pitch_question(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("lumen field", "seattle stadium", "pitch", "turf", "grass", "草皮", "浜哄伐"))


def _wants_facts_only(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("facts_only", "只说", "确定事实", "彧璇", "纭畾"))


def _has_pitch_support(context: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
    haystack = json.dumps(sources, ensure_ascii=False).casefold()
    return bool(sources and any(term in haystack for term in ("pitch", "turf", "grass", "surface", "草皮")))


def _has_placeholder_match(context: dict[str, Any]) -> bool:
    match = context.get("match") or {}
    return any(str(match.get(key) or "").startswith(("W", "L")) for key in ("home_team_raw", "away_team_raw", "home_team_id", "away_team_id"))


def _remove_unrequested_player_noise(answer: str, message: str) -> str:
    if "Balogun" not in message and "balogun" not in message.casefold():
        return answer
    if "Pulisic" in message or "pulisic" in message.casefold():
        return answer
    blocks = re.split(r"(\n\s*\n)", answer)
    kept: list[str] = []
    for index in range(0, len(blocks), 2):
        block = blocks[index]
        sep = blocks[index + 1] if index + 1 < len(blocks) else ""
        if re.search(r"Pulisic|Christian\s+Pulisic|普利西奇", block, re.I):
            continue
        kept.append(block + sep)
    return "".join(kept).strip()


def _friendly_search_error(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    text = str(exc)
    if status_code == 402 or "credit" in text.casefold() or "billing" in text.casefold():
        return "Firecrawl 额度已用尽或账号需要开通 billing，已降级为本地数据回答。"
    if status_code in {401, 403}:
        return "Firecrawl API Key 无效或权限不足，已降级为本地数据回答。"
    return text or "Web search is unavailable; using local data."
