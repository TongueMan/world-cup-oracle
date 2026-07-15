"""Published prediction, candidate and snapshot read APIs."""

from fastapi import APIRouter, HTTPException

from wcpa.api.deps import get_prediction_artifact, get_prediction_artifact_by_id
from wcpa.prediction_release import PredictionArtifactStore, PredictionReleaseService, PredictionRunInProgress
from wcpa.simulation.tournament_state import ANCHOR_ACTIVE_ROUND, ROUND_ORDER, build_tournament_state, is_concrete_team
from wcpa.worldcup.service import WorldCupDataService

router = APIRouter()
ALLOWED_ANCHORS = {"current", "pre_tournament", "post_group", "post_r32", "post_r16", "post_qf", "post_sf"}


@router.get("/stages")
async def get_prediction_stage_availability():
    schedule = WorldCupDataService().list_matches()
    team_ids = {
        str(team_id)
        for row in schedule
        for team_id in (row.get("home_team_id"), row.get("away_team_id"))
        if is_concrete_team(team_id)
    }
    live = build_tournament_state(schedule, team_ids, requested_anchor="current")
    current_index = ROUND_ORDER.index(live.active_round) if live.active_round in ROUND_ORDER else len(ROUND_ORDER)
    store = PredictionArtifactStore()
    rows = []
    for anchor in ("current", "pre_tournament", "post_group", "post_r32", "post_r16", "post_qf", "post_sf"):
        published = store.load_published(anchor)
        if published is not None:
            status = "available"
            message = "该阶段已保存正式预测报告。"
        elif anchor == "current":
            status = "generatable"
            message = "当前赛况可以立即重新生成预测。"
        else:
            expected = ANCHOR_ACTIVE_ROUND[anchor]
            expected_index = ROUND_ORDER.index(expected)
            if anchor == "pre_tournament":
                status = "not_captured"
                message = "赛前预测需要完整小组赛模拟，本页当前只支持小组赛后起点的冠军回放。"
            elif current_index < expected_index:
                status = "not_reached"
                message = "赛事尚未到达该预测起点。"
            elif current_index == expected_index and live.round_completed == 0:
                status = "generatable"
                message = "赛事正处于该阶段边界，可以生成并永久保存报告。"
            else:
                status = "generatable"
                message = "该历史起点可以按当时赛果边界重新生成；不会采用该阶段之后的赛果、新闻、赔率或伤停。"
        rows.append({"anchor": anchor, "status": status, "message": message})
    return rows


@router.get("/tournament")
async def get_tournament_prediction(anchor: str = "current"):
    if anchor not in ALLOWED_ANCHORS:
        raise HTTPException(status_code=422, detail="Unsupported prediction stage.")
    artifact = get_prediction_artifact(strict=True, anchor=anchor)
    if artifact is None:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "verified_prediction_unavailable",
                "message": "该阶段暂无通过验证的预测报告。",
            },
        )
    return artifact.model_dump(mode="json")


@router.get("/candidate")
async def get_candidate_prediction(anchor: str = "current"):
    if anchor not in ALLOWED_ANCHORS:
        raise HTTPException(status_code=422, detail="Unsupported prediction stage.")
    artifact = PredictionArtifactStore().load_candidate(anchor)
    if artifact is None:
        raise HTTPException(status_code=404, detail="No candidate prediction found.")
    return artifact.model_dump(mode="json")


@router.get("/snapshots")
async def list_prediction_snapshots():
    return [
        row
        for row in PredictionArtifactStore().list_snapshots()
        if get_prediction_artifact_by_id(str(row["artifact_id"])) is not None
    ]


@router.get("/snapshots/{artifact_id}")
async def get_prediction_snapshot(artifact_id: str):
    artifact = get_prediction_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Published snapshot {artifact_id} not found.")
    return artifact.model_dump(mode="json")


@router.get("/reports/{artifact_id}")
async def get_prediction_report(artifact_id: str):
    artifact = get_prediction_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Verified prediction report not found.")
    if artifact.prediction_report is None:
        raise HTTPException(status_code=404, detail=f"Report for artifact {artifact_id} not found.")
    return artifact.prediction_report.model_dump(mode="json")


@router.get("/artifacts/{artifact_id}/matches/{match_id}")
async def get_artifact_match(artifact_id: str, match_id: str):
    artifact = get_prediction_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Verified prediction version not found.")
    prediction = next((row for row in artifact.match_predictions if row.match_id == match_id), None)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found in artifact.")
    return {
        "artifact_id": artifact.artifact_id,
        "publication_status": artifact.publication_status,
        "data_verified": artifact.data_verified,
        "prediction": prediction.model_dump(mode="json"),
        "symbolic_signal": None,
        "debate_transcript": None,
    }


@router.post("/run")
async def run_prediction(seed: int = 42, mode: str = "professional", strict: bool = True, anchor: str = "current"):
    if seed != 42 or mode != "professional" or not strict or anchor not in ALLOWED_ANCHORS:
        raise HTTPException(status_code=422, detail="Published runs use a supported anchor, seed=42, mode=professional and strict=true.")
    try:
        return PredictionReleaseService().run(sync_first=True, anchor=anchor)
    except PredictionRunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _published_or_candidate():
    artifact = get_prediction_artifact(strict=True)
    if artifact is None:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "verified_prediction_unavailable",
                "message": "当前没有通过验证的冠军预测。",
            },
        )
    return artifact


@router.get("/champion-probabilities")
async def get_champion_probabilities():
    artifact = _published_or_candidate()
    return {
        "champion": artifact.rational_champion,
        "actual_champion": artifact.champion_team_id,
        "publication_status": artifact.publication_status,
        "probabilities": [item.model_dump(mode="json") for item in artifact.champion_probabilities],
    }


@router.get("/upsets")
async def get_upsets():
    return _published_or_candidate().upset_alerts


@router.get("/dark-horses")
async def get_dark_horses():
    return _published_or_candidate().dark_horses


@router.get("/sources")
async def get_data_sources():
    return [source.model_dump(mode="json") for source in _published_or_candidate().data_sources]
