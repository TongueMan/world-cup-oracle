"""Agent debate API routes."""

from fastapi import APIRouter, HTTPException

from wcpa.api.deps import get_prediction_artifact

router = APIRouter()


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
