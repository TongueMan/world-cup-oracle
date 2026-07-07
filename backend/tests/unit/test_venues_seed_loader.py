"""Venue seed loader tests."""

import json

import pytest

from wcpa.worldcup.environment import VenueSeedError, load_venue_seed


def test_load_venue_seed_requires_required_fields(tmp_path):
    seed = tmp_path / "venues_seed.json"
    seed.write_text(json.dumps([{"venue_id": "venue_x"}]), encoding="utf-8")

    with pytest.raises(VenueSeedError) as exc:
        load_venue_seed(seed)

    assert "venue_name" in str(exc.value)


def test_load_venue_seed_rejects_single_coordinate(tmp_path):
    seed = tmp_path / "venues_seed.json"
    seed.write_text(
        json.dumps(
            [
                {
                    "venue_id": "venue_x",
                    "venue_name": "Venue X",
                    "country": "United States",
                    "latitude": 1.0,
                    "source": "manual",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(VenueSeedError) as exc:
        load_venue_seed(seed)

    assert "latitude and longitude" in str(exc.value)


def test_project_seed_contains_16_venues():
    rows = load_venue_seed()

    assert len(rows) == 16
    assert {row["venue_id"] for row in rows}
