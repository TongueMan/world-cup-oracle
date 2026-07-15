"""Venue, elevation, weather, and match environment services."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.schemas.worldcup_environment import (
    WorldCupEnvironmentFeatures,
    WorldCupMatchEnvironment,
    WorldCupVenue,
    WorldCupVenueList,
    WorldCupWeatherSnapshot,
)
from wcpa.shared.paths import DATA_DIR

VENUES_SEED_FILE = DATA_DIR / "seeds" / "venues_seed.json"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ENVIRONMENT_CACHE_DIR = DATA_DIR / "cache" / "worldcup" / "environment"
WORLD_CUP_MATCHES_FILE = DATA_DIR / "knowledge" / "worldcup" / "matches.json"


@dataclass(frozen=True)
class ImportReport:
    status: str
    loaded_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] | None = None


class VenueSeedError(ValueError):
    """Raised when venue seed data is invalid."""


def load_venue_seed(path: Path = VENUES_SEED_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        raise VenueSeedError(f"Venue seed file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise VenueSeedError("Venue seed must be a JSON array.")
    venues = []
    errors = []
    for index, row in enumerate(payload):
        try:
            venues.append(validate_venue_seed_row(row, index))
        except VenueSeedError as exc:
            errors.append(str(exc))
    if errors:
        raise VenueSeedError("; ".join(errors))
    return venues


def validate_venue_seed_row(row: dict[str, Any], index: int = 0) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise VenueSeedError(f"venues_seed[{index}] must be an object.")
    for key in ("venue_id", "venue_name", "country", "source"):
        if not row.get(key):
            raise VenueSeedError(f"venues_seed[{index}] missing required field: {key}")
    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if (latitude is None) ^ (longitude is None):
        raise VenueSeedError(f"venues_seed[{index}] latitude and longitude must be provided together.")
    normalized = dict(row)
    normalized.setdefault("source_url", "")
    normalized.setdefault("coordinate_source_url", "")
    normalized.setdefault("source_venue_ids", [])
    normalized.setdefault("aliases", [])
    normalized.setdefault("metadata", {})
    if latitude is not None:
        normalized["latitude"] = float(latitude)
        normalized["longitude"] = float(longitude)
    if normalized.get("capacity") is not None:
        normalized["capacity"] = int(normalized["capacity"])
    if normalized.get("altitude_m") is not None:
        normalized["altitude_m"] = float(normalized["altitude_m"])
    return normalized


def compute_environment_features(
    *,
    temperature_c: float | None = None,
    apparent_temperature_c: float | None = None,
    humidity_pct: float | None = None,
    precipitation_mm: float | None = None,
    rain_probability: float | None = None,
    wind_speed_kmh: float | None = None,
    wind_gust_kmh: float | None = None,
    altitude_m: float | None = None,
) -> dict[str, Any]:
    heat = _heat_stress(temperature_c, apparent_temperature_c, humidity_pct)
    rain = _rain_disruption(precipitation_mm, rain_probability)
    wind = _wind_disruption(wind_speed_kmh, wind_gust_kmh)
    altitude = _altitude_stress(altitude_m)
    available = [value for value in (heat, rain, wind, altitude) if value is not None]
    difficulty = None
    if available:
        difficulty = _clamp(
            0.35 * (heat or 0.0)
            + 0.25 * (rain or 0.0)
            + 0.20 * (wind or 0.0)
            + 0.20 * (altitude or 0.0)
        )
    summary = _environment_summary(heat, rain, wind, altitude, difficulty)
    return {
        "heat_stress_index": heat,
        "rain_disruption_index": rain,
        "wind_disruption_index": wind,
        "altitude_stress_index": altitude,
        "environment_difficulty_index": difficulty,
        "environment_summary": summary,
    }


def fetch_elevation(latitude: float, longitude: float, timeout: float = 15.0) -> dict[str, Any]:
    query = urlencode({"latitude": latitude, "longitude": longitude})
    source_url = f"{OPEN_METEO_ELEVATION_URL}?{query}"
    try:
        response = httpx.get(source_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        values = payload.get("elevation") or []
        if not values:
            return _failed("open_meteo_elevation", source_url, "elevation missing")
        return {
            "status": "ok",
            "altitude_m": float(values[0]),
            "source": "open_meteo_elevation",
            "source_url": source_url,
        }
    except Exception as exc:
        return _failed("open_meteo_elevation", source_url, str(exc))


def fetch_hourly_weather(
    latitude: float,
    longitude: float,
    kickoff_time: datetime,
    timeout: float = 15.0,
) -> dict[str, Any]:
    kickoff_utc = _ensure_datetime(kickoff_time).astimezone(timezone.utc)
    query = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "precipitation_probability",
                "wind_speed_10m",
                "wind_gusts_10m",
            ]
        ),
        "timezone": "UTC",
        "start_date": kickoff_utc.date().isoformat(),
        "end_date": kickoff_utc.date().isoformat(),
    }
    source_url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(query)}"
    try:
        response = httpx.get(source_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            return _failed(
                "open_meteo_forecast",
                source_url,
                "weather forecast unavailable for kickoff time",
            )
        offset = int(payload.get("utc_offset_seconds") or 0)
        matched_index = _nearest_hour_index(times, kickoff_time, offset)
        if matched_index is None:
            return _failed(
                "open_meteo_forecast",
                source_url,
                "weather forecast unavailable for kickoff time",
            )
        matched_hour = _local_hour_to_datetime(times[matched_index], offset)
        return {
            "status": "ok",
            "source": "open_meteo_forecast",
            "source_url": source_url,
            "matched_hour": matched_hour.isoformat(),
            "temperature_c": _hourly_value(hourly, "temperature_2m", matched_index),
            "apparent_temperature_c": _hourly_value(hourly, "apparent_temperature", matched_index),
            "humidity_pct": _hourly_value(hourly, "relative_humidity_2m", matched_index),
            "precipitation_mm": _hourly_value(hourly, "precipitation", matched_index),
            "rain_probability": _hourly_value(hourly, "precipitation_probability", matched_index),
            "wind_speed_kmh": _hourly_value(hourly, "wind_speed_10m", matched_index),
            "wind_gust_kmh": _hourly_value(hourly, "wind_gusts_10m", matched_index),
            "raw": payload,
        }
    except Exception as exc:
        return _failed("open_meteo_forecast", source_url, str(exc))


class WorldCupEnvironmentService:
    def __init__(self, repository: PostgresRepository | None = None):
        self.repository = repository or PostgresRepository()

    def sync_venues(self, seed_path: Path = VENUES_SEED_FILE) -> ImportReport:
        venues = load_venue_seed(seed_path)
        counts = self.repository.upsert_venues(venues)
        return ImportReport(
            status="ok",
            loaded_count=len(venues),
            inserted_count=counts["inserted"],
            updated_count=counts["updated"],
        )

    def sync_match_venues(self) -> ImportReport:
        venues = self.repository.load_venues()
        source_to_venue = {}
        for venue in venues:
            for source_id in venue.get("source_venue_ids") or []:
                source_to_venue[source_id] = venue["venue_id"]
        rows = []
        skipped = []
        for match in self.repository.load_worldcup_matches():
            source_venue_id = (match.get("metadata") or {}).get("venue_id")
            if not source_venue_id:
                skipped.append(f"{match['match_id']}: missing metadata.venue_id")
                continue
            venue_id = source_to_venue.get(source_venue_id)
            if not venue_id:
                skipped.append(f"{match['match_id']}: unmapped source venue {source_venue_id}")
                continue
            rows.append(
                {
                    "match_id": match["match_id"],
                    "venue_id": venue_id,
                    "source": "worldcup_matches_metadata",
                    "source_url": match.get("source_url", ""),
                    "source_venue_id": source_venue_id,
                }
            )
        counts = self.repository.upsert_match_venues(rows)
        return ImportReport(
            status="ok" if rows else "partial",
            loaded_count=len(rows),
            inserted_count=counts["inserted"],
            updated_count=counts["updated"],
            skipped_count=len(skipped),
            errors=skipped,
        )

    def sync_venue_elevation(self) -> ImportReport:
        updated = 0
        skipped = []
        for venue in self.repository.load_venues():
            if venue.get("latitude") is None or venue.get("longitude") is None:
                skipped.append(f"{venue['venue_id']}: missing latitude/longitude")
                continue
            result = fetch_elevation(float(venue["latitude"]), float(venue["longitude"]))
            if result.get("status") != "ok" or result.get("altitude_m") is None:
                skipped.append(f"{venue['venue_id']}: {result.get('error', 'elevation failed')}")
                continue
            self.repository.update_venue_elevation(
                venue["venue_id"],
                float(result["altitude_m"]),
                result["source"],
                result["source_url"],
            )
            updated += 1
        return ImportReport(
            status="ok" if updated else "partial",
            loaded_count=updated,
            skipped_count=len(skipped),
            errors=skipped,
        )

    def sync_match_weather(self) -> ImportReport:
        loaded = 0
        skipped = []
        for row in self.repository.load_matches_with_venues():
            if not row.get("kickoff_time"):
                skipped.append(f"{row['match_id']}: missing kickoff_time")
                continue
            if row.get("latitude") is None or row.get("longitude") is None:
                skipped.append(f"{row['match_id']}: missing venue coordinates")
                continue
            weather = fetch_hourly_weather(
                float(row["latitude"]),
                float(row["longitude"]),
                _ensure_datetime(row["kickoff_time"]),
            )
            payload = {
                "match_id": row["match_id"],
                "venue_id": row["venue_id"],
                "kickoff_time": row["kickoff_time"],
                "altitude_m": row.get("altitude_m"),
                "source": weather.get("source"),
                "source_url": weather.get("source_url", ""),
                "fetched_at": datetime.now(timezone.utc),
                "raw_weather": weather.get("raw", {}),
            }
            if weather.get("status") == "ok":
                payload.update(
                    {
                        "temperature_c": weather.get("temperature_c"),
                        "apparent_temperature_c": weather.get("apparent_temperature_c"),
                        "humidity_pct": weather.get("humidity_pct"),
                        "precipitation_mm": weather.get("precipitation_mm"),
                        "rain_probability": weather.get("rain_probability"),
                        "wind_speed_kmh": weather.get("wind_speed_kmh"),
                        "wind_gust_kmh": weather.get("wind_gust_kmh"),
                        "data_status": "partial",
                        "reason": "features_not_built",
                    }
                )
                loaded += 1
            else:
                payload.update(
                    {
                        "data_status": "data_unavailable",
                        "reason": weather.get("error", "weather unavailable"),
                    }
                )
                skipped.append(f"{row['match_id']}: {payload['reason']}")
            self.repository.upsert_match_environment(payload)
        return ImportReport(
            status="ok" if loaded else "partial",
            loaded_count=loaded,
            skipped_count=len(skipped),
            errors=skipped,
        )

    def build_match_environment_features(self) -> ImportReport:
        loaded = 0
        skipped = []
        for row in self.repository.load_matches_with_venues():
            existing = self.repository.load_match_environment(row["match_id"])
            if not existing:
                payload = {
                    "match_id": row["match_id"],
                    "venue_id": row["venue_id"],
                    "kickoff_time": row.get("kickoff_time"),
                    "altitude_m": row.get("altitude_m"),
                    "environment_summary": (
                        "场馆已确认；天气、草皮、屋顶和临场环境细节仍待权威来源确认。"
                    ),
                    "data_status": "partial",
                    "reason": "venue_confirmed_weather_snapshot_missing",
                    "source": "worldcup_matches_and_venue_seed",
                    "source_url": row.get("source_url", ""),
                    "raw_weather": {},
                    "fetched_at": datetime.now(timezone.utc),
                }
                self.repository.upsert_match_environment(payload)
                loaded += 1
                continue
            weather_missing = all(
                existing.get(key) is None
                for key in (
                    "temperature_c",
                    "apparent_temperature_c",
                    "humidity_pct",
                    "precipitation_mm",
                    "rain_probability",
                    "wind_speed_kmh",
                    "wind_gust_kmh",
                )
            )
            if weather_missing:
                payload = {
                    **existing,
                    "venue_id": row["venue_id"],
                    "kickoff_time": row.get("kickoff_time") or existing.get("kickoff_time"),
                    "altitude_m": existing.get("altitude_m") if existing.get("altitude_m") is not None else row.get("altitude_m"),
                    "heat_stress_index": None,
                    "rain_disruption_index": None,
                    "wind_disruption_index": None,
                    "altitude_stress_index": None,
                    "environment_difficulty_index": None,
                    "environment_summary": (
                        "场馆已确认；天气、草皮、屋顶和临场环境细节仍待权威来源确认。"
                    ),
                    "data_status": "partial",
                    "reason": existing.get("reason") or "weather_snapshot_missing",
                    "raw_weather": {},
                }
                self.repository.upsert_match_environment(payload)
                loaded += 1
                continue
            features = compute_environment_features(
                temperature_c=existing.get("temperature_c"),
                apparent_temperature_c=existing.get("apparent_temperature_c"),
                humidity_pct=existing.get("humidity_pct"),
                precipitation_mm=existing.get("precipitation_mm"),
                rain_probability=existing.get("rain_probability"),
                wind_speed_kmh=existing.get("wind_speed_kmh"),
                wind_gust_kmh=existing.get("wind_gust_kmh"),
                altitude_m=existing.get("altitude_m") if existing.get("altitude_m") is not None else row.get("altitude_m"),
            )
            payload = {
                **existing,
                **features,
                "venue_id": row["venue_id"],
                "altitude_m": existing.get("altitude_m") if existing.get("altitude_m") is not None else row.get("altitude_m"),
                "data_status": "ok" if existing.get("data_status") != "data_unavailable" else "partial",
                "reason": None if existing.get("data_status") != "data_unavailable" else existing.get("reason"),
                "raw_weather": {},
            }
            self.repository.upsert_match_environment(payload)
            loaded += 1
        return ImportReport(
            status="ok" if loaded else "partial",
            loaded_count=loaded,
            skipped_count=len(skipped),
            errors=skipped,
        )

    def list_venues(self) -> dict[str, Any]:
        rows = self.repository.load_venues()
        if not rows:
            try:
                rows = load_venue_seed()
            except VenueSeedError:
                rows = []
        return WorldCupVenueList(items=[WorldCupVenue(**row) for row in rows]).model_dump(mode="json")

    def get_venue(self, venue_id: str) -> dict[str, Any]:
        row = self.repository.load_venue(venue_id)
        if row:
            return WorldCupVenue(**row).model_dump(mode="json")
        try:
            row = next((item for item in load_venue_seed() if item["venue_id"] == venue_id), None)
        except VenueSeedError:
            row = None
        if row:
            return WorldCupVenue(**row).model_dump(mode="json")
        return {"data_status": "not_found", "reason": "venue not found"}

    def get_match_environment(self, match_id: str) -> dict[str, Any]:
        row = self.repository.load_match_environment(match_id)
        if row:
            return _environment_response(row)
        match_venue = self.repository.load_match_venue(match_id)
        if not match_venue:
            file_backed = _file_backed_match_environment(match_id)
            if file_backed:
                return file_backed
            return {
                "match_id": match_id,
                "data_status": "data_unavailable",
                "reason": "match venue mapping not found",
            }
        venue = self.repository.load_venue(match_venue["venue_id"]) or {}
        return {
            "match_id": match_id,
            "venue": venue,
            "data_status": "partial",
            "reason": "weather forecast unavailable for kickoff time",
        }


def _file_backed_match_environment(match_id: str) -> dict[str, Any] | None:
    """Resolve venue and live weather without requiring PostgreSQL."""

    try:
        matches = json.loads(WORLD_CUP_MATCHES_FILE.read_text(encoding="utf-8"))
        match = next((row for row in matches if row.get("match_id") == match_id), None)
        if not match:
            return None
        source_venue_id = (match.get("metadata") or {}).get("venue_id")
        venue = next(
            (
                row
                for row in load_venue_seed()
                if source_venue_id in (row.get("source_venue_ids") or [])
            ),
            None,
        )
        if not venue:
            return None
        cached = _read_environment_cache(match_id)
        if cached:
            return cached
        kickoff = _ensure_datetime(match.get("kickoff_time"))
        weather = fetch_hourly_weather(
            float(venue["latitude"]),
            float(venue["longitude"]),
            kickoff,
        )
        if weather.get("status") != "ok":
            payload = {
                "match_id": match_id,
                "venue": venue,
                "features": {},
                "summary": "场馆已经确认，但当前天气源没有返回开赛时段预报。",
                "data_status": "partial",
                "reason": weather.get("error") or "weather forecast unavailable",
                "source": venue.get("source"),
                "source_url": venue.get("source_url", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_environment_cache(match_id, payload)
            return payload
        features = compute_environment_features(
            temperature_c=weather.get("temperature_c"),
            apparent_temperature_c=weather.get("apparent_temperature_c"),
            humidity_pct=weather.get("humidity_pct"),
            precipitation_mm=weather.get("precipitation_mm"),
            rain_probability=weather.get("rain_probability"),
            wind_speed_kmh=weather.get("wind_speed_kmh"),
            wind_gust_kmh=weather.get("wind_gust_kmh"),
            altitude_m=venue.get("altitude_m"),
        )
        payload = {
            "match_id": match_id,
            "venue": venue,
            "weather": {
                key: weather.get(key)
                for key in (
                    "matched_hour", "temperature_c", "apparent_temperature_c", "humidity_pct",
                    "precipitation_mm", "rain_probability", "wind_speed_kmh", "wind_gust_kmh",
                )
            },
            "features": features,
            "summary": features.get("environment_summary") or "开赛时段天气已经获取。",
            "data_status": "ok",
            "source": weather.get("source"),
            "source_url": weather.get("source_url", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_environment_cache(match_id, payload)
        return payload
    except (OSError, ValueError, TypeError, VenueSeedError):
        return None


def _environment_cache_path(match_id: str) -> Path:
    digest = hashlib.sha256(match_id.encode("utf-8")).hexdigest()[:20]
    return ENVIRONMENT_CACHE_DIR / f"{digest}.json"


def _read_environment_cache(match_id: str) -> dict[str, Any] | None:
    path = _environment_cache_path(match_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = _ensure_datetime(payload.get("fetched_at"))
        if payload.get("data_status") == "ok" and datetime.now(timezone.utc) - fetched_at <= timedelta(hours=1):
            return payload
    except (OSError, ValueError, TypeError):
        return None
    return None


def _write_environment_cache(match_id: str, payload: dict[str, Any]) -> None:
    ENVIRONMENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _environment_cache_path(match_id)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _environment_response(row: dict[str, Any]) -> dict[str, Any]:
    weather = WorldCupWeatherSnapshot(
        kickoff_time=row.get("kickoff_time"),
        temperature_c=row.get("temperature_c"),
        apparent_temperature_c=row.get("apparent_temperature_c"),
        humidity_pct=row.get("humidity_pct"),
        precipitation_mm=row.get("precipitation_mm"),
        rain_probability=row.get("rain_probability"),
        wind_speed_kmh=row.get("wind_speed_kmh"),
        wind_gust_kmh=row.get("wind_gust_kmh"),
    )
    features = WorldCupEnvironmentFeatures(
        heat_stress_index=row.get("heat_stress_index"),
        rain_disruption_index=row.get("rain_disruption_index"),
        wind_disruption_index=row.get("wind_disruption_index"),
        altitude_stress_index=row.get("altitude_stress_index"),
        environment_difficulty_index=row.get("environment_difficulty_index"),
    )
    venue = row.get("venue") or {}
    if venue:
        venue = WorldCupVenue(**venue).model_dump(mode="json")
    return WorldCupMatchEnvironment(
        match_id=row["match_id"],
        venue=venue,
        weather=weather,
        features=features,
        summary=row.get("environment_summary") or "",
        data_status=row.get("data_status") or "data_unavailable",
        reason=row.get("reason"),
        source=row.get("source"),
        source_url=row.get("source_url"),
        fetched_at=row.get("fetched_at"),
    ).model_dump(mode="json")


def _heat_stress(
    temperature_c: float | None,
    apparent_temperature_c: float | None,
    humidity_pct: float | None,
) -> float | None:
    if temperature_c is None and apparent_temperature_c is None:
        return None
    temp = max(value for value in [temperature_c, apparent_temperature_c] if value is not None)
    if temp < 24:
        value = 0.1
    elif temp < 28:
        value = 0.2 + (temp - 24) / 4 * 0.3
    elif temp < 32:
        value = 0.5 + (temp - 28) / 4 * 0.25
    else:
        value = 0.75 + min((temp - 32) / 10 * 0.25, 0.25)
    if humidity_pct is not None and humidity_pct >= 70 and temp >= 24:
        value += min((humidity_pct - 70) / 30 * 0.15, 0.15)
    return round(_clamp(value), 4)


def _rain_disruption(precipitation_mm: float | None, rain_probability: float | None) -> float | None:
    if precipitation_mm is None and rain_probability is None:
        return None
    precip = precipitation_mm or 0.0
    probability = (rain_probability or 0.0) / 100.0
    precip_component = min(precip / 12.0, 1.0)
    value = 0.7 * precip_component + 0.3 * probability
    return round(_clamp(value), 4)


def _wind_disruption(wind_speed_kmh: float | None, wind_gust_kmh: float | None) -> float | None:
    if wind_speed_kmh is None and wind_gust_kmh is None:
        return None
    speed = wind_speed_kmh or 0.0
    gust = wind_gust_kmh or speed
    effective = max(speed, gust * 0.75)
    if effective < 10:
        value = effective / 10 * 0.2
    elif effective < 20:
        value = 0.2 + (effective - 10) / 10 * 0.2
    elif effective < 35:
        value = 0.4 + (effective - 20) / 15 * 0.3
    else:
        value = 0.7 + min((effective - 35) / 25 * 0.3, 0.3)
    return round(_clamp(value), 4)


def _altitude_stress(altitude_m: float | None) -> float | None:
    if altitude_m is None:
        return None
    if altitude_m < 500:
        return 0.0
    if altitude_m < 1000:
        value = 0.1 + (altitude_m - 500) / 500 * 0.15
    elif altitude_m < 1500:
        value = 0.25 + (altitude_m - 1000) / 500 * 0.20
    elif altitude_m < 2000:
        value = 0.45 + (altitude_m - 1500) / 500 * 0.25
    else:
        value = 0.70 + min((altitude_m - 2000) / 1000 * 0.30, 0.30)
    return round(_clamp(value), 4)


def _environment_summary(
    heat: float | None,
    rain: float | None,
    wind: float | None,
    altitude: float | None,
    difficulty: float | None,
) -> str:
    if all(value is None for value in (heat, rain, wind, altitude, difficulty)):
        return "场馆已确认；天气、草皮、屋顶和临场环境细节仍待权威来源确认。"
    if difficulty is None or difficulty < 0.2:
        return "本场比赛环境整体压力较低，天气条件对比赛影响有限。"
    parts = []
    if heat is not None and heat >= 0.5:
        parts.append("存在一定高温高湿压力，可能影响高位逼抢和持续冲刺能力")
    if rain is not None and rain >= 0.35:
        parts.append("存在降雨风险，地面传控和门将处理球稳定性可能受到影响")
    if wind is not None and wind >= 0.4:
        parts.append("风速较高，可能影响长传、传中、高空球和定位球质量")
    if altitude is not None and altitude >= 0.25:
        parts.append("海拔因素可能增加高强度跑动和下半场恢复压力")
    if not parts:
        return "本场比赛存在轻度环境压力，但暂未达到明显改变比赛条件的程度。"
    return "本场" + "；".join(parts) + "。"


def _nearest_hour_index(times: list[str], kickoff_time: datetime, offset_seconds: int) -> int | None:
    target = _ensure_datetime(kickoff_time)
    best_index = None
    best_delta = None
    for index, raw in enumerate(times):
        current = _local_hour_to_datetime(raw, offset_seconds)
        delta = abs((current.astimezone(timezone.utc) - target.astimezone(timezone.utc)).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_index = index
    if best_delta is not None and best_delta <= timedelta(hours=3).total_seconds():
        return best_index
    return None


def _local_hour_to_datetime(raw: str, offset_seconds: int) -> datetime:
    value = datetime.fromisoformat(raw)
    return value.replace(tzinfo=timezone(timedelta(seconds=offset_seconds)))


def _hourly_value(hourly: dict[str, list[Any]], key: str, index: int) -> float | None:
    values = hourly.get(key) or []
    if index >= len(values) or values[index] is None:
        return None
    return float(values[index])


def _ensure_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _failed(source: str, source_url: str, error: str) -> dict[str, Any]:
    return {"status": "failed", "source": source, "source_url": source_url, "error": error}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
