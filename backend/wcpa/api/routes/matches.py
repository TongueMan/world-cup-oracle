"""比赛详情路由。"""
from fastapi import APIRouter, HTTPException
from wcpa.api.deps import get_prediction_artifact

router = APIRouter()


@router.get("/{match_id}")
async def get_match(match_id: str):
    """返回单场预测详情，包含象征信号和 Agent 辩论。"""
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    prediction = None
    for pred in artifact.match_predictions:
        if pred.match_id == match_id:
            prediction = pred
            break
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found.")
    symbolic = next(
        (signal for signal in artifact.symbolic_signals if signal.match_id == match_id),
        None,
    )
    debate = next(
        (transcript for transcript in artifact.debate_transcripts if transcript.match_id == match_id),
        None,
    )
    return {
        "prediction": prediction.model_dump(),
        "symbolic_signal": symbolic.model_dump() if symbolic else None,
        "debate_transcript": debate.model_dump() if debate else None,
    }
