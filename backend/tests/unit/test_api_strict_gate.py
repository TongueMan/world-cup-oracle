"""预测 API 的缺数据降级回归测试。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from wcpa.api.server import app
from wcpa.schemas.artifact import DataQualityReport, DataSourceStatus, TournamentPrediction


def test_predict_tournament_returns_degraded_prediction_instead_of_409(monkeypatch):
    source_status = DataSourceStatus(
        source_key="bing_sports_schedule",
        status="ok",
        credibility="B",
        fetched_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        records=19,
        message="HTTP 200; extracted 19 matches.",
    )
    report = DataQualityReport(
        status="invalid",
        strict=True,
        invalid_records=[
            {
                "dataset": "teams",
                "id": "ARG",
                "reason": "missing_required_model_fields",
                "fields": ["fifa_rank", "elo_rating"],
            }
        ],
        source_statuses=[source_status],
        message="真实数据存在缺失字段，已执行低置信度预测。",
    )
    degraded_report = report.model_copy(update={"status": "degraded_prediction"})
    artifact = TournamentPrediction(
        champion_team_id="ARG",
        data_verified=False,
        data_quality_report=degraded_report,
    )

    class FakeReleaseService:
        def run(self, sync_first: bool = True, anchor: str = "current"):
            return {
                "run_id": "test-run",
                "publish_status": "candidate_only",
                "reason_codes": ["data_not_verified"],
                "candidate_artifact_id": "candidate-test",
                "published_artifact_id": None,
                "artifact": artifact.model_dump(mode="json"),
            }

    monkeypatch.setattr("wcpa.api.routes.predict.PredictionReleaseService", FakeReleaseService)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/predict/tournament?anchor=current&seed=42&mode=professional&precompute_agents=false&strict=true"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["publish_status"] == "candidate_only"
    assert body["artifact"]["data_quality_report"]["status"] == "degraded_prediction"
    assert body["artifact"]["data_quality_report"]["source_statuses"][0]["fetched_at"] == "2026-07-03T00:00:00Z"
    assert body["artifact"]["champion_team_id"] == "ARG"
