"""WorldCup structured data service tests."""

from datetime import datetime, timezone

from wcpa.data.sources.bing_worldcup import BingKnowledgeRun
from wcpa.worldcup.service import normalize_bing_run, normalize_teams


def _fake_run() -> BingKnowledgeRun:
    return BingKnowledgeRun(
        run_id="test-run",
        fetched_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        source_url="https://www.bing.com/sportsdetails",
        snapshots=[],
        manifest={"raw_dir": ""},
        records={
            "matches": [
                {
                    "match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_1",
                    "stage": "R32",
                    "stage_label": "32 强赛",
                    "group": None,
                    "date_label": "6月30日",
                    "kickoff_label": "6月30日 01:00",
                    "home_name": "巴西",
                    "away_name": "日本",
                    "home_team_id": "BRA",
                    "away_team_id": "JPN",
                    "home_score": 2,
                    "away_score": 1,
                    "winner_name": "巴西",
                    "status": "final",
                    "source_url": "https://www.bing.com/game/1",
                    "raw_label": "查看 巴西 对阵 日本 的详细信息",
                    "fetched_at": "2026-07-03T00:00:00+00:00",
                }
                ,
                {
                    "match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_2",
                    "stage": "SF",
                    "stage_label": "半决赛",
                    "group": None,
                    "date_label": "今天",
                    "kickoff_label": "今天",
                    "home_name": "英格兰",
                    "away_name": "阿根廷",
                    "home_team_id": "ENG",
                    "away_team_id": "ARG",
                    "home_score": 1,
                    "away_score": 2,
                    "winner_name": "阿根廷",
                    "status": "final",
                    "source_url": "https://www.bing.com/game/2",
                    "raw_label": "查看 英格兰 对阵 阿根廷 的详细信息",
                    "fetched_at": "2026-07-03T00:00:00+00:00",
                }
            ],
            "bracket": [
                {
                    "match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_1",
                    "next_match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_2",
                    "round": "R32",
                    "home_penalty_score": None,
                    "away_penalty_score": None,
                },
                {
                    "match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_3",
                    "round": "QF",
                    "date_label": "7月10日",
                    "time_label": "04:00",
                    "home_name": "W89",
                    "away_name": "W90",
                    "status": "scheduled",
                    "next_match_id": "SportRadar_Soccer_InternationalWorldCup_2026_Game_4",
                    "source_url": "https://www.bing.com/game/3",
                },
            ],
            "standings": [],
            "teams": [],
        },
    )


def test_normalize_bing_run_merges_schedule_and_bracket():
    normalized = normalize_bing_run(_fake_run())

    match = next(row for row in normalized["matches"] if row["match_id"].endswith("_Game_1"))

    assert match["status"] == "complete"
    assert match["home_score"] == 2
    assert match["away_score"] == 1
    assert match["winner_team_id"] == "BRA"
    assert match["next_match_id"].endswith("_Game_2")
    assert match["source"] == "bing_sports_html_fragment"
    assert match["parser_version"] == "bing-html-v1"
    assert match["schema_version"] == "worldcup-match-v1"


def test_normalize_bing_run_keeps_bracket_placeholders_traceable():
    normalized = normalize_bing_run(_fake_run())

    match = next(row for row in normalized["matches"] if row["match_id"].endswith("_Game_3"))

    assert match["home_team_id"] == "W89"
    assert match["away_team_id"] == "W90"
    assert match["stage"] == "QF"
    assert match["status"] == "scheduled"
    assert "schedule_card_missing" in match["parse_warnings"]


def test_normalize_bing_run_marks_date_without_clock_as_imprecise():
    normalized = normalize_bing_run(_fake_run())

    match = next(row for row in normalized["matches"] if row["match_id"].endswith("_Game_2"))

    assert "kickoff_clock_time_missing" in match["parse_warnings"]
    assert match["date_confidence"] == "medium"


def test_team_aliases_normalize_to_same_team_id():
    teams = normalize_teams(
        [
            {"home_team_id": "USA", "home_team_raw": "美国"},
            {"home_team_id": "USA", "home_team_raw": "United States"},
        ],
        [],
    )

    usa = next(team for team in teams if team["team_id"] == "USA")
    assert "美国" in usa["aliases"]
    assert "United States" in usa["aliases"]
