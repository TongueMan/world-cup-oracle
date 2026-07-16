"""比赛详情路由。"""
from fastapi import APIRouter, HTTPException
from wcpa.api.deps import get_prediction_artifact

router = APIRouter()


@router.get("/{match_id}")
async def get_match(match_id: str):
    """返回已验证预测产物中的单场概率详情。"""
    artifact = get_prediction_artifact(strict=True)
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    prediction = None
    for pred in artifact.match_predictions:
        if pred.match_id == match_id:
            prediction = pred
            break
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found.")
    return {
        "artifact_id": artifact.artifact_id,
        "publication_status": artifact.publication_status,
        "data_verified": artifact.data_verified,
        "prediction": prediction.model_dump(),
    }
