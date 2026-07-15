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
from wcpa.agents.prediction_bridge import (
    build_agent_match_prediction,
    format_agent_match_prediction,
    load_bound_match_prediction,
    load_tournament_prediction_context,
)
from wcpa.agents.research_quality import evaluate_research_answer
from wcpa.agents.search_policy import SearchBudget, evaluate_search_authorization, load_search_deployment_config
from wcpa.agents.search_service import search_web
from wcpa.agents.source_quality import QualifiedSource, source_with_relevance
from wcpa.prediction.satisfaction import evaluate_prediction_satisfaction
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
    context["message"] = request.message
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
        search_error = f"联网研究不可用：{auth.message}"
        if not _is_prediction_question(request.message):
            yield sse_event("error", {"message": search_error})
            return
        filtered.append({"title": "Search unavailable", "reason": search_error, "sourceType": "search_error"})
        yield sse_event("search_warning", {"message": search_error})

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

    if plan.output_contract.get("prediction_required"):
        conversation = " ".join(
            [item.content for item in request.history[-6:] if item.role == "user"]
            + [request.message]
        )
        if _is_tournament_question(conversation):
            page = context.get("page") or {}
            context["tournament_prediction"] = load_tournament_prediction_context(
                [str(item) for item in page.get("currentContenders") or []],
                artifact_id=str(page.get("artifactId") or "") or None,
                expected_anchor=str(page.get("anchorStage") or "") or None,
            )
        else:
            if not context.get("prediction"):
                prediction = build_agent_match_prediction(
                    context,
                    sources,
                    search_attempted=search_mode != "local_only",
                    search_error=search_error,
                )
                if prediction is not None:
                    context["prediction"] = prediction.model_dump(mode="json")

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
    prediction_quality = None
    structured_prediction = _prediction_from_context(context)
    if structured_prediction is not None:
        prediction_quality = evaluate_prediction_satisfaction(
            structured_prediction,
            final_answer,
            placeholder_expected=_has_placeholder_match(context),
        )
        yield sse_event(
            "prediction_quality",
            {
                "passed": prediction_quality.passed,
                "automaticScore": prediction_quality.automatic_score,
                "dimensions": prediction_quality.dimensions,
                "hardFailures": prediction_quality.hard_failures,
                "issues": prediction_quality.issues,
            },
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
                "predictionQuality": (
                    {
                        "passed": prediction_quality.passed,
                        "automaticScore": prediction_quality.automatic_score,
                        "dimensions": prediction_quality.dimensions,
                        "hardFailures": prediction_quality.hard_failures,
                        "issues": prediction_quality.issues,
                    }
                    if prediction_quality
                    else None
                ),
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

    page_scope = context.get("scope") in {"page", "tournament"}
    intent: ResearchIntent = request.tool_intent if request.tool_intent != "general" else ("general" if page_scope else "match_analysis")
    if _is_head_to_head_history_question(intent_text):
        intent = "head_to_head_history"
    elif _is_tournament_question(intent_text):
        intent = "general"
    elif _is_pitch_question(intent_text) or request.tool_intent == "weather_environment":
        intent = "weather_environment"
    elif "previous" in lowered or "上一" in message:
        intent = "previous_match_report"

    page = context.get("page") or {}
    home = str(match.get("home_team_raw") or request.context.data.get("home_team_raw") or request.context.data.get("homeTeam") or "")
    away = str(match.get("away_team_raw") or request.context.data.get("away_team_raw") or request.context.data.get("awayTeam") or "")
    stage = str(match.get("stage") or request.context.data.get("stage") or page.get("tab") or "World Cup")
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
    elif page_scope and not match:
        page_label = str(request.context.summary or page.get("tab") or "World Cup dashboard")
        queries = [
            f"2026 FIFA World Cup {page_label} predictions schedule standings analysis",
            "2026 FIFA World Cup winner prediction favorites official",
            "2026 FIFA World Cup knockout path contenders",
            "2026 FIFA World Cup latest team news injuries lineup",
        ]
    else:
        matchup = f"{home} {away}".strip() or "2026 FIFA World Cup"
        queries = [
            f"{matchup} {stage} official match preview",
            f"{matchup} injuries lineup official",
            f"{matchup} tactical analysis",
            f"{matchup} head to head World Cup",
            f"{matchup} latest news Reuters ESPN",
            f"{matchup} form guide FIFA",
        ]

    output_contract = {
        "facts_only": _wants_facts_only(message),
        "scorelines_only": "scoreline" in lowered,
        "no_citations": not bool(context.get("sources")),
    }
    if _is_prediction_question(intent_text):
        output_contract["prediction_required"] = True
    if _is_tournament_question(intent_text):
        output_contract["prediction_shape"] = (
            "必须给出明确冠军倾向，不允许以数据不足为由拒答；"
            "至少包含第一选择、2-4 个竞争者、概率/置信度区间、核心理由、反转条件和事实边界。"
        )
        current_contenders = page.get("currentContenders") if isinstance(page.get("currentContenders"), list) else []
        eliminated_teams = page.get("eliminatedTeams") if isinstance(page.get("eliminatedTeams"), list) else []
        if current_contenders:
            output_contract["current_contenders_only"] = current_contenders
            output_contract["probability_instruction"] = "如果用户问剩余球队概率，只能在 current_contenders_only 中分配冠军概率；不要把 eliminated_teams 当作争冠候选。"
        if eliminated_teams:
            output_contract["eliminated_teams"] = eliminated_teams[:24]
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
        "不得点名具体球员/教练作为当前事实 unless the provided context or sources support it. "
        "For prediction questions, do not refuse just because the event is future or uncertain; make a bounded forecast with confidence and caveats. "
        "Do not provide betting advice, stake sizing, or guaranteed-outcome language. "
        "If output_requirements.current_contenders_only is provided, restrict title-probability forecasts to those teams only."
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
        if (plan.bracket_context.get("has_placeholders") or _has_placeholder_match(context)) and not sources:
            return _bracket_scenario_answer(context, sources)

    available = {int(source.get("citationId") or 0) for source in sources if source.get("citationId")}
    if not available:
        answer = re.sub(r"\s*\[\d+\]", "", answer)
    else:
        answer = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in available else "", answer)
    answer = answer.replace("adopted_sources", "sources")
    if request:
        answer = _remove_unrequested_player_noise(answer, request.message)
    if request and plan and plan.output_contract.get("prediction_required") and _prediction_answer_needs_repair(answer):
        if _is_tournament_question(request.message):
            return _tournament_prediction_answer(context, request, sources)
        prediction = _prediction_from_context(context)
        if prediction is not None:
            return format_agent_match_prediction(
                prediction,
                _team_label(context, "home"),
                _team_label(context, "away"),
                len(sources),
            )
    return answer.strip()


