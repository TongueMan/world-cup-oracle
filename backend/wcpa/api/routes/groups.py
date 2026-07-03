"""小组积分路由。"""
from fastapi import APIRouter, HTTPException
from wcpa.api.deps import get_prediction_artifact

router = APIRouter()


@router.get("")
async def get_all_groups():
    """返回所有小组积分。"""
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    return [gs.model_dump() for gs in artifact.group_standings]


@router.get("/{group}")
async def get_group(group: str):
    """返回单个小组积分。"""
    artifact = get_prediction_artifact()
    if artifact is None:
        raise HTTPException(status_code=409, detail="No verified prediction found.")
    for gs in artifact.group_standings:
        if gs.group.upper() == group.upper():
            return gs.model_dump()
    raise HTTPException(status_code=404, detail=f"Group {group} not found.")
