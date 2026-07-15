"""Assemble source-backed model features for the teams still in contention."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from wcpa.agents.firecrawl_client import FirecrawlCallError, FirecrawlClient
from wcpa.agents.search import SearchCallError, SearchConfigError, search_web
from wcpa.data.real_dataset import DataUnavailableError
from wcpa.schemas.artifact import DataQualityReport, DataSourceStatus
from wcpa.schemas.team import Team
from wcpa.shared.paths import DATA_DIR


FIFA_RANKING_URL = "https://inside.fifa.com/fifa-world-ranking/men"
ELO_RATING_URL = "https://www.eloratings.net/"
IDENTITY_FILE = DATA_DIR / "knowledge" / "worldcup" / "teams.json"
HISTORY_FILE = DATA_DIR / "knowledge" / "worldcup" / "history.json"
CACHE_DIR = DATA_DIR / "cache" / "prediction_sources"
RATING_CACHE = CACHE_DIR / "live_team_ratings.json"
HEALTH_CACHE = CACHE_DIR / "live_team_health.json"


@dataclass(frozen=True)
class LiveTeamFeatureResult:
    teams: list[Team]
    report: DataQualityReport


class LiveTeamFeatureAssembler:
    """Join live ratings, current results and web evidence into model-ready teams."""

    def __init__(
        self,
        firecrawl: FirecrawlClient | None = None,
        search: Callable[..., Any] = search_web,
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self.firecrawl = firecrawl or FirecrawlClient()
        self.search = search
        self.cache_dir = cache_dir

    def build(
        self,
        schedule: list[dict[str, Any]],
        required_team_ids: list[str],
        now: datetime | None = None,
        allow_live_sources: bool = True,
    ) -> LiveTeamFeatureResult:
        generated_at = now or datetime.now(timezone.utc)
        required = sorted({str(team_id) for team_id in required_team_ids if team_id})
        identities = _load_identities()
        invalid: list[dict[str, Any]] = []
        statuses: list[DataSourceStatus] = []

        performance = _current_performance(schedule, required)
        statuses.append(
            DataSourceStatus(
                source_key="worldcup_completed_results_features",
                status="available" if all(team_id in performance for team_id in required) else "partial",
                credibility="B",
                fetched_at=generated_at,
                records=len(performance),
                message="近期状态和攻防分数由当前世界杯已完成比赛计算。",
            )
        )
        experience = _historical_experience(required, identities)
        statuses.append(
            DataSourceStatus(
                source_key="openfootball_worldcup_history_features",
                status="available" if all(team_id in experience for team_id in required) else "partial",
                credibility="B",
                fetched_at=generated_at,
                records=len(experience),
                message="世界杯经验分数由历史世界杯比赛记录计算。",
            )
        )
        if allow_live_sources:
            ratings, rating_statuses = self._ratings(required, identities, generated_at)
        else:
            ratings = {}
            rating_statuses = [
                DataSourceStatus(
                    source_key="fifa_live_mens_ranking",
                    status="not_connected",
                    credibility="D",
                    fetched_at=generated_at,
                    records=0,
                    message="历史预测起点回放不读取生成时刻的实时 FIFA 排名。",
                ),
                DataSourceStatus(
                    source_key="world_football_elo_live",
                    status="not_connected",
                    credibility="D",
                    fetched_at=generated_at,
                    records=0,
                    message="历史预测起点回放不读取生成时刻的实时 Elo 评级。",
                ),
            ]
        statuses.extend(rating_statuses)
        derived_ratings = _derived_ratings(required, performance, experience)
        rating_fallback_count = 0
        for team_id in required:
            if team_id not in ratings and team_id in derived_ratings:
                ratings[team_id] = derived_ratings[team_id]
                rating_fallback_count += 1
        statuses.append(
            DataSourceStatus(
                source_key="worldcup_results_derived_team_rating",
                status="available" if rating_fallback_count else "not_connected",
                credibility="C" if rating_fallback_count else "D",
                fetched_at=generated_at,
                records=rating_fallback_count,
                message=(
                    "实时 FIFA/Elo 缺失的球队使用本届已锁定赛果与世界杯历史经验生成保守强度特征。"
                    if rating_fallback_count
                    else "全部所需球队已有实时排名和 Elo 特征。"
                ),
            )
        )
        if allow_live_sources:
            health, health_statuses = self._health(required, identities, generated_at)
        else:
            health = {}
            health_statuses = [
                DataSourceStatus(
                    source_key="live_squad_health",
                    status="not_connected",
                    credibility="D",
                    fetched_at=generated_at,
                    records=0,
                    message="历史预测起点回放不读取生成时刻之后的阵容、伤停或停赛信息。",
                )
            ]
        statuses.extend(health_statuses)
        health_fallback_count = 0
        for team_id in required:
            if team_id not in health:
                health[team_id] = {
                    "score": 0.82,
                    "records": 0,
                    "derived": True,
                }
                health_fallback_count += 1
        statuses.append(
            DataSourceStatus(
                source_key="neutral_squad_availability_assumption",
                status="partial" if health_fallback_count else "not_connected",
                credibility="C" if health_fallback_count else "D",
                fetched_at=generated_at,
                records=health_fallback_count,
                message=(
                    "未取得可追溯阵容健康证据的球队使用中性可用度；确认伤停未进入模型。"
                    if health_fallback_count
                    else "全部所需球队已有阵容健康证据。"
                ),
            )
        )

        teams: list[Team] = []
        for team_id in required:
            identity = identities.get(team_id)
            rating = ratings.get(team_id)
            form = performance.get(team_id)
            health_row = health.get(team_id)
            confederation = CONFEDERATIONS.get(team_id)
            rating_is_derived = bool(rating and rating.get("derived"))
            health_is_derived = bool(health_row and health_row.get("derived"))
            missing = [
                name
                for name, value in (
                    ("identity", identity),
                    ("confederation", confederation),
                    ("fifa_rank", rating and rating.get("fifa_rank")),
                    ("elo_rating", rating and rating.get("elo_rating")),
                    ("current_performance", form),
                    ("squad_health", health_row),
                    ("world_cup_experience", experience.get(team_id)),
                )
                if value is None
            ]
            if missing:
                invalid.append({"dataset": "live_team_features", "id": team_id, "reason": "missing_source_backed_fields", "fields": missing})
                continue
            teams.append(
                Team(
                    team_id=team_id,
                    name=str(identity.get("name_zh") or identity.get("name_en") or team_id),
                    confederation=str(confederation),
                    fifa_rank=int(rating["fifa_rank"]),
                    elo_rating=int(rating["elo_rating"]),
                    recent_form_score=float(form["recent_form_score"]),
                    attack_score=float(form["attack_score"]),
                    defense_score=float(form["defense_score"]),
                    squad_health_score=float(health_row["score"]),
                    world_cup_experience_score=float(experience[team_id]),
                    data_quality="C" if rating_is_derived or health_is_derived else "B",
                    source_key=(
                        "worldcup_results_derived_rating+neutral_health"
                        if rating_is_derived or health_is_derived
                        else "fifa+eloratings+worldcup_results+firecrawl"
                    ),
                    source_url="" if rating_is_derived else FIFA_RANKING_URL,
                    verified=True,
                )
            )

        if invalid:
            report = DataQualityReport(
                status="data_unavailable",
                strict=True,
                invalid_records=invalid,
                source_statuses=statuses,
                message="当前存活球队仍缺少可追溯的模型特征。",
            )
            raise DataUnavailableError(report)
        report = DataQualityReport(
            status="ready",
            strict=True,
            source_statuses=statuses,
            message="当前存活球队的排名、Elo、赛会表现、历史经验与阵容健康证据已完成装配。",
        )
        return LiveTeamFeatureResult(teams=teams, report=report)

    def _ratings(
        self,
        required: list[str],
        identities: dict[str, dict[str, Any]],
        now: datetime,
    ) -> tuple[dict[str, dict[str, Any]], list[DataSourceStatus]]:
        cache_path = self.cache_dir / RATING_CACHE.name
        cached = _read_cache(cache_path, now, timedelta(hours=6))
        rows = cached.get("teams", {}) if cached else {}
        if not all(team_id in rows for team_id in required):
            try:
                fifa = self.firecrawl.scrape(FIFA_RANKING_URL)
                elo = self.firecrawl.scrape(ELO_RATING_URL)
                fifa_rows = parse_fifa_ranking_markdown(fifa.markdown)
                elo_rows = parse_elo_ranking_markdown(elo.markdown)
                rows = {}
                for team_id in required:
                    identity = identities.get(team_id, {})
                    english_name = str(identity.get("name_en") or "")
                    fifa_rank = fifa_rows.get(team_id)
                    elo_rating = elo_rows.get(_normalize_name(english_name))
                    if fifa_rank is not None and elo_rating is not None:
                        rows[team_id] = {
                            "fifa_rank": fifa_rank,
                            "elo_rating": elo_rating,
                            "fifa_source_url": fifa.url,
                            "elo_source_url": elo.url,
                        }
                _write_cache(cache_path, {"fetched_at": now.isoformat(), "teams": rows})
            except FirecrawlCallError:
                rows = cached.get("teams", {}) if cached else {}
        statuses = [
            DataSourceStatus(
                source_key="fifa_live_mens_ranking",
                status="available" if all(team_id in rows and rows[team_id].get("fifa_rank") for team_id in required) else "partial",
                credibility="A",
                fetched_at=now,
                records=sum(1 for team_id in required if team_id in rows and rows[team_id].get("fifa_rank")),
                message="FIFA 男足实时排名用于当前存活球队的排名特征。",
            ),
            DataSourceStatus(
                source_key="world_football_elo_live",
                status="available" if all(team_id in rows and rows[team_id].get("elo_rating") for team_id in required) else "partial",
                credibility="B",
                fetched_at=now,
                records=sum(1 for team_id in required if team_id in rows and rows[team_id].get("elo_rating")),
                message="World Football Elo Ratings 用于当前存活球队的 Elo 特征。",
            ),
        ]
        return rows, statuses

    def _health(
        self,
        required: list[str],
        identities: dict[str, dict[str, Any]],
        now: datetime,
    ) -> tuple[dict[str, dict[str, Any]], list[DataSourceStatus]]:
        cache_path = self.cache_dir / HEALTH_CACHE.name
        cached = _read_cache(cache_path, now, timedelta(minutes=30))
        if cached.get("schema_version") != 2:
            cached = {}
        rows = cached.get("teams", {}) if cached else {}
        for team_id in required:
            if team_id in rows:
                continue
            identity = identities.get(team_id, {})
            team_name = str(identity.get("name_en") or team_id)
            try:
                sources = self.search(
                    f"{team_name} World Cup 2026 latest confirmed lineup injuries suspension team news",
                    limit=5,
                )
            except (SearchConfigError, SearchCallError):
                continue
            qualified = []
            for item in sources:
                text = " ".join((item.title, item.snippet, item.excerpt or "")).casefold()
                if (
                    item.source_quality_score >= 0.70
                    and item.source_type in {"official", "wire", "media"}
                    and team_name.casefold() in text
                ):
                    qualified.append((item, text))
            texts = [text for _, text in qualified]
            if not texts:
                continue
            negative_sources = sum(1 for text in texts if any(term in text for term in ACTIVE_NEGATIVE_HEALTH_TERMS))
            confirmed_sources = sum(1 for text in texts if any(term in text for term in CONFIRMATION_TERMS))
            source_scores = []
            for text in texts:
                negative = any(term in text for term in ACTIVE_NEGATIVE_HEALTH_TERMS)
                positive = any(term in text for term in CONFIRMATION_TERMS)
                source_scores.append(0.70 if negative and positive else 0.65 if negative else 0.95 if positive else 0.80)
            score = sum(source_scores) / len(source_scores)
            rows[team_id] = {
                "score": round(score, 4),
                "records": len(texts),
                "negative_sources": negative_sources,
                "confirmed_sources": confirmed_sources,
                "source_urls": [item.url for item, _ in qualified if item.url][:5],
            }
        _write_cache(cache_path, {"schema_version": 2, "fetched_at": now.isoformat(), "teams": rows})
        statuses = []
        for team_id in required:
            row = rows.get(team_id)
            statuses.append(
                DataSourceStatus(
                    source_key=f"live_squad_health:{team_id}",
                    status="available" if row else "data_unavailable",
                    credibility="B" if row else "D",
                    fetched_at=now,
                    records=int(row.get("records", 0)) if row else 0,
                    message=(
                        "已基于最新阵容、伤停和停赛来源计算阵容可用度。"
                        if row
                        else "未获取到可追溯的最新阵容健康来源。"
                    ),
                )
            )
        return rows, statuses


def parse_fifa_ranking_markdown(markdown: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in markdown.splitlines():
        if not line.startswith("| ### "):
            continue
        rank_match = re.match(r"\| ### (\d+)", line)
        code_match = re.search(r"fifa-world-ranking/([A-Z]{3})\?gender=men", line)
        if rank_match and code_match:
            result[code_match.group(1)] = int(rank_match.group(1))
    return result


def parse_elo_ranking_markdown(markdown: str) -> dict[str, int]:
    pattern = re.compile(r"\[([^\]]+)\]\(https://eloratings\.net/[^)]+\)\s+([0-9]{3,4})", re.MULTILINE)
    return {_normalize_name(name): int(rating) for name, rating in pattern.findall(markdown)}


def _current_performance(schedule: list[dict[str, Any]], required: list[str]) -> dict[str, dict[str, float]]:
    matches: dict[str, list[dict[str, Any]]] = {team_id: [] for team_id in required}
    for row in schedule:
        if str(row.get("status") or "").lower() not in {"complete", "completed", "final", "finished", "closed"}:
            continue
        home = str(row.get("home_team_id") or "")
        away = str(row.get("away_team_id") or "")
        if row.get("home_score") is None or row.get("away_score") is None:
            continue
        for team_id, opponent, goals_for, goals_against in (
            (home, away, row.get("home_score"), row.get("away_score")),
            (away, home, row.get("away_score"), row.get("home_score")),
        ):
            if team_id not in matches:
                continue
            matches[team_id].append(
                {
                    "kickoff": str(row.get("kickoff_time") or ""),
                    "opponent": opponent,
                    "goals_for": int(goals_for),
                    "goals_against": int(goals_against),
                    "winner": row.get("winner_team_id"),
                }
            )
    result: dict[str, dict[str, float]] = {}
    for team_id, rows in matches.items():
        recent = sorted(rows, key=lambda item: item["kickoff"])[-8:]
        if not recent:
            continue
        points = 0
        goals_for = 0
        goals_against = 0
        for row in recent:
            goals_for += row["goals_for"]
            goals_against += row["goals_against"]
            if row["winner"] == team_id:
                points += 3
            elif not row["winner"] and row["goals_for"] == row["goals_against"]:
                points += 1
        played = len(recent)
        result[team_id] = {
            "recent_form_score": round(points / (played * 3), 4),
            "attack_score": round(min(1.0, goals_for / (played * 3)), 4),
            "defense_score": round(max(0.0, 1 - goals_against / (played * 3)), 4),
        }
    return result


def _historical_experience(required: list[str], identities: dict[str, dict[str, Any]]) -> dict[str, float]:
    if not HISTORY_FILE.exists():
        return {}
    payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    matches = payload.get("matches") or []
    by_team: dict[str, set[int]] = {}
    for row in matches:
        year = row.get("year")
        for key in ("home_team", "away_team"):
            name = _normalize_name(str(row.get(key) or ""))
            if name and year:
                by_team.setdefault(name, set()).add(int(year))
    result = {}
    for team_id in required:
        english_name = _normalize_name(str(identities.get(team_id, {}).get("name_en") or ""))
        editions = by_team.get(english_name, set())
        result[team_id] = round(min(1.0, len(editions) / 18), 4)
    return result


def _derived_ratings(
    required: list[str],
    performance: dict[str, dict[str, float]],
    experience: dict[str, float],
) -> dict[str, dict[str, Any]]:
    scored: list[tuple[str, float]] = []
    for team_id in required:
        form = performance.get(team_id)
        if not form:
            continue
        score = (
            0.42 * float(form.get("recent_form_score", 0.5))
            + 0.24 * float(form.get("attack_score", 0.5))
            + 0.24 * float(form.get("defense_score", 0.5))
            + 0.10 * float(experience.get(team_id, 0.5))
        )
        scored.append((team_id, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    total = max(len(scored), 1)
    rows: dict[str, dict[str, Any]] = {}
    for index, (team_id, score) in enumerate(scored, 1):
        rank = max(1, min(80, index + 6))
        elo = round(1540 + 520 * score + 60 * (1 - (index - 1) / total))
        rows[team_id] = {
            "fifa_rank": rank,
            "elo_rating": int(max(1200, min(2200, elo))),
            "derived": True,
        }
    return rows


def _load_identities() -> dict[str, dict[str, Any]]:
    if not IDENTITY_FILE.exists():
        return {}
    rows = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
    return {str(row.get("team_id")): row for row in rows if row.get("team_id")}


def _read_cache(path: Path, now: datetime, max_age: timedelta) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at") or "").replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return payload if now - fetched_at <= max_age else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


ACTIVE_NEGATIVE_HEALTH_TERMS = (
    "ruled out", "will miss", "set to miss", "suspended:", "injured:",
    "is injured", "remains injured", "unavailable", "out for", "major doubt",
    "确认缺阵", "将缺席", "无法出场", "停赛：", "受伤：", "出战成疑",
)
CONFIRMATION_TERMS = (
    "confirmed lineup", "predicted lineup", "team news", "available", "returns", "fit",
    "确认首发", "预计首发", "阵容", "复出",
)


CONFEDERATIONS = {
    "ALG": "CAF", "ARG": "CONMEBOL", "AUS": "AFC", "AUT": "UEFA", "BEL": "UEFA",
    "BIH": "UEFA", "BRA": "CONMEBOL", "CAN": "CONCACAF", "CIV": "CAF", "COD": "CAF",
    "COL": "CONMEBOL", "CPV": "CAF", "CRO": "UEFA", "CUW": "CONCACAF", "CZE": "UEFA",
    "ECU": "CONMEBOL", "EGY": "CAF", "ENG": "UEFA", "ESP": "UEFA", "FRA": "UEFA",
    "GER": "UEFA", "GHA": "CAF", "HAI": "CONCACAF", "IRN": "AFC", "IRQ": "AFC",
    "JOR": "AFC", "JPN": "AFC", "KOR": "AFC", "KSA": "AFC", "MAR": "CAF",
    "MEX": "CONCACAF", "NED": "UEFA", "NOR": "UEFA", "NZL": "OFC", "PAN": "CONCACAF",
    "PAR": "CONMEBOL", "POR": "UEFA", "QAT": "AFC", "RSA": "CAF", "SCO": "UEFA",
    "SEN": "CAF", "SUI": "UEFA", "SWE": "UEFA", "TUN": "CAF", "TUR": "UEFA",
    "URU": "CONMEBOL", "USA": "CONCACAF", "UZB": "AFC",
}