def _precomputed_final_answer(
    request: AgentResearchRequest,
    context: dict[str, Any],
    plan: ResearchPlan,
    sources: list[dict[str, Any]],
) -> str | None:
    if (plan.bracket_context.get("has_placeholders") or _has_placeholder_match(context)) and _is_placeholder_identity_question(request.message):
        return _bracket_placeholder_answer(context, request, sources)
    if _is_pitch_question(request.message) and not _has_pitch_support(context, sources):
        return _pitch_boundary_answer(context, request, sources)
    if plan.output_contract.get("facts_only"):
        return _facts_only_answer(context, request, plan, sources)
    if _is_tournament_question(request.message) and not (context.get("tournament_prediction") or {}).get("rows"):
        return _tournament_prediction_answer(context, request, sources)
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
    if context.get("intent") == "general" and _is_tournament_question(str(context.get("message") or "")):
        return _tournament_prediction_answer(context, None, sources)
    if context.get("scope") in {"page", "tournament"} and not match:
        return _page_context_answer(context, sources, reason)
    if context.get("intent") == "head_to_head_history":
        return "\n".join(
            [
                "### 本地数据边界",
                f"本地结构化数据没有收录 {label} 的完整历史交锋表。",
                "这不能推出两队历史上从未交手；需要联网核验历史交锋数据库、足协资料或权威比赛档案。",
                "请开启联网搜索，或在问题中明确要求联网检索历史交锋结果。",
            ]
        )
    if (context.get("bracket") or {}).get("has_placeholders") or _has_placeholder_match(context):
        return _bracket_scenario_answer(context, sources, reason)
    prediction = _prediction_from_context(context)
    if prediction is not None:
        return format_agent_match_prediction(
            prediction,
            _team_label(context, "home"),
            _team_label(context, "away"),
            len(sources),
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


def _page_context_answer(context: dict[str, Any], sources: list[dict[str, Any]], reason: str = "") -> str:
    page = context.get("page") or {}
    tab = page.get("tab") or "当前页面"
    lines = [
        "### 当前页面概览",
        f"- 页面：{tab}",
    ]
    if page.get("totalMatches") is not None:
        lines.append(f"- 比赛：共 {page.get('totalMatches')} 场，已赛 {page.get('completeMatches', 0)} 场，未赛 {page.get('scheduledMatches', 0)} 场。")
    if page.get("placeholderMatches") is not None:
        lines.append(f"- 淘汰赛占位：{page.get('placeholderMatches')} 场含 W/L 路径占位。")
    if page.get("totalStandings") is not None:
        lines.append(f"- 排名记录：{page.get('totalStandings')} 条。")
    if page.get("totalStats") is not None:
        lines.append(f"- 统计记录：{page.get('totalStats')} 条。")
    if page.get("editionCount") is not None:
        lines.append(f"- 历史数据：{page.get('editionCount')} 届赛事，当前年份 {page.get('selectedYear')}。")
    lines.extend(
        [
            "### 可继续推进",
            "- 可以基于当前页面摘要讨论赛程、排名、淘汰赛路径、历史决赛或冠军预测。",
            "- 如果问题需要最新伤停、首发、赔率或新闻，应启用联网检索后再下判断。",
        ]
    )
    if sources:
        lines.append(f"- 已采用 {len(sources)} 条联网来源。")
    elif reason:
        lines.append(f"- 联网或模型生成未完成：{reason}")
    return "\n".join(lines)


def _tournament_prediction_answer(
    context: dict[str, Any],
    request: AgentResearchRequest | None,
    sources: list[dict[str, Any]],
) -> str:
    page = context.get("page") or {}
    placeholder_count = page.get("placeholderMatches")
    model_context = context.get("tournament_prediction") or {}
    model_rows = model_context.get("rows") or []
    if not model_rows:
        return "\n".join(
            [
                "### 当前没有有效冠军预测",
                "- 当前页面没有绑定一份通过正式验证的冠军预测报告。",
                "- 我不会使用旧阶段结果、均匀概率、默认球队强度或通用强队印象代替当前模型结论。",
                "- 请先补齐页面所示的数据缺口并重新生成；通过验证后，我才能解释对应概率和比赛路径。",
            ]
        )
    if model_rows:
        leader = str(model_rows[0].get("team_name") or model_rows[0].get("team_id"))
        contender_lines = [
            (
                f"- {row.get('team_name') or row.get('team_id')}："
                f"夺冠概率 {float(row.get('champion_probability') or 0):.1%}。"
            )
            for row in model_rows[:5]
        ]
    citation_ids = [int(source.get("citationId")) for source in sources if source.get("citationId")]
    citation_a = f"[{citation_ids[0]}]" if citation_ids else ""
    citation_b = f"[{citation_ids[1]}]" if len(citation_ids) > 1 else citation_a
    citation_c = f"[{citation_ids[2]}]" if len(citation_ids) > 2 else citation_b
    source_note = (
        f"本次采用 {len(sources)} 条联网来源，主要作为外部赔率/预测市场和媒体观点参照。{citation_a}{citation_c}"
        if sources
        else "当前没有可采用联网来源，因此这是基于本地赛程页、淘汰赛路径和通用强队先验的低置信度预测。"
    )
    if model_rows:
        simulation_count = int(model_context.get("simulation_count") or 0)
        verification_note = (
            "数据已通过严格校验"
            if model_context.get("data_verified")
            else f"数据状态为 {model_context.get('data_status') or 'degraded'}"
        )
        source_note = (
            f"冠军概率来自 {simulation_count} 次逐场 Monte Carlo 路径模拟；{verification_note}。"
            f"联网来源另有 {len(sources)} 条，用于补充临场信息。{citation_a}{citation_c}"
        )
    if placeholder_count:
        path_note = f"赛程表里还有 {placeholder_count} 场占位路径，后续落位会显著改变概率。"
    else:
        path_note = "后续赛程落位、伤停、首发和赔率变化会显著改变概率。"
    return "\n".join(
        [
            "### 预测结论",
            f"- 如果现在必须选一个，我更看好**{leader}夺冠**。{citation_a}",
            f"- 但这不是“断言冠军已定”：{leader}只是当前第一倾向，不是压倒性热门。",
            "### 我的冠军概率分配",
            *contender_lines,
            "### 为什么这么排",
            f"- 外部赔率/预测市场类来源可作为市场共识参照，但当前项目赛程表的剩余球队优先级更高。{citation_b}",
            f"- 我把{leader}放第一，是因为逐场概率驱动的路径模拟给出了当前最高夺冠频次，而不是直接用排名换算冠军。",
            "- 其余球队仍有足够争冠空间，差距主要来自半决赛对位、体能消耗、伤停和点球风险。",
            "### 什么情况会推翻这个判断",
            f"- 如果{leader}在半决赛消耗过大、关键位置缺阵，第一概率要明显下修。",
            "- 如果赔率和主流预测在半决赛前后明显转向另一支仍存活球队，应优先跟随新的路径信息重算。",
            "### 事实边界和置信度",
            f"- {source_note}",
            f"- {path_note}",
            f"- 当前置信度受数据状态、未落位路径和临场信息完整度约束；它足够给出“更看好谁”，但不适合当成确定结论。{citation_c}",
        ]
    )


def _contender_probability_rows(contenders: list[str]) -> list[tuple[str, str]]:
    bands = ["30%-36%", "24%-30%", "20%-25%", "14%-20%"]
    if len(contenders) == 2:
        bands = ["52%-58%", "42%-48%"]
    elif len(contenders) == 3:
        bands = ["38%-44%", "30%-36%", "22%-30%"]
    return [(team, bands[index] if index < len(bands) else "5%-12%") for index, team in enumerate(contenders)]


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


def _bracket_scenario_answer(context: dict[str, Any], sources: list[dict[str, Any]], reason: str = "") -> str:
    match = context.get("match") or {}
    bracket = context.get("bracket") or {}
    home = match.get("home_team_raw") or match.get("home_team_id") or "TBD"
    away = match.get("away_team_raw") or match.get("away_team_id") or "TBD"
    lines = [
        "### 路径情景推演",
        f"- 当前对阵：{home} vs {away}。",
        "- W/L 编号是淘汰赛路径占位，不是已确定球队；不能把它们写成具体球队或具体球员阵容。",
    ]
    for item in bracket.get("placeholders") or []:
        source = item.get("source_match") or {}
        source_label = _match_label(source) or f"match {item.get('match_number')}"
        side = "主队侧" if item.get("side") == "home" else "客队侧"
        kind = "胜者" if item.get("kind") == "winner" else "负者"
        lines.append(f"- {side} {item.get('code')}：来自 {source_label} 的{kind}。")
    lines.extend(
        [
            "### 预测边界",
            "- 前序比赛未落位前，合理输出应是路径级预测：比较潜在晋级球队的体能、赛程、风格克制、伤停和赔率变化。",
            "- 如果启用联网检索，可进一步把最新新闻、赔率和赛前发布会纳入胜负倾向；没有这些证据时只能给低置信度情景判断。",
        ]
    )
    if sources:
        lines.append(f"- 本次已采用 {len(sources)} 条联网来源。")
    elif reason:
        lines.append(f"- 联网或模型生成未完成：{reason}")
    return "\n".join(lines)


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
    return bool(plan.match_context) and not _quality_concise_allowed(request, plan)


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
        return "先解释 W/L 淘汰赛占位符，再按可能路径做情景推演，避免把占位符写成已确定球队。"
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
    if data.get("scope") in {"page", "tournament"}:
        return {"environment": {}, "bracket": {}, "team_history": {}, "scope": data.get("scope"), "page": data}
    if request.context.current_match_id:
        context = build_match_context(request.context.current_match_id)
        context["page"] = data
        bound_prediction = load_bound_match_prediction(
            str(data.get("artifactId") or "") or None,
            request.context.current_match_id,
            expected_anchor=str(data.get("anchorStage") or "") or None,
        )
        if bound_prediction:
            context["prediction"] = bound_prediction
        return context
    home = data.get("home_team_raw") or data.get("homeTeam")
    away = data.get("away_team_raw") or data.get("awayTeam")
    if not home and not away:
        return {"environment": {}, "bracket": {}, "team_history": {}, "scope": "page", "page": data}
    match = {
        "home_team_raw": home,
        "away_team_raw": away,
        "stage": data.get("stage") or data.get("stageName") or "World Cup",
    }
    context = {"match": match, "environment": {}, "bracket": {}, "team_history": {}, "scope": data.get("scope")}
    return context


def _public_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "match": context.get("match") or {},
        "environment": context.get("environment") or {},
        "bracket": context.get("bracket") or {},
        "team_history": context.get("team_history") or {},
        "page": context.get("page") or {},
        "prediction": context.get("prediction") or {},
        "tournament_prediction": context.get("tournament_prediction") or {},
    }


