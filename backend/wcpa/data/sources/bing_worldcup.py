"""Bing Sports single-source collector for the 2026 World Cup knowledge base."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

from wcpa.schemas.artifact import DataSourceStatus
from wcpa.shared.env import env_int, env_str
from wcpa.shared.paths import DATA_DIR


BING_WORLD_CUP_URL = (
    "https://www.bing.com/sportsdetails?"
    "q=%E4%B8%96%E7%95%8C%E6%9D%AF%E8%B5%9B%E7%A8%8B"
    "&sport=Soccer&scenario=League&TimezoneId=China%20Standard%20Time"
    "&IANATimezoneId=Asia/Shanghai&ISOTimezoneKey=CST"
    "&league=Soccer_InternationalWorldCup&intent=Schedule&seasonyear=2026"
    "&segment=sports&isl2=true&fromhere=1065311640&form=ANNTH1&"
)

BING_BASE = "https://www.bing.com"
KNOWLEDGE_DIR = DATA_DIR / "knowledge" / "bing"

STAGE_LABELS = {
    "32 强赛": "R32",
    "16 强赛": "R16",
    "四分之一决赛": "QF",
    "半决赛": "SF",
    "季军赛": "ThirdPlace",
    "决赛": "Final",
}

TAB_INTENTS = {
    "matches": "Schedule",
    "bracket": "Bracket",
    "standings": "Standings",
    "player_stats": "Stats",
}


@dataclass(frozen=True)
class SourceSnapshot:
    source_key: str
    url: str
    status: DataSourceStatus
    raw: dict[str, Any]


@dataclass(frozen=True)
class BingKnowledgeRun:
    run_id: str
    fetched_at: datetime
    source_url: str
    snapshots: list[SourceSnapshot]
    records: dict[str, list[dict[str, Any]]]
    manifest: dict[str, Any]


class BingSportsWorldCupCollector:
    """Collects Bing Sports World Cup tabs and infinite-scroll schedule pages."""

    def __init__(self, timeout: float = 15.0, max_scroll_pages: int | None = None):
        self.timeout = timeout
        self.max_scroll_pages = max_scroll_pages or env_int("WCPA_BING_MAX_SCROLL_PAGES", 12)
        self.source_url = env_str("WCPA_BING_SCHEDULE_URL", BING_WORLD_CUP_URL) or BING_WORLD_CUP_URL

    def collect(self) -> BingKnowledgeRun:
        fetched_at = datetime.now(timezone.utc)
        run_id = fetched_at.strftime("%Y%m%dT%H%M%SZ")
        raw_dir = KNOWLEDGE_DIR / "raw" / run_id
        raw_dir.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            home = self._fetch(client, self.source_url)
            self._write_raw(raw_dir, "sportsdetails.html", home.text)
            tab_urls = self._extract_tab_urls(home.text, str(home.url))
            meta = self._parse_home_meta(home.text)

            schedule_pages = [home.text]
            schedule_urls = [str(home.url)]
            schedule_pages.extend(self._collect_schedule_scroll(client, home.text, str(home.url), raw_dir, schedule_urls))

            tab_html: dict[str, str] = {}
            for record_type, intent in TAB_INTENTS.items():
                if record_type == "matches":
                    continue
                url = tab_urls.get(intent) or self._build_tab_url(intent)
                response = self._fetch(client, url)
                tab_html[record_type] = response.text
                self._write_raw(raw_dir, f"{record_type}.html", response.text)

        matches = self._parse_matches(schedule_pages, schedule_urls)
        bracket = self._parse_bracket(tab_html.get("bracket", ""))
        standings = self._parse_standings(tab_html.get("standings", ""))
        player_stats = self._parse_player_stats(tab_html.get("player_stats", ""))
        news: list[dict[str, Any]] = []
        teams = self._build_teams(matches, standings, player_stats)

        records = {
            "matches": matches,
            "bracket": bracket,
            "news": news,
            "standings": standings,
            "player_stats": player_stats,
            "teams": teams,
        }
        manifest = self._build_manifest(run_id, fetched_at, meta, records, raw_dir)
        snapshots = [
            SourceSnapshot(
                source_key="bing_sports_worldcup",
                url=self.source_url,
                status=DataSourceStatus(
                    source_key="bing_sports_worldcup",
                    status="ok",
                    credibility="B",
                    fetched_at=fetched_at,
                    records=len(matches),
                    message=(
                        f"Bing Sports single source collected {len(matches)} matches, "
                        f"{len(standings)} standings rows, {len(player_stats)} stat rows."
                    ),
                ),
                raw={
                    "run_id": run_id,
                    "manifest": manifest,
                    "records": records,
                },
            )
        ]
        return BingKnowledgeRun(
            run_id=run_id,
            fetched_at=fetched_at,
            source_url=self.source_url,
            snapshots=snapshots,
            records=records,
            manifest=manifest,
        )

    def _fetch(self, client: httpx.Client, url: str) -> httpx.Response:
        return client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 WorldCupOracle-BingKB/1.0",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                "Referer": self.source_url,
            },
        )

    def _collect_schedule_scroll(
        self,
        client: httpx.Client,
        first_html: str,
        current_url: str,
        raw_dir: Path,
        schedule_urls: list[str],
    ) -> list[str]:
        pages: list[str] = []
        for direction in ("tillhere", "fromhere"):
            cursor = self._extract_scroll_cursor(first_html, direction)
            seen = set()
            for page_index in range(self.max_scroll_pages):
                if not cursor or cursor in seen:
                    break
                seen.add(cursor)
                url = self._build_scroll_url(direction, cursor)
                response = self._fetch(client, url)
                if response.status_code >= 400 or len(response.text) < 200:
                    break
                pages.append(response.text)
                schedule_urls.append(url)
                self._write_raw(raw_dir, f"schedule_{direction}_{page_index + 1}.html", response.text)
                next_cursor = self._extract_scroll_cursor(response.text, direction)
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
        return pages

    def _build_scroll_url(self, direction: str, cursor: str) -> str:
        query = {
            "q": "",
            "sport": "Soccer",
            "scenario": "League",
            "TimezoneId": "China Standard Time",
            "IANATimezoneId": "Asia/Shanghai",
            "ISOTimezoneKey": "CST",
            "league": "Soccer_InternationalWorldCup",
            "intent": "Schedule",
            "seasonyear": "2026",
            "segment": "sports",
            "isl2": "true",
            "isajax": "true",
            "TopAjaxTabReq": "true",
            "IsInfiniteScrollAjax": "true",
            direction: cursor,
        }
        return f"{BING_BASE}/bingsportstab?{urlencode(query)}"

    def _build_tab_url(self, intent: str) -> str:
        query = {
            "q": "世界杯报道",
            "sport": "Soccer",
            "scenario": "League",
            "TimezoneId": "China Standard Time",
            "IANATimezoneId": "Asia/Shanghai",
            "ISOTimezoneKey": "CST",
            "league": "Soccer_InternationalWorldCup",
            "intent": intent,
            "seasonyear": "2026",
            "TopAjaxTabReq": "true",
            "isajax": "true",
            "segment": "sports",
            "ansposition": "Default",
            "isl2": "true",
        }
        return f"{BING_BASE}/bingsportstab?{urlencode(query)}"

    def _extract_tab_urls(self, text: str, base_url: str) -> dict[str, str]:
        urls: dict[str, str] = {}
        for raw_url in re.findall(r'data-url="([^"]+)"', text):
            url = html.unescape(raw_url)
            if "/bingsportstab" not in url:
                continue
            intent = parse_qs(urlparse(url).query).get("intent", [""])[0]
            if intent:
                urls[intent] = urljoin(base_url, url)
        return urls

    def _extract_scroll_cursor(self, text: str, direction: str) -> str | None:
        match = re.search(rf"{direction}=(\d+)", html.unescape(text))
        return match.group(1) if match else None

    def _parse_home_meta(self, text: str) -> dict[str, Any]:
        title_match = re.search(r'<div[^>]*class="[^"]*bsp_league_title[^"]*"[^>]*>(.*?)</div>', text, re.S)
        date_match = re.search(r"(11 六月\s*-\s*19 七月 2026|11月.*?2026|6月.*?2026)", text)
        tabs = []
        for label in ["比赛", "赛程表", "资讯", "排名", "统计信息"]:
            if label in text:
                tabs.append(label)
        return {
            "title": _strip_html(title_match.group(1)) if title_match else "世界杯报道",
            "date_range": date_match.group(1) if date_match else "",
            "tabs": tabs or ["比赛", "赛程表", "排名", "统计信息"],
        }

    def _parse_matches(self, pages: list[str], page_urls: list[str]) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for page_index, text in enumerate(pages):
            source_url = page_urls[min(page_index, len(page_urls) - 1)] if page_urls else self.source_url
            labels = re.findall(r'<a aria-label="([^"]+)" href="([^"]+)"', text)
            for label_raw, href_raw in labels:
                label = html.unescape(label_raw)
                href = html.unescape(href_raw)
                if "对阵" not in label or "gameid=" not in href:
                    continue
                parsed = self._parse_match_label(label)
                if parsed is None:
                    continue
                query = parse_qs(urlparse(href).query)
                match_id = query.get("gameid", [""])[0]
                if not match_id:
                    continue
                detail_url = urljoin(source_url, href)
                home_team_id = query.get("team", [""])[0]
                away_team_id = query.get("team2", [""])[0]
                venue_id = self._extract_venue_id(href)
                rows[match_id] = {
                    **parsed,
                    "match_id": match_id,
                    "home_sport_radar_id": home_team_id,
                    "away_sport_radar_id": away_team_id,
                    "venue_id": venue_id,
                    "detail_url": detail_url,
                    "source": "bing_sports",
                    "source_url": detail_url,
                    "raw_label": label,
                    "confidence": 0.92,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
        return sorted(rows.values(), key=lambda row: (_round_sort(row["stage"]), row.get("kickoff_label", ""), row["match_id"]))

    def _parse_match_label(self, label: str) -> dict[str, Any] | None:
        prefix = re.match(r"查看\s+(?P<home>.+?)\s+对阵\s+(?P<away>.+?)\s+的详细信息,\s+(?P<rest>.+)", label)
        if not prefix:
            return None
        home = prefix.group("home").strip()
        away = prefix.group("away").strip()
        parts = [part.strip() for part in prefix.group("rest").split(",")]
        if len(parts) < 2:
            return None
        stage_label = parts[0]
        stage = STAGE_LABELS.get(stage_label, "group" if stage_label.startswith("组 ") else stage_label)
        group = stage_label.replace("组 ", "").strip() if stage_label.startswith("组 ") else None
        home_score = away_score = None
        status = "scheduled"
        kickoff_label = ""
        date_label = ""
        if "全场" in parts:
            final_index = parts.index("全场")
            home_score = _extract_score(parts[final_index - 2]) if final_index >= 2 else None
            away_score = _extract_score(parts[final_index - 1]) if final_index >= 1 else None
            status = "final"
            date_label = parts[final_index + 1] if len(parts) > final_index + 1 else ""
            kickoff_label = date_label
        elif len(parts) >= 3:
            date_label = parts[1]
            kickoff_label = f"{parts[1]} {parts[2]}"
        winner_name = None
        if home_score is not None and away_score is not None:
            winner_name = home if home_score > away_score else away if away_score > home_score else None
        return {
            "record_type": "match",
            "home_name": home,
            "away_name": away,
            "home_team_id": _stable_team_id(home),
            "away_team_id": _stable_team_id(away),
            "stage": stage,
            "stage_label": stage_label,
            "group": group,
            "home_score": home_score,
            "away_score": away_score,
            "winner_name": winner_name,
            "status": status,
            "date_label": date_label,
            "kickoff_label": kickoff_label,
            "is_actual": status == "final",
            "home_is_placeholder": _is_placeholder(home),
            "away_is_placeholder": _is_placeholder(away),
        }

    def _parse_bracket(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for match in re.finditer(r'<div class="bsp_uni_game_card_l2(?P<class>[^"]*)"(?P<attrs>[^>]*)>(?P<body>.*?</a>)</div>', text, re.S):
            attrs = match.group("attrs")
            body = match.group("body")
            match_id = _first_attr(attrs, "data-game-id")
            if not match_id:
                continue
            previous_text = text[: match.start()]
            round_index = _last_match_value(previous_text, r'<div class="bsp_round_column" data-round="(\d+)"')
            round_label = _round_label_from_index(round_index)
            href = _first_attr(body, "href")
            date = _first_text(body, r'<span class="bsp_uni_header_left_l2">(.*?)</span>')
            status_or_time = _first_text(body, r'<span class="bsp_uni_header_right_l2">(.*?)</span>')
            names = [html.unescape(name).strip() for name in re.findall(r'<span class="bsp_uni_team_name_l2" title="([^"]*)"', body)]
            scores = [_safe_int(value) for value in re.findall(r'<span class="bsp_uni_team_score_l2">(.*?)</span>', body)]
            penalties = [_safe_int(value) for value in re.findall(r'<span class="bsp_uni_team_score_pen_l2">\((.*?)\)</span>', body)]
            home_name = names[0] if len(names) > 0 else None
            away_name = names[1] if len(names) > 1 else None
            home_score = scores[0] if len(scores) > 0 else None
            away_score = scores[1] if len(scores) > 1 else None
            home_penalty_score = penalties[0] if len(penalties) > 0 else None
            away_penalty_score = penalties[1] if len(penalties) > 1 else None
            winner_name = _winner_from_scores(home_name, away_name, home_score, away_score, home_penalty_score, away_penalty_score)
            rows.append(
                {
                    "record_type": "bracket",
                    "match_id": match_id,
                    "next_match_id": _first_attr(attrs, "data-next"),
                    "round_label": round_label,
                    "round": STAGE_LABELS.get(round_label, round_label),
                    "date_label": date,
                    "time_label": "" if status_or_time == "全场" else status_or_time,
                    "status": "final" if status_or_time == "全场" or "bsp_final" in match.group("class") else "scheduled",
                    "home_name": home_name,
                    "away_name": away_name,
                    "home_score": home_score,
                    "away_score": away_score,
                    "home_penalty_score": home_penalty_score,
                    "away_penalty_score": away_penalty_score,
                    "winner_name": winner_name,
                    "source": "bing_sports",
                    "source_url": urljoin(BING_BASE, html.unescape(href)) if href else self.source_url,
                    "raw_html_ref": _hash_text(match.group(0)),
                    "confidence": 0.88,
                }
            )

        cards = re.findall(r'<a href="([^"]*gameid=[^"]+)".*?<div class="bsp_championship_card(.*?)</a>', text, re.S)
        for href_raw, body in cards:
            href = html.unescape(href_raw)
            query = parse_qs(urlparse(href).query)
            match_id = query.get("gameid", [""])[0]
            names = [_strip_html(name) for name in re.findall(r'title="([^"]+)"', body)]
            names = [name for name in names if name and not name.startswith("http")]
            header = _first_text(body, r'<div class="bsp_champ_card_header"[^>]*>(.*?)</div>')
            date = _first_text(body, r'<span class="bsp_champ_date"><span>(.*?)</span></span>')
            time = _first_text(body, r'<span class="bsp_champ_time">(.*?)</span>')
            if match_id:
                rows.append(
                    {
                        "record_type": "bracket",
                        "match_id": match_id,
                        "round_label": header,
                        "round": STAGE_LABELS.get(header, header),
                        "home_name": names[0] if len(names) > 0 else None,
                        "away_name": names[1] if len(names) > 1 else None,
                        "date_label": date,
                        "time_label": time,
                        "source": "bing_sports",
                        "source_url": urljoin(BING_BASE, href),
                        "raw_html_ref": _hash_text(body),
                        "confidence": 0.85,
                    }
                )
        return _dedupe_records(rows, ("match_id",))

    def _parse_standings(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        headers = list(re.finditer(r'<tr role="row" class="bsp_row_hdr".*?</tr>', text, re.S))
        for index, header in enumerate(headers):
            group_label = _first_attr(header.group(0), "title")
            body_start = header.end()
            body_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
            body = text[body_start:body_end]
            for row_match in re.finditer(r'<tr role="presentation" class="bsp_row_item.*?</tr>', body, re.S):
                row_html = row_match.group(0)
                team = _first_text(row_html, r'<span class="bsp_row_teamname" title="([^"]+)">')
                rank = _safe_int(_first_text(row_html, r'<span class="bsp_row_rank">(.*?)</span>'))
                values = [
                    _safe_int(_strip_html(value))
                    for value in re.findall(r'<div role="cell" class="colVal(?: bsp_col_pts)?">(.*?)</div>', row_html, re.S)
                ]
                if not team or len(values) < 8:
                    continue
                rows.append(
                    {
                        "record_type": "standing",
                        "group": group_label.replace(" 组", "").strip(),
                        "rank": rank,
                        "team_name": team,
                        "team_id": _stable_team_id(team),
                        "played": values[0],
                        "won": values[1],
                        "drawn": values[2],
                        "lost": values[3],
                        "goals_for": values[4],
                        "goals_against": values[5],
                        "goal_difference": values[6],
                        "points": values[7],
                        "source": "bing_sports",
                        "source_url": self.source_url,
                        "raw_html_ref": _hash_text(row_html),
                        "confidence": 0.9,
                    }
                )
        return _dedupe_records(rows, ("group", "team_name"))

    def _parse_player_stats(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        categories = ["进球数", "助攻", "黄牌", "红牌"]
        for index, category in enumerate(categories):
            start = text.find(f'id="{category}_Panel"')
            if start < 0:
                continue
            following = [
                text.find(f'id="{next_category}_Panel"', start + 1)
                for next_category in categories[index + 1 :]
                if text.find(f'id="{next_category}_Panel"', start + 1) > 0
            ]
            end = min(following) if following else len(text)
            panel = text[start:end]
            for row_html in re.findall(r'<tr class="bsp_mgz_lgstat_row".*?</tr>', panel, re.S):
                player = _first_text(row_html, r'<span class="bsp_player_name">(.*?)</span>')
                team = _first_text(row_html, r'<span class="bsp_team_name">(.*?)</span>')
                value = _safe_int(_first_text(row_html, r'<div class="bsp_td_stat"><span>(.*?)</span></div>'))
                image = _first_attr(row_html, "src")
                if not player:
                    continue
                rows.append(
                    {
                        "record_type": "player_stat",
                        "category": category,
                        "player_name": player,
                        "team_name": team,
                        "title": f"{player} {team} {value if value is not None else ''}".strip(),
                        "content": f"{player} {team} {value if value is not None else ''}".strip(),
                        "value": value,
                        "image_url": image or None,
                        "source": "bing_sports",
                        "source_url": self.source_url,
                        "raw_html_ref": _hash_text(row_html),
                        "confidence": 0.9,
                    }
                )
        return _dedupe_records(rows, ("category", "player_name", "team_name"))

    def _parse_news(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        blocks = re.findall(r'<li class="b_algo".*?</li>|<div[^>]+class="[^"]*(?:news|card)[^"]*".*?</div>', text, re.S | re.I)
        for block in blocks:
            link = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
            if not link:
                continue
            title = _strip_html(link.group(2))
            if len(title) < 6:
                continue
            snippet = _first_text(block, r"<p>(.*?)</p>")
            img = re.search(r'<img[^>]+src="([^"]+)"', block)
            rows.append(
                {
                    "record_type": "news",
                    "title": title,
                    "summary": snippet,
                    "image_url": html.unescape(img.group(1)) if img else None,
                    "source": "bing_sports",
                    "source_url": urljoin(BING_BASE, html.unescape(link.group(1))),
                    "raw_html_ref": _hash_text(block),
                    "confidence": 0.4,
                }
            )
            if len(rows) >= 40:
                break
        return _dedupe_records(rows, ("title", "source_url"))

    def _build_teams(
        self,
        matches: list[dict[str, Any]],
        standings: list[dict[str, Any]],
        player_stats: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        teams: dict[str, dict[str, Any]] = {}
        for match in matches:
            for side in ("home", "away"):
                name = match[f"{side}_name"]
                if _is_placeholder(name):
                    continue
                team_id = match[f"{side}_team_id"]
                teams.setdefault(
                    team_id,
                    {
                        "record_type": "team",
                        "team_id": team_id,
                        "name": name,
                        "sport_radar_id": match.get(f"{side}_sport_radar_id"),
                        "source": "bing_sports",
                        "source_url": match["source_url"],
                        "verified": True,
                        "confidence": 0.8,
                    },
                )
        for row in standings:
            name = row.get("team_name")
            if name and not _is_placeholder(name):
                team_id = _stable_team_id(name)
                teams.setdefault(
                    team_id,
                    {
                        "record_type": "team",
                        "team_id": team_id,
                        "name": name,
                        "source": "bing_sports",
                        "source_url": row["source_url"],
                        "verified": True,
                        "confidence": 0.65,
                    },
                )
        return sorted(teams.values(), key=lambda row: row["name"])

    def _build_manifest(
        self,
        run_id: str,
        fetched_at: datetime,
        meta: dict[str, Any],
        records: dict[str, list[dict[str, Any]]],
        raw_dir: Path,
    ) -> dict[str, Any]:
        counts = {key: len(value) for key, value in records.items()}
        missing = []
        if counts.get("matches", 0) < 104:
            missing.append(f"expected_104_matches_got_{counts.get('matches', 0)}")
        for key in ("bracket", "standings", "player_stats"):
            if counts.get(key, 0) == 0:
                missing.append(f"{key}_empty")
        return {
            "run_id": run_id,
            "source": "bing_sports",
            "source_url": self.source_url,
            "fetched_at": fetched_at.isoformat(),
            "meta": meta,
            "counts": counts,
            "status": "ready" if not missing else "partial",
            "missing": missing,
            "raw_dir": str(raw_dir),
        }

    def _write_raw(self, raw_dir: Path, filename: str, text: str) -> None:
        (raw_dir / filename).write_text(text, encoding="utf-8")

    def _extract_venue_id(self, href: str) -> str | None:
        decoded = html.unescape(href)
        match = re.search(r'SportRadar_Soccer_InternationalWorldCup_2026_Venue_\d+', decoded)
        return match.group(0) if match else None


def write_bing_knowledge_files(run: BingKnowledgeRun, output_dir: Path = KNOWLEDGE_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for record_type, rows in run.records.items():
        path = output_dir / f"{record_type}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        paths[record_type] = str(path)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(run.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["manifest"] = str(manifest_path)
    return {"paths": paths, "manifest": run.manifest}


def load_bing_manifest(output_dir: Path = KNOWLEDGE_DIR) -> dict[str, Any] | None:
    path = output_dir / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_bing_records(record_type: str, output_dir: Path = KNOWLEDGE_DIR, limit: int | None = None) -> list[dict[str, Any]]:
    path = output_dir / f"{record_type}.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def _strip_html(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<.*?>", " ", value, flags=re.S)
    return re.sub(r"\s+", " ", value).strip()


def _first_text(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.S)
    return _strip_html(match.group(1)) if match else ""


def _first_attr(text: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', text, re.S)
    return html.unescape(match.group(1)) if match else ""


def _last_match_value(text: str, pattern: str) -> str:
    matches = re.findall(pattern, text, re.S)
    return matches[-1] if matches else ""


def _round_label_from_index(value: str) -> str:
    return {
        "0": "32 强赛",
        "1": "16 强赛",
        "2": "四分之一决赛",
        "3": "半决赛",
        "4": "决赛",
    }.get(value, "")


def _winner_from_scores(
    home_name: str | None,
    away_name: str | None,
    home_score: int | None,
    away_score: int | None,
    home_penalty_score: int | None,
    away_penalty_score: int | None,
) -> str | None:
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return home_name
    if away_score > home_score:
        return away_name
    if home_penalty_score is not None and away_penalty_score is not None:
        if home_penalty_score > away_penalty_score:
            return home_name
        if away_penalty_score > home_penalty_score:
            return away_name
    return None


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _extract_score(value: Any) -> int | None:
    numbers = re.findall(r"\d+", str(value))
    return int(numbers[-1]) if numbers else None


def _is_placeholder(name: str | None) -> bool:
    text = str(name or "").strip()
    return bool(
        text
        and (
            re.fullmatch(r"[WL]\d+", text, re.IGNORECASE)
            or text.upper() in {"TBD", "TBC", "UNKNOWN", "N/A", "NA"}
            or text in {"待定", "待确认", "未确定"}
        )
    )


TEAM_ID_BY_ZH_NAME = {
    "澳大利亚": "AUS",
    "埃及": "EGY",
    "阿根廷": "ARG",
    "佛得角": "CPV",
    "哥伦比亚": "COL",
    "加纳": "GHA",
    "加拿大": "CAN",
    "摩洛哥": "MAR",
    "巴拉圭": "PAR",
    "法国": "FRA",
    "巴西": "BRA",
    "挪威": "NOR",
    "墨西哥": "MEX",
    "英格兰": "ENG",
    "葡萄牙": "POR",
    "西班牙": "ESP",
    "美国": "USA",
    "比利时": "BEL",
    "瑞士": "SUI",
    "德国": "GER",
    "荷兰": "NED",
    "瑞典": "SWE",
    "日本": "JPN",
    "乌拉圭": "URU",
    "新西兰": "NZL",
    "土耳其": "TUR",
    "韩国": "KOR",
    "南非": "RSA",
    "沙特阿拉伯": "KSA",
    "伊朗": "IRN",
    "苏格兰": "SCO",
    "海地": "HAI",
    "卡塔尔": "QAT",
    "奥地利": "AUT",
    "塞内加尔": "SEN",
}


def _stable_team_id(name: str) -> str:
    name = name.strip()
    if _is_placeholder(name):
        return name
    if name in TEAM_ID_BY_ZH_NAME:
        return TEAM_ID_BY_ZH_NAME[name]
    ascii_key = re.sub(r"[^A-Za-z0-9]+", "", name.upper())
    if ascii_key:
        return ascii_key[:12]
    return "BING_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()


def _round_sort(stage: str) -> int:
    order = {"group": 0, "R32": 1, "R16": 2, "QF": 3, "SF": 4, "ThirdPlace": 5, "Final": 6}
    return order.get(stage, 99)


def _dedupe_records(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for row in rows:
        key = tuple(row.get(item) for item in keys)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
