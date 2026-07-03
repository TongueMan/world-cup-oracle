"""WorldCup structured API route tests."""

from fastapi.testclient import TestClient

from wcpa.api.server import app


class FakeWorldCupService:
    def list_matches(self, date_from=None, date_to=None, status=None, stage=None):
        return [
            {
                "match_id": "m1",
                "stage": stage or "R32",
                "status": status or "complete",
                "kickoff_time": "2026-06-30T01:00:00+08:00",
            }
        ]

    def get_match_detail(self, match_id):
        if match_id == "missing":
            return None
        return {"match_id": match_id, "status": "complete"}

    def get_bracket(self):
        return [{"match_id": "m1", "next_match_id": "m2"}]

    def get_standings(self):
        return [{"group_name": "A", "team_id": "MEX", "points": 9}]

    def get_sync_status(self):
        return {"last_status": "success", "parsed_count": 104, "source": "bing_sports_html_fragment"}

    def sync_worldcup_data(self):
        class Result:
            status = "success"
            fetched_count = 104
            parsed_count = 104
            inserted_count = 104
            updated_count = 0
            error_message = None
            raw_snapshot_dir = "data/knowledge/bing/raw/test"

        return Result()


def test_worldcup_api_routes(monkeypatch):
    monkeypatch.setattr("wcpa.api.routes.worldcup.WorldCupDataService", FakeWorldCupService)
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/api/worldcup/matches?status=complete&stage=R32").json()[0]["stage"] == "R32"
    assert client.get("/api/worldcup/matches/m1").json()["match_id"] == "m1"
    assert client.get("/api/worldcup/matches/missing").status_code == 404
    assert client.get("/api/worldcup/bracket").json()[0]["next_match_id"] == "m2"
    assert client.get("/api/worldcup/standings").json()[0]["team_id"] == "MEX"
    assert client.get("/api/worldcup/sync/status").json()["parsed_count"] == 104

    sync = client.post("/api/worldcup/admin/sync").json()
    assert sync["status"] == "success"
    assert sync["parsed_count"] == 104

