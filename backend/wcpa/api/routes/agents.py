"""Agent API routes."""

from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from wcpa.agents.chat import AgentChatError, sse_event, test_agent_provider, validate_chat_request
from wcpa.agents.agent_context_builder import AgentContextError
from wcpa.agents.match_tool_service import AgentToolError, run_match_tool
from wcpa.agents.providers import ProviderCallError, ProviderConfigError, provider_capabilities
from wcpa.agents.research_engine import stream_research_answer
from wcpa.agents.search import search_capability
from wcpa.api.deps import get_prediction_artifact
from wcpa.schemas.agent_chat import (
    AgentCapabilitiesResponse,
    AgentChatRequest,
    AgentMatchToolRequest,
    AgentMatchToolResponse,
    AgentProviderTestRequest,
    AgentProviderTestResponse,
    AgentResearchRequest,
)

router = APIRouter()

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
async def get_agent_capabilities():
    return AgentCapabilitiesResponse(
        providers=provider_capabilities(),
        search=search_capability(),
    )


@router.post("/providers/test", response_model=AgentProviderTestResponse)
async def test_provider(request: AgentProviderTestRequest):
    try:
        test_agent_provider(request)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderCallError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AgentProviderTestResponse(ok=True, message="模型连接可用。")


@router.post("/chat/stream")
async def chat_stream(request: AgentChatRequest):
    try:
        validate_chat_request(request)
    except (AgentChatError, ProviderConfigError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    research_request = AgentResearchRequest.model_validate(
        {
            "message": request.message,
            "context": request.context.model_dump(by_alias=True),
            "history": [item.model_dump() for item in request.history],
            "llmConfig": request.llm_config.model_dump(by_alias=True),
            "searchMode": "required" if request.llm_config.search_enabled else "local_only",
            "toolIntent": "general",
        }
    )
    return StreamingResponse(
        stream_research_answer(research_request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/research/stream")
async def research_stream(request: AgentResearchRequest):
    try:
        resolve_error = None
        if not request.llm_config.api_key.strip():
            resolve_error = "请先配置模型 API Key。"
        if resolve_error and request.search_mode != "local_only":
            raise ProviderConfigError(resolve_error)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        stream_research_answer(request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/matches/{match_id}/analyze", response_model=AgentMatchToolResponse)
async def analyze_match(match_id: str, request: AgentMatchToolRequest):
    return _run_match_tool_api(match_id, "analyze", request)


@router.post("/matches/{match_id}/report", response_model=AgentMatchToolResponse)
async def generate_match_report(match_id: str, request: AgentMatchToolRequest):
    return _run_match_tool_api(match_id, "report", request)


@router.post("/matches/{match_id}/search-news", response_model=AgentMatchToolResponse)
async def search_match_news(match_id: str, request: AgentMatchToolRequest):
    return _run_match_tool_api(match_id, "search-news", request)


@router.post("/matches/{match_id}/environment", response_model=AgentMatchToolResponse)
async def analyze_match_environment(match_id: str, request: AgentMatchToolRequest):
    return _run_match_tool_api(match_id, "environment", request)


@router.post("/matches/{match_id}/{tool_name}/stream")
async def match_tool_stream(match_id: str, tool_name: str, request: AgentMatchToolRequest):
    if tool_name not in {"analyze", "report", "search-news", "environment"}:
        raise HTTPException(status_code=404, detail="Unsupported Agent match tool.")
    return StreamingResponse(
        _stream_match_tool(match_id, tool_name, request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _run_match_tool_api(
    match_id: str,
    tool_name: str,
    request: AgentMatchToolRequest,
) -> AgentMatchToolResponse:
    try:
        result = run_match_tool(
            match_id=match_id,
            tool_name=tool_name,
            llm_config=request.llm_config,
            question=request.question,
        )
    except AgentContextError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent 工具运行失败，请查看后端日志。") from exc
    return AgentMatchToolResponse(**result.__dict__)


def _stream_match_tool(
    match_id: str,
    tool_name: str,
    request: AgentMatchToolRequest,
) -> Iterator[str]:
    if request.llm_config is None:
        yield sse_event("error", {"message": "请先配置模型 API Key。"})
        return
    intent_map = {
        "analyze": "match_analysis",
        "report": "pre_match_report",
        "search-news": "latest_news",
        "environment": "weather_environment",
    }
    research_request = AgentResearchRequest.model_validate(
        {
            "message": request.question or _default_match_question(tool_name),
            "context": {"currentMatchId": match_id},
            "history": [],
            "llmConfig": request.llm_config.model_dump(by_alias=True),
            "searchMode": "required" if request.llm_config.search_enabled else "local_only",
            "toolIntent": intent_map.get(tool_name, "match_analysis"),
        }
    )
    yield from stream_research_answer(research_request)
    return

    yield sse_event("metadata", {"matchId": match_id, "toolName": tool_name})
    yield sse_event("progress", {"message": "读取本地比赛数据"})
    try:
        result = run_match_tool(
            match_id=match_id,
            tool_name=tool_name,
            llm_config=request.llm_config,
            question=request.question,
        )
    except AgentContextError as exc:
        yield sse_event("error", {"message": str(exc)})
        return
    except AgentToolError as exc:
        yield sse_event("error", {"message": str(exc)})
        return
    except Exception:
        yield sse_event("error", {"message": "Agent 工具运行失败，请查看后端日志。"})
        return

    for message in result.progress[1:]:
        yield sse_event("progress", {"message": message})
    if result.status == "needs_confirmation":
        yield sse_event("confirmation_required", result.confirmation or {})
        yield sse_event("done", {"answer": result.answer, "status": result.status})
        return
    if result.sources:
        yield sse_event("sources", {"results": result.sources})
    for chunk in _answer_chunks(result.answer):
        yield sse_event("token", {"content": chunk})
    yield sse_event(
        "done",
        {
            "answer": result.answer,
            "status": result.status,
            "sources": result.sources,
            "diagnostics": result.diagnostics,
        },
    )


def _answer_chunks(answer: str, size: int = 24) -> Iterator[str]:
    for index in range(0, len(answer), size):
        yield answer[index : index + size]


def _default_match_question(tool_name: str) -> str:
    if tool_name == "search-news":
        return "请查找这场比赛的最新新闻。"
    if tool_name == "environment":
        return "请分析这场比赛的天气和场馆环境影响。"
    if tool_name == "report":
        return "请生成这场比赛的赛前报告。"
    return "请分析这场比赛。"


@router.get("/debate/{match_id}")
async def get_debate(match_id: str):
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    transcript = next(
        (item for item in artifact.debate_transcripts if item.match_id == match_id),
        None,
    )
    if transcript is None or not transcript.opinions:
        return {
            "match_id": match_id,
            "status": "unavailable",
            "message": "LLM Agent 尚未生成；不会使用规则兜底冒充智能体输出。",
        }
    return transcript.model_dump()


@router.post("/debate/match")
async def generate_debate(match_id: str):
    """Agent generation is allowed only for verified prediction artifacts."""
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return {
        "match_id": match_id,
        "status": "unavailable",
        "message": "按需 Agent 生成需要先接入并验证真实球队数据；当前不使用 fixture 兜底。",
    }