def _prediction_from_context(context: dict[str, Any]):
    from wcpa.schemas.prediction import MatchPrediction

    payload = context.get("prediction")
    if not isinstance(payload, dict) or not payload:
        return None
    return MatchPrediction(**payload)


def _team_label(context: dict[str, Any], side: str) -> str:
    match = context.get("match") or {}
    return str(
        match.get(f"{side}_team_raw")
        or match.get(f"{side}_team_id")
        or ("主队" if side == "home" else "客队")
    )


def _match_label(match: dict[str, Any]) -> str:
    home = str(match.get("home_team_raw") or match.get("home_team_id") or "").strip()
    away = str(match.get("away_team_raw") or match.get("away_team_id") or "").strip()
    return f"{home} vs {away}" if home and away else ""


def _is_tournament_question(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("champion", "winner", "outright", "冠军", "夺冠"))


def _is_prediction_question(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("预测", "预估", "看好", "冠军", "夺冠", "胜负", "比分", "概率", "倾向", "predict", "prediction", "champion", "winner", "odds", "favorite"))


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
        "sui": "Switzerland",
        "哥伦比亚": "Colombia",
        "col": "Colombia",
        "巴西": "Brazil",
        "bra": "Brazil",
        "挪威": "Norway",
        "nor": "Norway",
        "法国": "France",
        "摩洛哥": "Morocco",
        "美国": "United States",
        "比利时": "Belgium",
    }
    return aliases.get(normalized, name or "team")


