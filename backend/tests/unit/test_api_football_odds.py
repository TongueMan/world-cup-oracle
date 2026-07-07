"""API-Football odds integration tests."""

from __future__ import annotations

from typing import Any

from wcpa.agents.agent_context_builder import build_match_context
from wcpa.agents.match_analysis_inputs import build_match_data_coverage
from wcpa.agents.odds_service import ApiFootballOddsService


def test_api_football_odds_unconfigured_does_not_call_network(monkeypatch):
    monkeypatch.setenv("WCPA_API_FOOTBALL_ODDS_ENABLED", "true")
    monkeypatch.setenv("WCPA_API_FOOTBALL_API_KEY", "")
    monkeypatch.setenv("WCPA_API_FOOTBALL_KEY", "")
    monkeypatch.setenv("API_FOOTBALL_KEY", "")

    result = ApiFootballOddsService().get_match_odds({"match_id": "123"})

    assert result["provider"] == "api-football"
    assert result["status"] == "unconfigured"


def test_api_football_odds_compacts_fixture_odds(monkeypatch):
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "errors": [],
                "response": [
                    {
                        "fixture": {"id": 9876, "date": "2026-07-07T20:00:00+00:00"},
                        "league": {"id": 1, "name": "World Cup", "season": 2026},
                        "update": "2026-07-07T10:00:00+00:00",
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "SampleBook",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "2.10"},
                                            {"value": "Draw", "odd": "3.20"},
                                            {"value": "Away", "odd": "3.60"},
                                        ],
                                    },
                                    {
                                        "id": 5,
                                        "name": "Goals Over/Under",
                                        "values": [{"value": "Over 2.5", "odd": "1.90"}],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, url: str, params: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    monkeypatch.setenv("WCPA_API_FOOTBALL_ODDS_ENABLED", "true")
    monkeypatch.setenv("WCPA_API_FOOTBALL_API_KEY", "sk-test")
    monkeypatch.setenv("WCPA_API_FOOTBALL_DISCOVER_FIXTURE", "false")
    monkeypatch.setattr("wcpa.agents.odds_service.httpx.Client", FakeClient)

    result = ApiFootballOddsService().get_match_odds(
        {"match_id": "local", "metadata": {"api_football_fixture_id": 9876}}
    )

    assert calls[0]["url"].endswith("/odds")
    assert calls[0]["params"] == {"fixture": 9876}
    assert calls[0]["headers"] == {"x-apisports-key": "sk-test"}
    assert result["status"] == "available"
    assert result["fixtureId"] == 9876
    assert result["markets"][0]["bookmaker"] == "SampleBook"
    assert result["markets"][0]["outcomes"][0]["odd"] == 2.1
    assert result["markets"][0]["outcomes"][0]["impliedProbability"] == 0.4762


def test_agent_context_marks_odds_snapshot_available(monkeypatch):
    class FakeOddsService:
        def get_match_odds(self, match: dict[str, Any]) -> dict[str, Any]:
            return {
                "provider": "api-football",
                "status": "available",
                "fixtureId": 9876,
                "markets": [{"market": "Match Winner", "outcomes": []}],
            }

    monkeypatch.setattr("wcpa.agents.agent_context_builder.ApiFootballOddsService", FakeOddsService)

    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")
    coverage = build_match_data_coverage(context)

    assert context["odds"]["status"] == "available"
    assert "odds_snapshot" in coverage.available_fields
