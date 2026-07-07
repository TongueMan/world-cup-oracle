"""API-Football odds integration for Agent match context."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from wcpa.shared.env import env_bool, env_int, env_str


class OddsServiceError(RuntimeError):
    """Raised when the odds provider cannot be queried."""


class ApiFootballOddsService:
    """Fetch compact pre-match odds from API-Football.

    API-Football uses its own fixture ids. The service first looks for a
    configured fixture id on the local match, then optionally discovers one
    from the World Cup fixture list by team/date.
    """

    def __init__(self) -> None:
        api_key = (
            env_str("WCPA_API_FOOTBALL_API_KEY")
            or env_str("WCPA_API_FOOTBALL_KEY")
            or env_str("API_FOOTBALL_KEY")
        )
        self.api_key = api_key
        self.enabled = env_bool("WCPA_API_FOOTBALL_ODDS_ENABLED", bool(api_key))
        self.base_url = env_str("WCPA_API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io").rstrip("/")
        self.league_id = env_int("WCPA_API_FOOTBALL_WORLD_CUP_LEAGUE_ID", 1)
        self.season = env_int("WCPA_API_FOOTBALL_SEASON", 2026)
        self.timeout = max(1, env_int("WCPA_API_FOOTBALL_TIMEOUT_SECONDS", 12))
        self.discover_fixture = env_bool("WCPA_API_FOOTBALL_DISCOVER_FIXTURE", True)
        self.max_markets = max(1, env_int("WCPA_API_FOOTBALL_MAX_MARKETS", 8))
        self.max_bookmakers = max(1, env_int("WCPA_API_FOOTBALL_MAX_BOOKMAKERS", 4))

    def get_match_odds(self, match: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return _unavailable("disabled", "API-Football odds are disabled.")
        if not self.api_key:
            return _unavailable("unconfigured", "Missing WCPA_API_FOOTBALL_API_KEY.")

        fixture_id = _configured_fixture_id(match)
        if fixture_id is None and self.discover_fixture:
            fixture_id = self._discover_fixture_id(match)
        if fixture_id is None:
            return _unavailable(
                "unmatched",
                "No API-Football fixture id was found for this local match.",
            )

        payload = self._get_json("/odds", {"fixture": fixture_id})
        error = _api_error(payload)
        if error:
            return _unavailable("api_error", error, fixture_id=fixture_id)

        rows = payload.get("response") or []
        if not rows:
            return _unavailable("empty", "API-Football returned no odds for this fixture.", fixture_id=fixture_id)
        return _compact_odds(rows[0], fixture_id, self.max_bookmakers, self.max_markets)

    def _discover_fixture_id(self, match: dict[str, Any]) -> int | None:
        params: dict[str, Any] = {"league": self.league_id, "season": self.season}
        date = _match_date(match)
        if date:
            params["date"] = date
        payload = self._get_json("/fixtures", params)
        error = _api_error(payload)
        if error:
            raise OddsServiceError(error)
        rows = payload.get("response") or []
        candidate = _best_fixture_match(match, rows)
        if not candidate:
            return None
        fixture = candidate.get("fixture") or {}
        fixture_id = fixture.get("id")
        return int(fixture_id) if fixture_id is not None else None

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"x-apisports-key": self.api_key}
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise OddsServiceError(f"API-Football request failed with HTTP {status}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OddsServiceError(f"API-Football request failed: {exc}") from exc
        if not isinstance(data, dict):
            raise OddsServiceError("API-Football returned an unexpected response shape.")
        return data


def _configured_fixture_id(match: dict[str, Any]) -> int | None:
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    values = [
        match.get("api_football_fixture_id"),
        metadata.get("api_football_fixture_id"),
        metadata.get("apiFootballFixtureId"),
        metadata.get("fixture_id"),
    ]
    for value in values:
        if value is None:
            continue
        try:
            return int(str(value).strip())
        except ValueError:
            continue
    match_id = str(match.get("match_id") or "").strip()
    return int(match_id) if match_id.isdigit() else None


def _api_error(payload: dict[str, Any]) -> str:
    errors = payload.get("errors")
    if not errors:
        return ""
    if isinstance(errors, list):
        return "; ".join(str(item) for item in errors if item)
    if isinstance(errors, dict):
        return "; ".join(str(value) for value in errors.values() if value)
    return str(errors)


def _compact_odds(
    row: dict[str, Any],
    fixture_id: int,
    max_bookmakers: int,
    max_markets: int,
) -> dict[str, Any]:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    league = row.get("league") if isinstance(row.get("league"), dict) else {}
    markets: list[dict[str, Any]] = []
    for bookmaker in (row.get("bookmakers") or [])[:max_bookmakers]:
        bookmaker_name = str(bookmaker.get("name") or "")
        for bet in bookmaker.get("bets") or []:
            market_name = str(bet.get("name") or "")
            if not _is_supported_market(market_name):
                continue
            outcomes = []
            for value in bet.get("values") or []:
                odd = _float_or_none(value.get("odd"))
                outcomes.append(
                    {
                        "name": str(value.get("value") or ""),
                        "odd": odd if odd is not None else value.get("odd"),
                        "impliedProbability": round(1 / odd, 4) if odd and odd > 0 else None,
                    }
                )
            if not outcomes:
                continue
            markets.append(
                {
                    "bookmaker": bookmaker_name,
                    "market": market_name,
                    "apiBetId": bet.get("id"),
                    "outcomes": outcomes,
                }
            )
            if len(markets) >= max_markets:
                break
        if len(markets) >= max_markets:
            break
    return {
        "provider": "api-football",
        "status": "available" if markets else "empty",
        "fixtureId": fixture_id,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "sourceUpdatedAt": row.get("update"),
        "fixtureDate": fixture.get("date"),
        "league": {
            "id": league.get("id"),
            "name": league.get("name"),
            "season": league.get("season"),
        },
        "bookmakerCount": len(row.get("bookmakers") or []),
        "markets": markets,
        "notice": (
            "Odds are informational snapshots from API-Football; they are not betting advice."
        ),
    }


def _is_supported_market(name: str) -> bool:
    text = name.casefold()
    terms = (
        "match winner",
        "winner",
        "fulltime",
        "goals over/under",
        "over/under",
        "correct score",
        "both teams score",
    )
    return any(term in text for term in terms)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _unavailable(status: str, reason: str, fixture_id: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "api-football",
        "status": status,
        "reason": reason,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }
    if fixture_id is not None:
        payload["fixtureId"] = fixture_id
    return payload


def _match_date(match: dict[str, Any]) -> str:
    value = str(match.get("kickoff_at") or match.get("kickoff_time") or "").strip()
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return ""


def _best_fixture_match(match: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    home_terms = _team_terms(match.get("home_team_id"), match.get("home_team_raw"))
    away_terms = _team_terms(match.get("away_team_id"), match.get("away_team_raw"))
    if not home_terms or not away_terms:
        return None
    expected_date = _match_date(match)
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for row in rows:
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        home_name = _normalize(str(home.get("name") or ""))
        away_name = _normalize(str(away.get("name") or ""))
        score = _name_score(home_name, home_terms) + _name_score(away_name, away_terms)
        fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
        fixture_date = str(fixture.get("date") or "")[:10]
        if expected_date and fixture_date == expected_date:
            score += 0.35
        if score > best[0]:
            best = (score, row)
    return best[1] if best[0] >= 1.6 else None


def _team_terms(team_id: Any, raw_name: Any) -> set[str]:
    terms = set()
    for value in (team_id, raw_name):
        if value:
            terms.add(_normalize(str(value)))
    aliases = _TEAM_ALIASES.get(str(team_id or "").upper(), ())
    terms.update(_normalize(alias) for alias in aliases)
    return {term for term in terms if term}


def _name_score(api_name: str, terms: set[str]) -> float:
    if not api_name:
        return 0.0
    if api_name in terms:
        return 1.0
    return max((0.9 for term in terms if term and (term in api_name or api_name in term)), default=0.0)


def _normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


_TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "ARG": ("Argentina",),
    "AUS": ("Australia",),
    "AUT": ("Austria",),
    "BEL": ("Belgium",),
    "BRA": ("Brazil",),
    "CAN": ("Canada",),
    "COL": ("Colombia",),
    "CPV": ("Cape Verde",),
    "ECU": ("Ecuador",),
    "EGY": ("Egypt",),
    "ENG": ("England",),
    "ESP": ("Spain",),
    "FRA": ("France",),
    "GER": ("Germany",),
    "GHA": ("Ghana",),
    "HAI": ("Haiti",),
    "IRN": ("Iran",),
    "JPN": ("Japan",),
    "KOR": ("South Korea", "Korea Republic"),
    "KSA": ("Saudi Arabia",),
    "MAR": ("Morocco",),
    "MEX": ("Mexico",),
    "NED": ("Netherlands",),
    "NOR": ("Norway",),
    "NZL": ("New Zealand",),
    "PAR": ("Paraguay",),
    "POR": ("Portugal",),
    "QAT": ("Qatar",),
    "RSA": ("South Africa",),
    "SCO": ("Scotland",),
    "SEN": ("Senegal",),
    "SUI": ("Switzerland",),
    "SWE": ("Sweden",),
    "TUR": ("Turkey", "Turkiye"),
    "URU": ("Uruguay",),
    "USA": ("United States", "USA"),
}