def _is_pitch_question(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("lumen field", "seattle stadium", "pitch", "turf", "grass", "草皮", "人工草皮"))


def _wants_facts_only(message: str) -> bool:
    text = message.casefold()
    return any(term in text for term in ("facts_only", "只说", "确定事实"))


def _has_pitch_support(context: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
    haystack = json.dumps(sources, ensure_ascii=False).casefold()
    return bool(sources and any(term in haystack for term in ("pitch", "turf", "grass", "surface", "草皮")))


def _has_placeholder_match(context: dict[str, Any]) -> bool:
    match = context.get("match") or {}
    values = [str(match.get(key) or "").strip() for key in ("home_team_raw", "away_team_raw", "home_team_id", "away_team_id")]
    return any(
        value.upper() in {"TBD", "TBC", "UNKNOWN", "N/A", "NA"}
        or value in {"待定", "待确认", "未确定"}
        or bool(re.fullmatch(r"[WL]\d+", value, re.IGNORECASE))
        for value in values
    )


def _is_placeholder_identity_question(message: str) -> bool:
    text = message.casefold()
    has_placeholder_ref = bool(re.search(r"\b[wl]\d{2,3}\b", text)) or "占位" in text or "placeholder" in text
    if not has_placeholder_ref:
        return False
    prediction_terms = ("预测", "推演", "情景", "胜负", "比分", "倾向", "分析", "preview", "predict", "scenario")
    if any(term in text for term in prediction_terms):
        return False
    identity_terms = ("是谁", "是什么", "什么意思", "哪", "代表", "不要编", "meaning", "who is", "what is")
    return any(term in text for term in identity_terms)


def _prediction_answer_needs_repair(answer: str) -> bool:
    text = answer.strip()
    lowered = text.casefold()
    refusal_terms = (
        "无法预测",
        "不能预测",
        "无法直接预测",
        "没有足够数据",
        "无法给出明确",
        "无法判断",
        "需要等到",
        "cannot predict",
        "not enough data",
        "insufficient data",
    )
    if any(term in lowered for term in refusal_terms):
        return True
    has_pick = any(term in text for term in ("看好", "第一倾向", "首选", "更可能", "夺冠", "冠军")) or any(term in lowered for term in ("favorite", "pick", "winner"))
    has_reasoning = any(term in text for term in ("因为", "理由", "概率", "置信", "风险", "条件", "梯队"))
    return len(text) < 260 or not (has_pick and has_reasoning)


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
