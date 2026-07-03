"""Optional PostgreSQL repository for durable artifacts and agent caches."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from wcpa.shared.env import database_url


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prediction_versions (
  id BIGSERIAL PRIMARY KEY,
  artifact_version TEXT NOT NULL,
  edition TEXT NOT NULL,
  mode TEXT NOT NULL,
  seed INTEGER NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
  cache_key TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  id BIGSERIAL PRIMARY KEY,
  source_key TEXT NOT NULL,
  url TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  credibility TEXT NOT NULL,
  payload JSONB NOT NULL,
  message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bing_knowledge_records (
  id TEXT PRIMARY KEY,
  record_type TEXT NOT NULL,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  fetched_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS worldcup_sync_runs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  parsed_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  raw_snapshot_dir TEXT
);

CREATE TABLE IF NOT EXISTS worldcup_teams (
  team_id TEXT PRIMARY KEY,
  name_en TEXT,
  name_zh TEXT,
  fifa_code TEXT,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  flag_code TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worldcup_matches (
  match_id TEXT PRIMARY KEY,
  stage TEXT NOT NULL,
  group_name TEXT,
  kickoff_time TIMESTAMPTZ,
  kickoff_label TEXT,
  home_team_id TEXT,
  away_team_id TEXT,
  winner_team_id TEXT,
  home_team_raw TEXT,
  away_team_raw TEXT,
  winner_team_raw TEXT,
  home_score INTEGER,
  away_score INTEGER,
  home_penalty INTEGER,
  away_penalty INTEGER,
  status TEXT NOT NULL,
  next_match_id TEXT,
  home_source_match_id TEXT,
  away_source_match_id TEXT,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  raw_html_file TEXT NOT NULL DEFAULT '',
  raw_content_hash TEXT NOT NULL DEFAULT '',
  parser_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  fetched_at TIMESTAMPTZ,
  parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worldcup_standings (
  id TEXT PRIMARY KEY,
  group_name TEXT,
  team_id TEXT,
  team_name_raw TEXT NOT NULL,
  played INTEGER,
  won INTEGER,
  drawn INTEGER,
  lost INTEGER,
  goals_for INTEGER,
  goals_against INTEGER,
  goal_difference INTEGER,
  points INTEGER,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  raw_content_hash TEXT NOT NULL DEFAULT '',
  parser_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  fetched_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worldcup_prediction_versions (
  id BIGSERIAL PRIMARY KEY,
  prediction_version TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  source_match_hash TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS worldcup_predictions (
  id BIGSERIAL PRIMARY KEY,
  prediction_version_id BIGINT REFERENCES worldcup_prediction_versions(id),
  match_id TEXT NOT NULL,
  predicted_home_score INTEGER,
  predicted_away_score INTEGER,
  predicted_winner_team_id TEXT,
  confidence DOUBLE PRECISION,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worldcup_agent_debates (
  id BIGSERIAL PRIMARY KEY,
  prediction_version_id BIGINT REFERENCES worldcup_prediction_versions(id),
  match_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class PostgresRepository:
    """Tiny psycopg-backed repository.

    Importing psycopg is delayed so local JSON-only development keeps working
    before optional database dependencies are installed.
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or database_url()

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.dsn)

    def init_schema(self) -> None:
        if not self.enabled:
            return
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
            conn.commit()

    def save_prediction(self, artifact: Any) -> None:
        if not self.enabled:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        payload = artifact.model_dump(mode="json")
        generated_at = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO prediction_versions
                      (artifact_version, edition, mode, seed, generated_at, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payload.get("artifact_version", ""),
                        payload.get("edition", ""),
                        payload.get("mode", ""),
                        int(payload.get("seed", 0)),
                        generated_at,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def load_agent_run(self, cache_key: str) -> dict | None:
        if not self.enabled:
            return None
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM agent_runs WHERE cache_key = %s", (cache_key,))
                row = cur.fetchone()
        return row[0] if row else None

    def save_agent_run(
        self,
        cache_key: str,
        match_id: str,
        agent_name: str,
        model: str,
        prompt_hash: str,
        payload: dict,
        token_usage: dict | None = None,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runs
                      (cache_key, match_id, agent_name, model, prompt_hash, created_at, token_usage, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (
                        cache_key,
                        match_id,
                        agent_name,
                        model,
                        prompt_hash,
                        datetime.now(timezone.utc),
                        json.dumps(token_usage or {}, ensure_ascii=False),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def save_source_snapshot(
        self,
        source_key: str,
        url: str,
        status: str,
        credibility: str,
        payload: dict,
        message: str = "",
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_snapshots
                      (source_key, url, fetched_at, status, credibility, payload, message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_key,
                        url,
                        datetime.now(timezone.utc),
                        status,
                        credibility,
                        json.dumps(payload, ensure_ascii=False),
                        message,
                    ),
                )
            conn.commit()

    def save_knowledge_records(self, records: dict[str, list[dict]], manifest: dict) -> None:
        if not self.enabled:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        fetched_at = manifest.get("fetched_at") or datetime.now(timezone.utc).isoformat()
        with conn:
            with conn.cursor() as cur:
                for record_type, rows in records.items():
                    for row in rows:
                        record_id = self._knowledge_record_id(record_type, row)
                        cur.execute(
                            """
                            INSERT INTO bing_knowledge_records
                              (id, record_type, source, source_url, fetched_at, payload)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                              fetched_at = EXCLUDED.fetched_at,
                              payload = EXCLUDED.payload
                            """,
                            (
                                record_id,
                                record_type,
                                row.get("source", "bing_sports"),
                                row.get("source_url", ""),
                                fetched_at,
                                json.dumps(row, ensure_ascii=False),
                            ),
                        )
            conn.commit()

    def load_bing_knowledge_records(self, record_type: str) -> list[dict]:
        if not self.enabled:
            return []
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return []
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload
                    FROM bing_knowledge_records
                    WHERE record_type = %s
                    ORDER BY fetched_at DESC, id
                    """,
                    (record_type,),
                )
                rows = cur.fetchall()
        return [row[0] for row in rows]

    def _knowledge_record_id(self, record_type: str, row: dict) -> str:
        stable = (
            row.get("match_id")
            or row.get("team_id")
            or row.get("raw_html_ref")
            or row.get("source_url")
            or json.dumps(row, ensure_ascii=False, sort_keys=True)
        )
        import hashlib

        return f"{record_type}:{hashlib.sha1(str(stable).encode('utf-8')).hexdigest()}"

    def save_worldcup_sync_run(
        self,
        source: str,
        started_at: datetime,
        finished_at: datetime | None,
        status: str,
        fetched_count: int = 0,
        parsed_count: int = 0,
        inserted_count: int = 0,
        updated_count: int = 0,
        error_message: str | None = None,
        raw_snapshot_dir: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO worldcup_sync_runs
                      (source, started_at, finished_at, status, fetched_count, parsed_count,
                       inserted_count, updated_count, error_message, raw_snapshot_dir)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source,
                        started_at,
                        finished_at,
                        status,
                        fetched_count,
                        parsed_count,
                        inserted_count,
                        updated_count,
                        error_message,
                        raw_snapshot_dir,
                    ),
                )
            conn.commit()

    def upsert_worldcup_teams(self, teams: list[dict]) -> None:
        if not self.enabled or not teams:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                for team in teams:
                    cur.execute(
                        """
                        INSERT INTO worldcup_teams
                          (team_id, name_en, name_zh, fifa_code, aliases, flag_code, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (team_id) DO UPDATE SET
                          name_en = COALESCE(EXCLUDED.name_en, worldcup_teams.name_en),
                          name_zh = COALESCE(EXCLUDED.name_zh, worldcup_teams.name_zh),
                          fifa_code = COALESCE(EXCLUDED.fifa_code, worldcup_teams.fifa_code),
                          aliases = EXCLUDED.aliases,
                          flag_code = COALESCE(EXCLUDED.flag_code, worldcup_teams.flag_code),
                          updated_at = EXCLUDED.updated_at
                        """,
                        (
                            team["team_id"],
                            team.get("name_en"),
                            team.get("name_zh"),
                            team.get("fifa_code"),
                            json.dumps(team.get("aliases", []), ensure_ascii=False),
                            team.get("flag_code"),
                            datetime.now(timezone.utc),
                        ),
                    )
            conn.commit()

    def upsert_worldcup_matches(self, matches: list[dict]) -> dict[str, int]:
        if not self.enabled or not matches:
            return {"inserted": 0, "updated": 0}
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return {"inserted": 0, "updated": 0}
        existing: set[str] = set()
        with conn:
            with conn.cursor() as cur:
                ids = [match["match_id"] for match in matches]
                cur.execute("SELECT match_id FROM worldcup_matches WHERE match_id = ANY(%s)", (ids,))
                existing = {row[0] for row in cur.fetchall()}
                for match in matches:
                    cur.execute(
                        """
                        INSERT INTO worldcup_matches
                          (match_id, stage, group_name, kickoff_time, kickoff_label, home_team_id,
                           away_team_id, winner_team_id, home_team_raw, away_team_raw, winner_team_raw,
                           home_score, away_score, home_penalty, away_penalty, status, next_match_id,
                           home_source_match_id, away_source_match_id, source, source_url, raw_html_file,
                           raw_content_hash, parser_version, schema_version, fetched_at, parse_warnings,
                           metadata, updated_at)
                        VALUES
                          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (match_id) DO UPDATE SET
                          stage = EXCLUDED.stage,
                          group_name = EXCLUDED.group_name,
                          kickoff_time = COALESCE(EXCLUDED.kickoff_time, worldcup_matches.kickoff_time),
                          kickoff_label = COALESCE(EXCLUDED.kickoff_label, worldcup_matches.kickoff_label),
                          home_team_id = EXCLUDED.home_team_id,
                          away_team_id = EXCLUDED.away_team_id,
                          winner_team_id = EXCLUDED.winner_team_id,
                          home_team_raw = EXCLUDED.home_team_raw,
                          away_team_raw = EXCLUDED.away_team_raw,
                          winner_team_raw = EXCLUDED.winner_team_raw,
                          home_score = EXCLUDED.home_score,
                          away_score = EXCLUDED.away_score,
                          home_penalty = EXCLUDED.home_penalty,
                          away_penalty = EXCLUDED.away_penalty,
                          status = EXCLUDED.status,
                          next_match_id = COALESCE(EXCLUDED.next_match_id, worldcup_matches.next_match_id),
                          home_source_match_id = COALESCE(EXCLUDED.home_source_match_id, worldcup_matches.home_source_match_id),
                          away_source_match_id = COALESCE(EXCLUDED.away_source_match_id, worldcup_matches.away_source_match_id),
                          source = EXCLUDED.source,
                          source_url = EXCLUDED.source_url,
                          raw_html_file = EXCLUDED.raw_html_file,
                          raw_content_hash = EXCLUDED.raw_content_hash,
                          parser_version = EXCLUDED.parser_version,
                          schema_version = EXCLUDED.schema_version,
                          fetched_at = EXCLUDED.fetched_at,
                          parse_warnings = EXCLUDED.parse_warnings,
                          metadata = EXCLUDED.metadata,
                          updated_at = EXCLUDED.updated_at
                        """,
                        self._worldcup_match_values(match),
                    )
            conn.commit()
        return {
            "inserted": len([match for match in matches if match["match_id"] not in existing]),
            "updated": len([match for match in matches if match["match_id"] in existing]),
        }

    def _worldcup_match_values(self, match: dict) -> tuple:
        return (
            match["match_id"],
            match["stage"],
            match.get("group_name"),
            match.get("kickoff_time"),
            match.get("kickoff_label"),
            match.get("home_team_id"),
            match.get("away_team_id"),
            match.get("winner_team_id"),
            match.get("home_team_raw"),
            match.get("away_team_raw"),
            match.get("winner_team_raw"),
            match.get("home_score"),
            match.get("away_score"),
            match.get("home_penalty"),
            match.get("away_penalty"),
            match.get("status", "scheduled"),
            match.get("next_match_id"),
            match.get("home_source_match_id"),
            match.get("away_source_match_id"),
            match.get("source", "bing_sports_html_fragment"),
            match.get("source_url", ""),
            match.get("raw_html_file", ""),
            match.get("raw_content_hash", ""),
            match.get("parser_version", "bing-html-v1"),
            match.get("schema_version", "worldcup-match-v1"),
            match.get("fetched_at"),
            json.dumps(match.get("parse_warnings", []), ensure_ascii=False),
            json.dumps(match.get("metadata", {}), ensure_ascii=False),
            datetime.now(timezone.utc),
        )

    def upsert_worldcup_standings(self, standings: list[dict]) -> None:
        if not self.enabled or not standings:
            return
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                for row in standings:
                    cur.execute(
                        """
                        INSERT INTO worldcup_standings
                          (id, group_name, team_id, team_name_raw, played, won, drawn, lost,
                           goals_for, goals_against, goal_difference, points, source, source_url,
                           raw_content_hash, parser_version, schema_version, fetched_at, payload, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                          payload = EXCLUDED.payload,
                          updated_at = EXCLUDED.updated_at
                        """,
                        (
                            row["id"],
                            row.get("group_name"),
                            row.get("team_id"),
                            row.get("team_name_raw", ""),
                            row.get("played"),
                            row.get("won"),
                            row.get("drawn"),
                            row.get("lost"),
                            row.get("goals_for"),
                            row.get("goals_against"),
                            row.get("goal_difference"),
                            row.get("points"),
                            row.get("source", "bing_sports_html_fragment"),
                            row.get("source_url", ""),
                            row.get("raw_content_hash", ""),
                            row.get("parser_version", "bing-html-v1"),
                            row.get("schema_version", "worldcup-standing-v1"),
                            row.get("fetched_at"),
                            json.dumps(row, ensure_ascii=False),
                            datetime.now(timezone.utc),
                        ),
                    )
            conn.commit()

    def load_worldcup_matches(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        stage: str | None = None,
    ) -> list[dict]:
        if not self.enabled:
            return []
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if date_from:
            clauses.append("kickoff_time >= %s")
            params.append(date_from)
        if date_to:
            clauses.append("kickoff_time <= %s")
            params.append(date_to)
        if status:
            clauses.append("status = %s")
            params.append(status.lower())
        if stage:
            clauses.append("stage = %s")
            params.append(stage)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        query = f"SELECT {self._worldcup_match_select_columns()} FROM worldcup_matches {where} ORDER BY kickoff_time NULLS LAST, match_id"
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [self._row_to_worldcup_match(row) for row in rows]

    def load_worldcup_match(self, match_id: str) -> dict | None:
        if not self.enabled:
            return None
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {self._worldcup_match_select_columns()} FROM worldcup_matches WHERE match_id = %s",
                    (match_id,),
                )
                row = cur.fetchone()
        return self._row_to_worldcup_match(row) if row else None

    def load_worldcup_bracket(self) -> list[dict]:
        return [
            match
            for match in self.load_worldcup_matches()
            if match.get("stage") != "group" or match.get("next_match_id")
        ]

    def load_worldcup_standings(self) -> list[dict]:
        if not self.enabled:
            return []
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return []
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM worldcup_standings ORDER BY group_name, points DESC NULLS LAST")
                rows = cur.fetchall()
        return [row[0] for row in rows]

    def load_worldcup_sync_status(self) -> dict | None:
        if not self.enabled:
            return None
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      MAX(finished_at) FILTER (WHERE status = 'success') AS last_success_at,
                      MAX(finished_at) FILTER (WHERE status = 'failed') AS last_failed_at
                    FROM worldcup_sync_runs
                    """
                )
                aggregate = cur.fetchone()
                cur.execute(
                    """
                    SELECT source, finished_at, status, fetched_count, parsed_count,
                           inserted_count, updated_count, error_message, raw_snapshot_dir
                    FROM worldcup_sync_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                latest = cur.fetchone()
        if not latest:
            return None
        return {
            "last_success_at": aggregate[0] if aggregate else None,
            "last_failed_at": aggregate[1] if aggregate else None,
            "last_status": latest[2],
            "source": latest[0],
            "fetched_count": latest[3],
            "parsed_count": latest[4],
            "inserted_count": latest[5],
            "updated_count": latest[6],
            "error_message": latest[7],
            "raw_snapshot_dir": latest[8],
        }

    def _worldcup_match_select_columns(self) -> str:
        return (
            "match_id, stage, group_name, kickoff_time, kickoff_label, home_team_id, away_team_id, "
            "winner_team_id, home_team_raw, away_team_raw, winner_team_raw, home_score, away_score, "
            "home_penalty, away_penalty, status, next_match_id, home_source_match_id, away_source_match_id, "
            "source, source_url, raw_html_file, raw_content_hash, parser_version, schema_version, fetched_at, "
            "parse_warnings, metadata"
        )

    def _row_to_worldcup_match(self, row: tuple) -> dict:
        keys = self._worldcup_match_select_columns().replace("\n", " ").split(", ")
        result = dict(zip(keys, row))
        result["parse_warnings"] = result.get("parse_warnings") or []
        result["metadata"] = result.get("metadata") or {}
        return result
