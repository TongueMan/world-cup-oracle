"""WorldCup match environment API tests."""

from fastapi.testclient import TestClient

from wcpa.api.server import app


class FakeEnvironmentService:
    def list_venues(self):
        return {"items": [{"venue_id": "venue_1", "venue_name": "Venue 1", "country": "US", "source": "test"}]}

    def get_venue(self, venue_id):
        if venue_id == "missing":
            return {"data_status": "not_found", "reason": "venue not found"}
        return {"venue_id": venue_id, "venue_name": "Venue 1", "country": "US", "source": "test"}

    def get_match_environment(self, match_id):
        if match_id == "missing":
            return {
                "match_id": match_id,
                "data_status": "data_unavailable",
                "reason": "match venue mapping not found",
            }
        return {
            "match_id": match_id,
            "venue": {"venue_id": "venue_1", "venue_name": "Venue 1"},
            "weather": {"temperature_c": 29.0},
            "features": {"heat_stress_index": 0.5},
            "summary": "本场存在一定环境压力。",
            "data_status": "ok",
            "source": "test",
            "fetched_at": "2026-07-04T10:00:00Z",
        }

    def sync_venues(self):
        class Report:
            status = "ok"
            loaded_count = 1
            inserted_count = 1
            updated_count = 0
            skipped_count = 0
            errors = []

        return Report()

    def sync_match_venues(self):
        return self.sync_venues()

    def sync_venue_elevation(self):
        return self.sync_venues()

    def sync_match_weather(self):
        return self.sync_venues()

    def build_match_environment_features(self):
        return self.sync_venues()


def test_worldcup_environment_api_routes(monkeypatch):
    monkeypatch.setattr("wcpa.api.routes.worldcup.WorldCupEnvironmentService", FakeEnvironmentService)
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/api/worldcup/venues").json()["items"][0]["venue_id"] == "venue_1"
    assert client.get("/api/worldcup/venues/venue_1").json()["venue_id"] == "venue_1"
    assert client.get("/api/worldcup/venues/missing").json()["data_status"] == "not_found"

    env = client.get("/api/worldcup/matches/m1/environment").json()
    assert env["match_id"] == "m1"
    assert env["data_status"] == "ok"
    assert "features" in env

    missing = client.get("/api/worldcup/matches/missing/environment").json()
    assert missing["data_status"] == "data_unavailable"

    assert client.post("/api/worldcup/admin/sync-venues").json()["status"] == "ok"
    assert client.post("/api/worldcup/admin/sync-environment").json()["status"] == "ok"
