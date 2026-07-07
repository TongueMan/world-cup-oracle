"""Historical WorldCup data tests."""

from fastapi.testclient import TestClient

from wcpa.api.server import app
from wcpa.worldcup.history import WorldCupHistoryService


def test_history_service_lists_full_mens_world_cup_editions():
    editions = WorldCupHistoryService().list_editions()

    assert len(editions) == 22
    assert editions[0]["year"] == 1930
    assert editions[-1]["year"] == 2022


def test_history_service_finals_include_2022_penalty_result():
    finals = WorldCupHistoryService().list_finals()
    final_2022 = next(row for row in finals if row["year"] == 2022)

    assert final_2022["champion"] == "Argentina"
    assert final_2022["champion_zh"] == "阿根廷"
    assert final_2022["runner_up"] == "France"
    assert final_2022["runner_up_zh"] == "法国"
    assert final_2022["home_flag_code"] == "ar"
    assert final_2022["away_flag_code"] == "fr"
    assert final_2022["home_penalty"] == 4
    assert final_2022["away_penalty"] == 2


def test_history_service_supports_chinese_team_search():
    service = WorldCupHistoryService()

    assert service.list_team_matches("巴西") == service.list_team_matches("Brazil")


def test_history_service_uses_modern_inherited_flags_for_old_teams():
    final_1966 = next(row for row in WorldCupHistoryService().list_finals() if row["year"] == 1966)

    assert final_1966["away_team"] == "West Germany"
    assert final_1966["away_team_zh"] == "西德"
    assert final_1966["away_flag_code"] == "de"


def test_history_service_localizes_common_venues_and_cities():
    matches = WorldCupHistoryService().list_matches(year=2006)
    opener = next(row for row in matches if row["venue"] == "Allianz Arena")
    dortmund = next(row for row in matches if row["venue"] == "Signal Iduna Park")

    assert opener["venue_zh"] == "安联球场"
    assert opener["city_zh"] == "慕尼黑"
    assert dortmund["venue_zh"] == "西格纳伊度纳公园球场"
    assert dortmund["city_zh"] == "多特蒙德"


def test_history_api_routes():
    client = TestClient(app, raise_server_exceptions=False)

    editions = client.get("/api/worldcup/history/editions").json()
    assert editions[0]["year"] == 1930

    edition = client.get("/api/worldcup/history/editions/2022").json()
    assert edition["champion"] == "Argentina"
    assert edition["champion_zh"] == "阿根廷"
    assert len(edition["matches"]) == 64

    finals = client.get("/api/worldcup/history/finals").json()
    assert len(finals) == 22

    brazil_matches = client.get("/api/worldcup/history/teams/Brazil/matches").json()
    assert any(row["year"] == 1970 and row["stage"] == "Final" for row in brazil_matches)
    assert client.get("/api/worldcup/history/teams/巴西/matches").json() == brazil_matches
    assert any(row["venue_zh"] == "安联球场" and row["city_zh"] == "慕尼黑" for row in brazil_matches)

    assert client.get("/api/worldcup/history/editions/1900").status_code == 404
