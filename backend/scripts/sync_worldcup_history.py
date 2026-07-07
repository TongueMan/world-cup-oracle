"""Download and normalize historical men's World Cup match data."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wcpa.shared.paths import DATA_DIR

YEARS = [
    1930,
    1934,
    1938,
    1950,
    1954,
    1958,
    1962,
    1966,
    1970,
    1974,
    1978,
    1982,
    1986,
    1990,
    1994,
    1998,
    2002,
    2006,
    2010,
    2014,
    2018,
    2022,
]

SOURCE = "openfootball_worldcup_json"
SOURCE_REPO = "https://github.com/openfootball/worldcup.json"
RAW_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/{year}/worldcup.json"
OUT_FILE = DATA_DIR / "knowledge" / "worldcup" / "history.json"
RAW_CACHE_DIR = DATA_DIR / "knowledge" / "worldcup" / "history_raw"
SEED_FILE = Path(__file__).resolve().parents[1] / "wcpa" / "worldcup" / "history_seed.json"

HOST_COUNTRIES = {
    1930: ["Uruguay"],
    1934: ["Italy"],
    1938: ["France"],
    1950: ["Brazil"],
    1954: ["Switzerland"],
    1958: ["Sweden"],
    1962: ["Chile"],
    1966: ["England"],
    1970: ["Mexico"],
    1974: ["West Germany"],
    1978: ["Argentina"],
    1982: ["Spain"],
    1986: ["Mexico"],
    1990: ["Italy"],
    1994: ["United States"],
    1998: ["France"],
    2002: ["South Korea", "Japan"],
    2006: ["Germany"],
    2010: ["South Africa"],
    2014: ["Brazil"],
    2018: ["Russia"],
    2022: ["Qatar"],
}

FINALISTS = {
    1930: ("Uruguay", "Argentina"),
    1934: ("Italy", "Czechoslovakia"),
    1938: ("Italy", "Hungary"),
    1950: ("Uruguay", "Brazil"),
    1954: ("West Germany", "Hungary"),
    1958: ("Brazil", "Sweden"),
    1962: ("Brazil", "Czechoslovakia"),
    1966: ("England", "West Germany"),
    1970: ("Brazil", "Italy"),
    1974: ("West Germany", "Netherlands"),
    1978: ("Argentina", "Netherlands"),
    1982: ("Italy", "West Germany"),
    1986: ("Argentina", "West Germany"),
    1990: ("West Germany", "Argentina"),
    1994: ("Brazil", "Italy"),
    1998: ("France", "Brazil"),
    2002: ("Brazil", "Germany"),
    2006: ("Italy", "France"),
    2010: ("Spain", "Netherlands"),
    2014: ("Germany", "Argentina"),
    2018: ("France", "Croatia"),
    2022: ("Argentina", "France"),
}


def main() -> None:
    editions: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    finals: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    for year in YEARS:
        source_url = RAW_URL.format(year=year)
        payload = _load_year_payload(year, source_url)
        year_matches = [
            _normalize_match(year, index + 1, row, source_url)
            for index, row in enumerate(payload.get("matches", []))
        ]
        matches.extend(year_matches)
        final_match = _find_final_match(year, year_matches)
        if final_match:
            finals.append(final_match | {"champion": FINALISTS[year][0], "runner_up": FINALISTS[year][1]})

        dates = sorted([row["date"] for row in year_matches if row.get("date")])
        teams = sorted(
            {
                team
                for row in year_matches
                for team in (row.get("home_team"), row.get("away_team"))
                if team
            }
        )
        editions.append(
            {
                "year": year,
                "name": payload.get("name") or f"World Cup {year}",
                "host_countries": HOST_COUNTRIES.get(year, []),
                "champion": FINALISTS[year][0],
                "runner_up": FINALISTS[year][1],
                "match_count": len(year_matches),
                "team_count": len(teams),
                "start_date": dates[0] if dates else None,
                "end_date": dates[-1] if dates else None,
                "source": SOURCE,
                "source_url": source_url,
            }
        )

    payload = json.dumps(
        {
            "source": {
                "name": SOURCE,
                "repo": SOURCE_REPO,
                "license": "CC0-1.0",
                "fetched_at": fetched_at,
            },
            "editions": editions,
            "matches": matches,
            "finals": finals,
        },
        ensure_ascii=False,
        indent=2,
    )
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(payload, encoding="utf-8")
    SEED_FILE.write_text(payload, encoding="utf-8")
    print(f"Wrote {len(editions)} editions and {len(matches)} matches to {OUT_FILE}")


def _load_year_payload(year: int, source_url: str) -> dict[str, Any]:
    cache_file = RAW_CACHE_DIR / f"{year}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    payload = _fetch_json(source_url)
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "worldcup-prediction-agent/0.1",
        },
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def _normalize_match(year: int, index: int, row: dict[str, Any], source_url: str) -> dict[str, Any]:
    score = row.get("score") or {}
    home_score, away_score = _score_pair(score.get("ft"))
    home_score_et, away_score_et = _score_pair(score.get("et"))
    home_penalty, away_penalty = _score_pair(score.get("p"))
    venue, city = _split_ground(row.get("ground"))
    home = row.get("team1")
    away = row.get("team2")
    winner = _winner(
        home,
        away,
        home_score,
        away_score,
        home_score_et,
        away_score_et,
        home_penalty,
        away_penalty,
    )
    stable = f"{year}:{index}:{row.get('date')}:{home}:{away}"
    return {
        "match_id": f"history-{year}-{index:03d}-{hashlib.sha1(stable.encode('utf-8')).hexdigest()[:8]}",
        "year": year,
        "stage": _normalize_stage(row.get("round"), row.get("group")),
        "round": row.get("round"),
        "group_name": row.get("group"),
        "date": row.get("date"),
        "time": row.get("time"),
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "home_score_et": home_score_et,
        "away_score_et": away_score_et,
        "home_penalty": home_penalty,
        "away_penalty": away_penalty,
        "winner_team": winner,
        "venue": venue,
        "city": city,
        "source": SOURCE,
        "source_url": source_url,
    }


def _score_pair(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, list) and len(value) >= 2:
        return _int_or_none(value[0]), _int_or_none(value[1])
    return None, None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _winner(
    home: str | None,
    away: str | None,
    home_score: int | None,
    away_score: int | None,
    home_score_et: int | None,
    away_score_et: int | None,
    home_penalty: int | None,
    away_penalty: int | None,
) -> str | None:
    if home_penalty is not None and away_penalty is not None and home_penalty != away_penalty:
        return home if home_penalty > away_penalty else away
    if home_score_et is not None and away_score_et is not None and home_score_et != away_score_et:
        return home if home_score_et > away_score_et else away
    if home_score is None or away_score is None or home_score == away_score:
        return None
    return home if home_score > away_score else away


def _split_ground(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) >= 2:
        return ", ".join(parts[:-1]), parts[-1]
    return value, None


def _normalize_stage(round_name: str | None, group_name: str | None) -> str:
    text = (round_name or "").casefold()
    if group_name or "matchday" in text or "group" in text:
        return "group"
    if "round of 16" in text:
        return "R16"
    if "quarter" in text:
        return "QF"
    if "semi" in text:
        return "SF"
    if "third" in text:
        return "ThirdPlace"
    if text.strip() == "final":
        return "Final"
    if "final round" in text:
        return "FinalRound"
    return re_slug(round_name or "unknown")


def re_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"


def _find_final_match(year: int, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    if year == 1950:
        return next(
            (
                row
                for row in matches
                if {row.get("home_team"), row.get("away_team")} == {"Uruguay", "Brazil"}
            ),
            None,
        )
    return next((row for row in matches if row.get("stage") == "Final"), None)


if __name__ == "__main__":
    main()
