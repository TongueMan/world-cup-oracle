"""Source-backed live team feature assembly tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from wcpa.agents.firecrawl_client import FirecrawlCallError
from wcpa.data.team_feature_assembler import (
    LiveTeamFeatureAssembler,
    parse_elo_ranking_markdown,
    parse_fifa_ranking_markdown,
)


def test_live_rating_parsers_extract_source_values():
    fifa = "| ### 3 | [Argentina](https://inside.fifa.com/fifa-world-ranking/ARG?gender=men) |"
    elo = "[Argentina](https://eloratings.net/Argentina) 2177"

    assert parse_fifa_ranking_markdown(fifa) == {"ARG": 3}
    assert parse_elo_ranking_markdown(elo) == {"argentina": 2177}


def test_assembler_builds_verified_team_without_default_feature_fill(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "wcpa.data.team_feature_assembler._load_identities",
        lambda: {"ARG": {"team_id": "ARG", "name_en": "Argentina", "name_zh": "阿根廷"}},
    )
    monkeypatch.setattr(
        "wcpa.data.team_feature_assembler._historical_experience",
        lambda required, identities: {"ARG": 1.0},
    )

    class FakeFirecrawl:
        def scrape(self, url):
            if "fifa" in url:
                return SimpleNamespace(
                    markdown="| ### 3 | [Argentina](https://inside.fifa.com/fifa-world-ranking/ARG?gender=men) |",
                    url=url,
                )
            return SimpleNamespace(
                markdown="[Argentina](https://eloratings.net/Argentina) 2177",
                url=url,
            )

    sources = [
        SimpleNamespace(
            title="Argentina team news and confirmed lineup",
            snippet="All available for the semifinal.",
            excerpt="",
            url="https://example.test/argentina-team-news",
            source_quality_score=0.95,
            source_type="media",
        )
    ]
    schedule = [
        {
            "match_id": "M1",
            "status": "complete",
            "home_team_id": "ARG",
            "away_team_id": "FRA",
            "home_score": 2,
            "away_score": 0,
            "winner_team_id": "ARG",
            "kickoff_time": "2026-07-10T00:00:00Z",
        }
    ]

    result = LiveTeamFeatureAssembler(
        firecrawl=FakeFirecrawl(),
        search=lambda *args, **kwargs: sources,
        cache_dir=tmp_path,
    ).build(schedule, ["ARG"], now=datetime(2026, 7, 15, tzinfo=timezone.utc))

    team = result.teams[0]
    assert result.report.status == "ready"
    assert team.verified is True
    assert team.fifa_rank == 3
    assert team.elo_rating == 2177
    assert team.attack_score > 0
    assert team.squad_health_score == 0.95


def test_assembler_derives_traceable_features_for_historical_stage_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "wcpa.data.team_feature_assembler._load_identities",
        lambda: {
            "CIV": {"team_id": "CIV", "name_en": "Ivory Coast", "name_zh": "科特迪瓦"},
            "SEN": {"team_id": "SEN", "name_en": "Senegal", "name_zh": "塞内加尔"},
        },
    )
    monkeypatch.setattr(
        "wcpa.data.team_feature_assembler._historical_experience",
        lambda required, identities: {team_id: 0.5 for team_id in required},
    )

    class MissingFirecrawl:
        def scrape(self, url):
            raise FirecrawlCallError("ratings unavailable")

    schedule = [
        {
            "match_id": "G1",
            "status": "complete",
            "home_team_id": "CIV",
            "away_team_id": "SEN",
            "home_score": 2,
            "away_score": 1,
            "winner_team_id": "CIV",
            "kickoff_time": "2026-06-20T00:00:00Z",
        }
    ]

    result = LiveTeamFeatureAssembler(
        firecrawl=MissingFirecrawl(),
        search=lambda *args, **kwargs: [],
        cache_dir=tmp_path,
    ).build(
        schedule,
        ["CIV", "SEN"],
        now=datetime(2026, 7, 15, tzinfo=timezone.utc),
        allow_live_sources=False,
    )

    assert result.report.status == "ready"
    assert {team.team_id for team in result.teams} == {"CIV", "SEN"}
    assert all(team.source_key == "worldcup_results_derived_rating+neutral_health" for team in result.teams)
    assert all(team.data_quality == "C" for team in result.teams)
    assert any(source.source_key == "worldcup_results_derived_team_rating" and source.records == 2 for source in result.report.source_statuses)
    assert any(source.source_key == "neutral_squad_availability_assumption" and source.records == 2 for source in result.report.source_statuses)
