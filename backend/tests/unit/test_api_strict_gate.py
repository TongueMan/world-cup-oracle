"""API strict data gate regression tests."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from wcpa.api.server import app
from wcpa.data.real_dataset import DataUnavailableError
from wcpa.schemas.artifact import DataQualityReport, DataSourceStatus


def test_predict_tournament_returns_json_409_for_data_unavailable(monkeypatch):
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
        message="真实数据存在缺失字段，正式预测已停止。",
    )

    class FakeEngine:
        def __init__(self, seed: int = 42, mode: str = "balanced"):
            self.seed = seed
            self.mode = mode

        def run_and_save(self, precompute_agents: bool = True, strict: bool = True):
            raise DataUnavailableError(report)

    monkeypatch.setattr("wcpa.api.routes.predict.OracleTournamentEngine", FakeEngine)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/predict/tournament?seed=42&mode=balanced")

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["status"] == "invalid"
    assert body["detail"]["source_statuses"][0]["fetched_at"] == "2026-07-03T00:00:00Z"
    assert body["detail"]["message"] == "真实数据存在缺失字段，正式预测已停止。"
