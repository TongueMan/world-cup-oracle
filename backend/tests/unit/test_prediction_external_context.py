"""External prediction context assembly tests."""

from __future__ import annotations

from wcpa.prediction.external_context import ExternalPredictionContextBuilder, _extract_web_match_winner


class FakeEnvironmentService:
    def get_match_environment(self, match_id: str) -> dict:
        return {
            "match_id": match_id,
            "data_status": "partial",
            "summary": "场馆已确认；天气细节仍待确认。",
        }


class UnconfiguredOddsService:
    def get_match_odds(self, match: dict) -> dict:
        return {
            "provider": "api-football",
            "status": "unconfigured",
            "reason": "Missing WCPA_API_FOOTBALL_API_KEY.",
        }


class AvailableOddsService:
    def get_match_odds(self, match: dict) -> dict:
        return {
            "provider": "api-football",
            "status": "available",
            "fixtureId": 1001,
            "fetchedAt": "2026-07-14T10:00:00Z",
            "sourceUpdatedAt": "2026-07-14T09:50:00Z",
            "markets": [
                {
                    "bookmaker": "SampleBook",
                    "market": "Match Winner",
                    "outcomes": [
                        {"name": "Home", "odd": 2.0},
                        {"name": "Draw", "odd": 3.2},
                        {"name": "Away", "odd": 3.8},
                    ],
                }
            ],
        }


def test_unconfigured_odds_are_reported_without_market_component(monkeypatch):
    monkeypatch.setenv("WCPA_PREDICTION_WEB_EVIDENCE_ENABLED", "false")
    builder = ExternalPredictionContextBuilder(
        odds_service=UnconfiguredOddsService(),
        environment_service=FakeEnvironmentService(),
    )

    result = builder.build(_match(), "ARG", "FRA")

    assert result.context.odds == []
    assert "market_odds" in result.context.missing_fields
    assert any(item.status == "unconfigured" for item in result.source_statuses)


def test_available_odds_enter_prediction_context(monkeypatch):
    monkeypatch.setenv("WCPA_PREDICTION_WEB_EVIDENCE_ENABLED", "false")
    builder = ExternalPredictionContextBuilder(
        odds_service=AvailableOddsService(),
        environment_service=FakeEnvironmentService(),
    )

    result = builder.build(_match(), "ARG", "FRA")

    assert len(result.context.odds) == 1
    assert "market_odds" not in result.context.missing_fields
    assert any(item.status == "available" for item in result.source_statuses)


def test_complete_web_moneyline_is_parsed_without_inventing_missing_outcomes():
    text = "Moneyline: ENG +175, Draw +180, ARG +195"

    parsed = _extract_web_match_winner(text, {"eng", "england"}, {"arg", "argentina"})

    assert parsed == (2.75, 2.8, 2.95)
    assert _extract_web_match_winner("England +175", {"england"}, {"argentina"}) is None


def _match() -> dict:
    return {
        "match_id": "SF-1",
        "stage": "SF",
        "home_team_id": "ARG",
        "away_team_id": "FRA",
        "home_team_raw": "Argentina",
        "away_team_raw": "France",
    }
