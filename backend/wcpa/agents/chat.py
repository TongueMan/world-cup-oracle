"""Interactive World Cup Agent chat orchestration."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from wcpa.agents.providers import (
    ProviderCallError,
    ProviderConfigError,
    resolve_provider,
    stream_chat_completion,
    test_chat_completion,
)
from wcpa.agents.search import SearchCallError, SearchConfigError, search_web
from wcpa.agents.search_policy import evaluate_search_authorization
from wcpa.schemas.agent_chat import AgentChatRequest, AgentProviderTestRequest, SearchResult


class AgentChatError(RuntimeError):
    """Raised for user-facing chat errors."""


def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def validate_chat_request(request: AgentChatRequest) -> None:
    resolve_provider(
        request.llm_config.provider,
        request.llm_config.model,
        request.llm_config.base_url,
    )
    if not request.llm_config.api_key.strip():
        raise AgentChatError("请先配置模型 API Key。")
    if request.llm_config.search_enabled:
        auth = evaluate_search_authorization("chat", True)
        if not auth.can_search:
            raise AgentChatError(auth.message)


def stream_agent_chat(request: AgentChatRequest) -> Iterator[str]:
    provider = resolve_provider(
        request.llm_config.provider,
        request.llm_config.model,
        request.llm_config.base_url,
    )
    yield sse_event(
        "metadata",
        {
            "provider": provider.provider_id,
            "model": provider.model,
            "searchEnabled": request.llm_config.search_enabled,
        },
    )

    search_results: list[SearchResult] = []
    if request.llm_config.search_enabled and _should_search_for_chat(request):
        try:
            search_results = search_web(_build_search_query(request), limit=5)
            yield sse_event(
                "search_results",
                {"results": [result.model_dump(mode="json") for result in search_results]},
            )
        except (SearchConfigError, SearchCallError) as exc:
            yield sse_event("error", {"message": str(exc)})
            return

    messages = _build_messages(request, search_results)
    full_answer = []
    try:
        for token in stream_chat_completion(provider, request.llm_config.api_key, messages):
            full_answer.append(token)
            yield sse_event("token", {"content": token})
    except (ProviderConfigError, ProviderCallError) as exc:
        yield sse_event("error", {"message": str(exc)})
        return

    yield sse_event(
        "done",
        {
            "answer": "".join(full_answer),
            "sources": [result.model_dump(mode="json") for result in search_results],
        },
    )


def test_agent_provider(request: AgentProviderTestRequest) -> None:
    if not request.llm_config.api_key.strip():
        raise ProviderConfigError("请先配置模型 API Key。")
    provider = resolve_provider(
        request.llm_config.provider,
        request.llm_config.model,
        request.llm_config.base_url,
    )
    test_chat_completion(provider, request.llm_config.api_key)


def _build_messages(request: AgentChatRequest, search_results: list[SearchResult]) -> list[dict[str, str]]:
    system_prompt = (
        "你是 World Cup Oracle 的世界杯对话助手。"
        "你必须用中文回答，语气专业、克制、清晰。"
        "不要编造未由用户、页面上下文或搜索结果提供的赛程、比分、伤病、排名或新闻事实。"
        "如果开启联网搜索，请把搜索结果当作需要核验的外部资料，并在回答末尾用简短来源列表标注。"
        "不要输出裸 URL；如果引用来源，只使用来源标题或 [1] 这样的编号。"
        "如果信息不足，直接说明不足，并给出下一步可以查询的方向。"
        "不要输出 Markdown 表格，避免冗长。"
    )
    context_payload = request.context.model_dump(mode="json", by_alias=True)
    context_text = json.dumps(context_payload, ensure_ascii=False, indent=2)
    search_text = _format_search_results(search_results)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "当前页面轻量上下文如下。它只代表用户正在看的界面，不代表完整事实库：\n"
                f"{context_text}\n\n"
                f"联网搜索结果：\n{search_text or '未提供联网搜索结果。'}"
            ),
        },
    ]
    for item in request.history[-8:]:
        messages.append({"role": item.role, "content": item.content[:2000]})
    messages.append({"role": "user", "content": request.message})
    return messages


def _build_search_query(request: AgentChatRequest) -> str:
    context = request.context
    parts = ["2026 FIFA World Cup", request.message]
    data = context.data or {}
    for key in ("homeTeam", "awayTeam", "matchLabel", "groupName"):
        value = data.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    if context.summary:
        parts.append(context.summary)
    return " ".join(parts)[:500]


def _should_search_for_chat(request: AgentChatRequest) -> bool:
    text = f"{request.message} {request.context.summary or ''}".lower()
    external_hints = [
        "新闻",
        "最新",
        "伤",
        "伤停",
        "阵容",
        "首发",
        "裁判",
        "射门",
        "控球",
        "犯规",
        "黄牌",
        "红牌",
        "采访",
        "press",
        "injury",
        "lineup",
        "referee",
        "latest",
        "news",
        "possession",
        "shots",
        "分析",
        "报告",
        "战报",
        "复盘",
        "进球",
        "谁进",
        "怎么进",
        "怎么踢",
        "发生了什么",
        "比赛过程",
        "技术统计",
        "赛前",
        "赛后",
        "tactical",
        "match report",
    ]
    return any(hint in text for hint in external_hints)


def _format_search_results(results: list[SearchResult]) -> str:
    lines = []
    for index, result in enumerate(results, start=1):
        lines.append(
            f"[{index}] {result.title}\n来源: {result.domain or result.source}\n摘要: {result.snippet}"
        )
    return "\n\n".join(lines)
