"""Schemas for WorldCup venue and environment data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from wcpa.schemas import WCPABaseModel


class WorldCupVenue(WCPABaseModel):
    venue_id: str
    venue_name: str
    tournament_name: str | None = None
    host_city: str | None = None
    city: str | None = None
    country: str
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    capacity: int | None = None
    pitch_type: str | None = None
    roof_type: str | None = None
    source: str
    source_url: str | None = None
    coordinate_source_url: str | None = None
    source_venue_ids: list[str] = []
    aliases: list[str] = []
    metadata: dict[str, Any] = {}
    updated_at: datetime | None = None


class WorldCupVenueList(WCPABaseModel):
    items: list[WorldCupVenue]


class WorldCupMatchVenue(WCPABaseModel):
    match_id: str
    venue_id: str
    source: str
    source_url: str | None = None
    source_venue_id: str | None = None
    updated_at: datetime | None = None


class WorldCupWeatherSnapshot(WCPABaseModel):
    kickoff_time: datetime | None = None
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    humidity_pct: float | None = None
    precipitation_mm: float | None = None
    rain_probability: float | None = None
    wind_speed_kmh: float | None = None
    wind_gust_kmh: float | None = None


class WorldCupEnvironmentFeatures(WCPABaseModel):
    heat_stress_index: float | None = None
    rain_disruption_index: float | None = None
    wind_disruption_index: float | None = None
    altitude_stress_index: float | None = None
    environment_difficulty_index: float | None = None


class WorldCupMatchEnvironment(WCPABaseModel):
    match_id: str
    venue: WorldCupVenue | dict[str, Any] = {}
    weather: WorldCupWeatherSnapshot | dict[str, Any] = {}
    features: WorldCupEnvironmentFeatures | dict[str, Any] = {}
    summary: str = ""
    data_status: str = "data_unavailable"
    reason: str | None = None
    source: str | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
