"""Agent match-context boundary tests."""

from wcpa.agents.agent_context_builder import _remove_time_misaligned_weather


def _environment():
    return {
        "venue": {"venue_name": "Mercedes-Benz Stadium", "source": "fifa", "source_url": "https://fifa.com/venue"},
        "weather": {"temperature_c": 27.6, "humidity_pct": 77},
        "features": {"heat_stress": 0.8},
        "data_status": "available",
    }


def test_weather_is_removed_when_kickoff_clock_is_unknown():
    result = _remove_time_misaligned_weather(
        {"kickoff_label": "今天", "kickoff_time": "2026-07-16T00:00:00+08:00", "parse_warnings": ["kickoff_clock_time_missing"]},
        _environment(),
    )

    assert "weather" not in result
    assert result["features"] == {}
    assert result["reason"] == "kickoff_clock_time_unavailable"
    assert "不能把小时级天气称为开球时天气" in result["summary"]


def test_weather_is_kept_when_kickoff_clock_is_explicit():
    result = _remove_time_misaligned_weather(
        {"kickoff_label": "7月16日 03:00", "kickoff_time": "2026-07-16T03:00:00+08:00"},
        _environment(),
    )

    assert result["weather"]["temperature_c"] == 27.6
