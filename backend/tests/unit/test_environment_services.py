"""Environment service and feature tests."""

from datetime import datetime, timezone

from wcpa.worldcup import environment
from wcpa.worldcup.environment import (
    _environment_summary,
    compute_environment_features,
    fetch_elevation,
    fetch_hourly_weather,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http failed")

    def json(self):
        return self.payload


def test_fetch_elevation_success(monkeypatch):
    def fake_get(url, timeout):
        return FakeResponse({"elevation": [12.0]})

    monkeypatch.setattr(environment.httpx, "get", fake_get)

    result = fetch_elevation(40.0, -74.0)

    assert result["status"] == "ok"
    assert result["altitude_m"] == 12.0


def test_fetch_elevation_failure_does_not_fabricate(monkeypatch):
    def fake_get(url, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(environment.httpx, "get", fake_get)

    result = fetch_elevation(40.0, -74.0)

    assert result["status"] == "failed"
    assert "altitude_m" not in result


def test_fetch_hourly_weather_failure_does_not_fabricate(monkeypatch):
    def fake_get(url, timeout):
        return FakeResponse({"hourly": {"time": []}})

    monkeypatch.setattr(environment.httpx, "get", fake_get)

    result = fetch_hourly_weather(40.0, -74.0, datetime(2026, 7, 4, tzinfo=timezone.utc))

    assert result["status"] == "failed"
    assert "temperature_c" not in result


def test_environment_indexes_rise_for_stressors():
    calm = compute_environment_features(
        temperature_c=20,
        apparent_temperature_c=20,
        humidity_pct=40,
        precipitation_mm=0,
        rain_probability=0,
        wind_speed_kmh=3,
        altitude_m=10,
    )
    harsh = compute_environment_features(
        temperature_c=34,
        apparent_temperature_c=39,
        humidity_pct=85,
        precipitation_mm=8,
        rain_probability=90,
        wind_speed_kmh=38,
        wind_gust_kmh=55,
        altitude_m=2200,
    )

    assert harsh["heat_stress_index"] > calm["heat_stress_index"]
    assert harsh["rain_disruption_index"] > calm["rain_disruption_index"]
    assert harsh["wind_disruption_index"] > calm["wind_disruption_index"]
    assert harsh["altitude_stress_index"] > calm["altitude_stress_index"]
    assert harsh["environment_difficulty_index"] > calm["environment_difficulty_index"]


def test_environment_summary_does_not_claim_low_pressure_without_data():
    summary = _environment_summary(None, None, None, None, None)

    assert "待权威来源确认" in summary
    assert "压力较低" not in summary
