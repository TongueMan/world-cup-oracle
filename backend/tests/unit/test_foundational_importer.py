from __future__ import annotations

import json
from pathlib import Path

from wcpa.data.open_source_importer import (
    _float_or_none,
    _implied_probs,
    _parse_squad_file,
    import_historical_worldcup_matches,
    import_worldcup_squads,
)


class CaptureRepository:
    enabled = False

    def __init__(self):
        self.history = []
        self.squads = []

    def upsert_data_historical_matches(self, rows):
        self.history.extend(rows)
        return {"loaded": len(rows)}

    def upsert_data_team_squads(self, rows):
        self.squads.extend(rows)
        return {"loaded": len(rows)}


def test_parse_squad_file_extracts_players(tmp_path: Path):
    path = tmp_path / "开源数据/世界杯/worldcup-master/1930--uruguay/squads/fr-france.txt"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
##############################
# France (FRA)

   -  GK  Alex Thépot                        ##   12, Red Star Paris
   -  FW  Lucien Laurent                     ##    2, FC Sochaux
""",
        encoding="utf-8",
    )

    rows = _parse_squad_file(path, 1930, "France", tmp_path)

    assert len(rows) == 2
    assert rows[0]["team_name"] == "France"
    assert rows[0]["position"] == "GK"
    assert rows[0]["player_name"] == "Alex Thépot"
    assert rows[0]["shirt_number"] == "12"
    assert rows[0]["payload"]["club"] == "Red Star Paris"


def test_import_historical_worldcup_matches_maps_history_json(tmp_path: Path):
    path = tmp_path / "data/knowledge/worldcup/history.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "matches": [
                    {
                        "year": 1930,
                        "date": "1930-07-13",
                        "stage": "group",
                        "home_team": "France",
                        "away_team": "Mexico",
                        "home_score": 4,
                        "away_score": 1,
                        "winner_team": "France",
                        "source": "openfootball",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repo = CaptureRepository()

    result = import_historical_worldcup_matches(repo, tmp_path)

    assert result.loaded == 1
    assert repo.history[0]["edition_year"] == 1930
    assert repo.history[0]["match_date"] == "1930-07-13"


def test_import_worldcup_squads_walks_worldcup_master(tmp_path: Path):
    path = tmp_path / "开源数据/世界杯/worldcup-master/1930--uruguay/squads/fr-france.txt"
    path.parent.mkdir(parents=True)
    path.write_text("# France (FRA)\n-  GK  Alex Thépot ## 12, Red Star Paris\n", encoding="utf-8")
    repo = CaptureRepository()

    result = import_worldcup_squads(repo, tmp_path)

    assert result.loaded == 1
    assert repo.squads[0]["edition_year"] == 1930


def test_implied_probs_are_normalized():
    probs = _implied_probs(2.0, 3.0, 4.0)

    assert round(sum(probs.values()), 6) == 1.0
    assert probs["implied_home_prob"] > probs["implied_away_prob"]


def test_float_or_none_rejects_zero_odds():
    assert _float_or_none("0") is None
    assert _float_or_none("-1") is None
    assert _float_or_none("2.5") == 2.5
