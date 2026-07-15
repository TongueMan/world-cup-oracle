"""Agent 到多源预测内核的桥接测试。"""

import pytest

from wcpa.agents.prediction_bridge import (
    build_agent_match_prediction,
    format_agent_match_prediction,
)


def test_agent_bridge_uses_api_odds_and_local_team_features():
    context = {
        "match": {
            "match_id": "agent-bra-arg",
            "stage": "QF",
            "home_team_id": "BRA",
            "away_team_id": "ARG",
            "home_team_raw": "Brazil",
            "away_team_raw": "Argentina",
        },
        "odds": {
            "status": "available",
            "fetchedAt": "2026-07-14T10:00:00Z",
            "markets": [
                {
                    "bookmaker": "Example Book",
                    "market": "Match Winner",
                    "outcomes": [
                        {"name": "Home", "odd": 2.4},
                        {"name": "Draw", "odd": 3.1},
                        {"name": "Away", "odd": 3.0},
                    ],
                }
            ],
        },
    }

    prediction = build_agent_match_prediction(
        context,
        sources=[],
        search_attempted=False,
    )

    assert prediction is not None
    assert prediction.data_grade == "B"
    assert "market" in {item.name for item in prediction.probability_components}
    assert prediction.home_advancement_prob + prediction.away_advancement_prob == pytest.approx(1.0)


def test_agent_bridge_uses_web_evidence_when_structured_teams_are_unknown():
    context = {
        "match": {
            "match_id": "agent-unknown",
            "stage": "group",
            "home_team_id": "Team Alpha",
            "away_team_id": "Team Beta",
        },
        "odds": {"status": "unconfigured"},
    }
    sources = [
        {
            "citationId": 1,
            "title": "Official match preview",
            "url": "https://example.com/preview",
            "domain": "example.com",
            "publishedAt": "2026-07-14T08:00:00Z",
            "sourceQualityScore": 0.9,
        }
    ]

    prediction = build_agent_match_prediction(
        context,
        sources=sources,
        search_attempted=True,
    )

    assert prediction is not None
    assert prediction.data_grade == "D"
    assert prediction.confidence <= 0.5
    assert any(item.source_type == "web" for item in prediction.evidence)


def test_agent_bridge_converts_clear_web_language_to_bounded_semantic_signal():
    context = {
        "match": {
            "match_id": "agent-semantic",
            "stage": "group",
            "home_team_id": "BRA",
            "away_team_id": "ARG",
            "home_team_raw": "Brazil",
            "away_team_raw": "Argentina",
        },
        "odds": {"status": "empty"},
    }
    sources = [
        {
            "citationId": 4,
            "title": "Brazil favored after key player returns",
            "snippet": "Brazil are expected to win after a confirmed return.",
            "url": "https://example.com/brazil-preview",
            "domain": "example.com",
            "sourceQualityScore": 0.9,
            "relevanceScore": 0.9,
        }
    ]

    prediction = build_agent_match_prediction(
        context,
        sources=sources,
        search_attempted=True,
    )

    assert prediction is not None
    semantic = next(
        item for item in prediction.probability_components if item.name == "web_semantic"
    )
    assert semantic.home_win_prob > semantic.away_win_prob
    assert semantic.evidence_ids == ["web-4"]
    assert semantic.confidence <= 0.75


def test_agent_bridge_failed_search_still_returns_grade_e_answer():
    context = {
        "match": {
            "match_id": "agent-minimal",
            "stage": "group",
            "home_team_id": "Team Alpha",
            "away_team_id": "Team Beta",
        },
        "odds": {"status": "api_error"},
    }

    prediction = build_agent_match_prediction(
        context,
        sources=[],
        search_attempted=True,
        search_error="search unavailable",
    )

    assert prediction is not None
    assert prediction.data_grade == "E"
    answer = format_agent_match_prediction(prediction, "Team Alpha", "Team Beta", 0)
    assert "结论倾向" in answer
    assert "低" not in answer or "预测" in answer
    assert "无法预测" not in answer
    assert "不构成投注建议" in answer
