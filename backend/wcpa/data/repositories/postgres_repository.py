"""Optional PostgreSQL repository for durable artifacts and agent caches."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from wcpa.data.migrations import apply_migrations
from wcpa.shared.env import database_url


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


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

CREATE TABLE IF NOT EXISTS agent_search_runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL DEFAULT '',
  match_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  search_intent TEXT NOT NULL,
  provider TEXT NOT NULL,
  search_enabled BOOLEAN NOT NULL,
  query_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  latency_ms INTEGER
);

CREATE TABLE IF NOT EXISTS agent_search_results (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_search_runs(run_id),
  query TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  snippet TEXT NOT NULL DEFAULT '',
  rank INTEGER NOT NULL,
  published_at TEXT,
  fetched_at TIMESTAMPTZ NOT NULL,
  scrape_status TEXT NOT NULL,
  source_quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS agent_evidence_snapshots (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_search_runs(run_id),
  match_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  claim TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL,
  source_title TEXT NOT NULL DEFAULT '',
  source_excerpt TEXT NOT NULL DEFAULT '',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  extracted_at TIMESTAMPTZ NOT NULL
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

CREATE TABLE IF NOT EXISTS venues (
  venue_id TEXT PRIMARY KEY,
  venue_name TEXT NOT NULL,
  tournament_name TEXT,
  host_city TEXT,
  city TEXT,
  country TEXT NOT NULL,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  altitude_m DOUBLE PRECISION,
  capacity INTEGER,
  pitch_type TEXT,
  roof_type TEXT,
  source TEXT NOT NULL,
  source_url TEXT DEFAULT '',
  coordinate_source_url TEXT DEFAULT '',
  source_venue_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS match_venues (
  match_id TEXT PRIMARY KEY,
  venue_id TEXT NOT NULL REFERENCES venues(venue_id),
  source TEXT NOT NULL,
  source_url TEXT DEFAULT '',
  source_venue_id TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS match_environment_features (
  match_id TEXT PRIMARY KEY,
  venue_id TEXT REFERENCES venues(venue_id),
  kickoff_time TIMESTAMPTZ,
  temperature_c DOUBLE PRECISION,
  apparent_temperature_c DOUBLE PRECISION,
  humidity_pct DOUBLE PRECISION,
  precipitation_mm DOUBLE PRECISION,
  rain_probability DOUBLE PRECISION,
  wind_speed_kmh DOUBLE PRECISION,
  wind_gust_kmh DOUBLE PRECISION,
  altitude_m DOUBLE PRECISION,
  heat_stress_index DOUBLE PRECISION,
  rain_disruption_index DOUBLE PRECISION,
  wind_disruption_index DOUBLE PRECISION,
  altitude_stress_index DOUBLE PRECISION,
  environment_difficulty_index DOUBLE PRECISION,
  environment_summary TEXT,
  data_status TEXT NOT NULL DEFAULT 'data_unavailable',
  reason TEXT,
  source TEXT,
  source_url TEXT DEFAULT '',
  raw_weather JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetched_at TIMESTAMPTZ
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
        self._schema_ready = False

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.dsn)

    def init_schema(self) -> None:
        if not self.enabled:
            return
        if self._schema_ready:
            return
        try:
            conn = self._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
            apply_migrations(conn)
            conn.commit()
        self._schema_ready = True

    def list_schema_migrations(self) -> list[dict[str, Any]]:
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
                    SELECT migration_id, checksum, description, applied_at
                    FROM schema_migrations
                    ORDER BY migration_id
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "migration_id": row[0],
                "checksum": row[1],
                "description": row[2],
                "applied_at": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
            }
            for row in rows
        ]

    def load_table_counts(self, table_names: list[str]) -> dict[str, int]:
        if not self.enabled or not table_names:
            return {}
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return {}
        allowed = {name for name in table_names if name.replace("_", "").isalnum()}
        counts: dict[str, int] = {}
        with conn:
            with conn.cursor() as cur:
                for table_name in sorted(allowed):
                    cur.execute(
                        """
                        SELECT EXISTS (
                          SELECT 1
                          FROM information_schema.tables
                          WHERE table_schema = 'public' AND table_name = %s
                        )
                        """,
                        (table_name,),
                    )
                    if not cur.fetchone()[0]:
                        continue
                    cur.execute(f"SELECT count(*) FROM {table_name}")
                    counts[table_name] = int(cur.fetchone()[0])
        return counts

    def save_data_health_snapshot(
        self,
        snapshot_type: str,
        status: str,
        summary: dict[str, Any],
        payload: dict[str, Any],
    ) -> int | None:
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
                    INSERT INTO data_health_snapshots
                      (snapshot_type, generated_at, status, summary, payload)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        snapshot_type,
                        datetime.now(timezone.utc),
                        status,
                        _json_dumps(summary),
                        _json_dumps(payload),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return int(row[0]) if row else None

    def create_agent_workflow_run(
        self,
        run_id: str,
        workflow_name: str,
        session_id: str,
        match_id: str,
        intent: str,
        search_mode: str,
        message_hash: str,
        input_payload: dict[str, Any],
        started_at: datetime,
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
                    INSERT INTO agent_workflow_runs
                      (run_id, session_id, match_id, workflow_name, intent, search_mode,
                       message_hash, status, started_at, input_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'running', %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      input_payload = EXCLUDED.input_payload
                    """,
                    (
                        run_id,
                        session_id,
                        match_id,
                        workflow_name,
                        intent,
                        search_mode,
                        message_hash,
                        started_at,
                        _json_dumps(input_payload),
                    ),
                )
            conn.commit()

    def save_agent_workflow_step(
        self,
        run_id: str,
        step_name: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        latency_ms: int,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        error_message: str = "",
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
                    INSERT INTO agent_workflow_steps
                      (run_id, step_name, status, started_at, finished_at, latency_ms,
                       input_payload, output_payload, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        step_name,
                        status,
                        started_at,
                        finished_at,
                        latency_ms,
                        _json_dumps(input_payload),
                        _json_dumps(output_payload),
                        error_message,
                    ),
                )
            conn.commit()

    def finish_agent_workflow_run(
        self,
        run_id: str,
        status: str,
        finished_at: datetime,
        latency_ms: int,
        context_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        quality_payload: dict[str, Any] | None = None,
        error_message: str = "",
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
                    UPDATE agent_workflow_runs
                    SET status = %s,
                        finished_at = %s,
                        latency_ms = %s,
                        context_summary = %s,
                        output_summary = %s,
                        quality_payload = %s,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        finished_at,
                        latency_ms,
                        _json_dumps(context_summary or {}),
                        _json_dumps(output_summary or {}),
                        _json_dumps(quality_payload or {}),
                        error_message,
                        run_id,
                    ),
                )
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

    def create_agent_search_run(
        self,
        run_id: str,
        session_id: str,
        match_id: str,
        tool_name: str,
        search_intent: str,
        provider: str,
        search_enabled: bool,
        query_plan: dict,
        status: str,
        created_at: datetime,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_search_runs
                      (run_id, session_id, match_id, tool_name, search_intent, provider,
                       search_enabled, query_plan, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        session_id,
                        match_id,
                        tool_name,
                        search_intent,
                        provider,
                        search_enabled,
                        json.dumps(query_plan, ensure_ascii=False),
                        status,
                        created_at,
                    ),
                )
            conn.commit()

    def finish_agent_search_run(
        self,
        run_id: str,
        status: str,
        error_message: str,
        finished_at: datetime,
        latency_ms: int,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_search_runs
                    SET status = %s,
                        error_message = %s,
                        finished_at = %s,
                        latency_ms = %s
                    WHERE run_id = %s
                    """,
                    (status, error_message, finished_at, latency_ms, run_id),
                )
            conn.commit()

    def save_agent_search_result(
        self,
        run_id: str,
        query: str,
        title: str,
        url: str,
        domain: str,
        snippet: str,
        rank: int,
        published_at: str | None,
        fetched_at: datetime,
        scrape_status: str,
        source_quality_score: float,
        raw_payload: dict,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_search_results
                      (run_id, query, title, url, domain, snippet, rank, published_at,
                       fetched_at, scrape_status, source_quality_score, raw_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        query,
                        title,
                        url,
                        domain,
                        snippet,
                        rank,
                        published_at,
                        fetched_at,
                        scrape_status,
                        source_quality_score,
                        json.dumps(raw_payload, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def save_agent_evidence_snapshot(
        self,
        run_id: str,
        match_id: str,
        evidence_type: str,
        claim: str,
        source_url: str,
        source_title: str,
        source_excerpt: str,
        confidence: float,
        extracted_at: datetime,
    ) -> None:
        if not self.enabled:
            return
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_evidence_snapshots
                      (run_id, match_id, evidence_type, claim, source_url, source_title,
                       source_excerpt, confidence, extracted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        match_id,
                        evidence_type,
                        claim,
                        source_url,
                        source_title,
                        source_excerpt,
                        confidence,
                        extracted_at,
                    ),
                )
            conn.commit()

    def find_recent_success_agent_search_run(
        self,
        match_id: str,
        tool_name: str,
        search_intent: str,
        ttl_seconds: int,
    ) -> str | None:
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
                    SELECT run_id
                    FROM agent_search_runs
                    WHERE match_id = %s
                      AND tool_name = %s
                      AND search_intent = %s
                      AND status = 'success'
                      AND created_at >= now() - (%s || ' seconds')::interval
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (match_id, tool_name, search_intent, ttl_seconds),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def load_agent_search_sources(self, run_id: str) -> list[dict]:
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
                    SELECT title, url, domain, snippet, published_at, source_quality_score, raw_payload
                    FROM agent_search_results
                    WHERE run_id = %s
                    ORDER BY rank, id
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "title": row[0],
                "url": row[1],
                "domain": row[2],
                "snippet": row[3],
                "published_at": row[4],
                "source_quality_score": row[5],
                "raw_payload": row[6] or {},
            }
            for row in rows
        ]

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

    def upsert_venues(self, venues: list[dict]) -> dict[str, int]:
        if not self.enabled or not venues:
            return {"inserted": 0, "updated": 0}
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return {"inserted": 0, "updated": 0}
        existing: set[str] = set()
        with conn:
            with conn.cursor() as cur:
                ids = [venue["venue_id"] for venue in venues]
                cur.execute("SELECT venue_id FROM venues WHERE venue_id = ANY(%s)", (ids,))
                existing = {row[0] for row in cur.fetchall()}
                for venue in venues:
                    metadata = dict(venue.get("metadata", {}))
                    for key in ("coordinate_source_url",):
                        if venue.get(key):
                            metadata[key] = venue[key]
                    cur.execute(
                        """
                        INSERT INTO venues
                          (venue_id, venue_name, tournament_name, host_city, city, country,
                           latitude, longitude, altitude_m, capacity, pitch_type, roof_type,
                           source, source_url, coordinate_source_url, source_venue_ids,
                           aliases, metadata, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (venue_id) DO UPDATE SET
                          venue_name = EXCLUDED.venue_name,
                          tournament_name = EXCLUDED.tournament_name,
                          host_city = EXCLUDED.host_city,
                          city = EXCLUDED.city,
                          country = EXCLUDED.country,
                          latitude = EXCLUDED.latitude,
                          longitude = EXCLUDED.longitude,
                          altitude_m = COALESCE(EXCLUDED.altitude_m, venues.altitude_m),
                          capacity = EXCLUDED.capacity,
                          pitch_type = EXCLUDED.pitch_type,
                          roof_type = EXCLUDED.roof_type,
                          source = EXCLUDED.source,
                          source_url = EXCLUDED.source_url,
                          coordinate_source_url = EXCLUDED.coordinate_source_url,
                          source_venue_ids = EXCLUDED.source_venue_ids,
                          aliases = EXCLUDED.aliases,
                          metadata = EXCLUDED.metadata,
                          updated_at = EXCLUDED.updated_at
                        """,
                        (
                            venue["venue_id"],
                            venue["venue_name"],
                            venue.get("tournament_name"),
                            venue.get("host_city"),
                            venue.get("city"),
                            venue["country"],
                            venue.get("latitude"),
                            venue.get("longitude"),
                            venue.get("altitude_m"),
                            venue.get("capacity"),
                            venue.get("pitch_type"),
                            venue.get("roof_type"),
                            venue.get("source", ""),
                            venue.get("source_url", ""),
                            venue.get("coordinate_source_url", ""),
                            json.dumps(venue.get("source_venue_ids", []), ensure_ascii=False),
                            json.dumps(venue.get("aliases", []), ensure_ascii=False),
                            json.dumps(metadata, ensure_ascii=False),
                            datetime.now(timezone.utc),
                        ),
                    )
            conn.commit()
        return {
            "inserted": len([venue for venue in venues if venue["venue_id"] not in existing]),
            "updated": len([venue for venue in venues if venue["venue_id"] in existing]),
        }

    def load_venues(self) -> list[dict]:
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
                    SELECT venue_id, venue_name, tournament_name, host_city, city, country,
                           latitude, longitude, altitude_m, capacity, pitch_type, roof_type,
                           source, source_url, coordinate_source_url, source_venue_ids,
                           aliases, metadata, updated_at
                    FROM venues
                    ORDER BY host_city NULLS LAST, venue_name
                    """
                )
                rows = cur.fetchall()
        return [self._row_to_venue(row) for row in rows]

    def load_venue(self, venue_id: str) -> dict | None:
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
                    SELECT venue_id, venue_name, tournament_name, host_city, city, country,
                           latitude, longitude, altitude_m, capacity, pitch_type, roof_type,
                           source, source_url, coordinate_source_url, source_venue_ids,
                           aliases, metadata, updated_at
                    FROM venues
                    WHERE venue_id = %s
                    """,
                    (venue_id,),
                )
                row = cur.fetchone()
        return self._row_to_venue(row) if row else None

    def update_venue_elevation(
        self,
        venue_id: str,
        altitude_m: float,
        source: str,
        source_url: str,
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
                    UPDATE venues
                    SET altitude_m = %s,
                        metadata = metadata || %s::jsonb,
                        updated_at = %s
                    WHERE venue_id = %s
                    """,
                    (
                        altitude_m,
                        json.dumps(
                            {"elevation_source": source, "elevation_source_url": source_url},
                            ensure_ascii=False,
                        ),
                        datetime.now(timezone.utc),
                        venue_id,
                    ),
                )
            conn.commit()

    def upsert_match_venues(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"inserted": 0, "updated": 0}
        self.init_schema()
        try:
            conn = self._connect()
        except Exception:
            return {"inserted": 0, "updated": 0}
        existing: set[str] = set()
        with conn:
            with conn.cursor() as cur:
                ids = [row["match_id"] for row in rows]
                cur.execute("SELECT match_id FROM match_venues WHERE match_id = ANY(%s)", (ids,))
                existing = {row[0] for row in cur.fetchall()}
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO match_venues
                          (match_id, venue_id, source, source_url, source_venue_id, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (match_id) DO UPDATE SET
                          venue_id = EXCLUDED.venue_id,
                          source = EXCLUDED.source,
                          source_url = EXCLUDED.source_url,
                          source_venue_id = EXCLUDED.source_venue_id,
                          updated_at = EXCLUDED.updated_at
                        """,
                        (
                            row["match_id"],
                            row["venue_id"],
                            row.get("source", "worldcup_matches_metadata"),
                            row.get("source_url", ""),
                            row.get("source_venue_id"),
                            datetime.now(timezone.utc),
                        ),
                    )
            conn.commit()
        return {
            "inserted": len([row for row in rows if row["match_id"] not in existing]),
            "updated": len([row for row in rows if row["match_id"] in existing]),
        }

    def load_match_venue(self, match_id: str) -> dict | None:
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
                    SELECT match_id, venue_id, source, source_url, source_venue_id, updated_at
                    FROM match_venues
                    WHERE match_id = %s
                    """,
                    (match_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "match_id": row[0],
            "venue_id": row[1],
            "source": row[2],
            "source_url": row[3],
            "source_venue_id": row[4],
            "updated_at": row[5],
        }

    def load_matches_with_venues(self) -> list[dict]:
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
                    SELECT m.match_id, m.kickoff_time, m.source_url, m.metadata,
                           mv.venue_id, v.latitude, v.longitude, v.altitude_m
                    FROM worldcup_matches m
                    JOIN match_venues mv ON mv.match_id = m.match_id
                    JOIN venues v ON v.venue_id = mv.venue_id
                    ORDER BY m.kickoff_time NULLS LAST, m.match_id
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "match_id": row[0],
                "kickoff_time": row[1],
                "source_url": row[2],
                "metadata": row[3] or {},
                "venue_id": row[4],
                "latitude": row[5],
                "longitude": row[6],
                "altitude_m": row[7],
            }
            for row in rows
        ]

    def upsert_match_environment(self, payload: dict) -> None:
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
                    INSERT INTO match_environment_features
                      (match_id, venue_id, kickoff_time, temperature_c, apparent_temperature_c,
                       humidity_pct, precipitation_mm, rain_probability, wind_speed_kmh,
                       wind_gust_kmh, altitude_m, heat_stress_index, rain_disruption_index,
                       wind_disruption_index, altitude_stress_index, environment_difficulty_index,
                       environment_summary, data_status, reason, source, source_url, raw_weather, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (match_id) DO UPDATE SET
                      venue_id = EXCLUDED.venue_id,
                      kickoff_time = EXCLUDED.kickoff_time,
                      temperature_c = EXCLUDED.temperature_c,
                      apparent_temperature_c = EXCLUDED.apparent_temperature_c,
                      humidity_pct = EXCLUDED.humidity_pct,
                      precipitation_mm = EXCLUDED.precipitation_mm,
                      rain_probability = EXCLUDED.rain_probability,
                      wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                      wind_gust_kmh = EXCLUDED.wind_gust_kmh,
                      altitude_m = EXCLUDED.altitude_m,
                      heat_stress_index = EXCLUDED.heat_stress_index,
                      rain_disruption_index = EXCLUDED.rain_disruption_index,
                      wind_disruption_index = EXCLUDED.wind_disruption_index,
                      altitude_stress_index = EXCLUDED.altitude_stress_index,
                      environment_difficulty_index = EXCLUDED.environment_difficulty_index,
                      environment_summary = EXCLUDED.environment_summary,
                      data_status = EXCLUDED.data_status,
                      reason = EXCLUDED.reason,
                      source = EXCLUDED.source,
                      source_url = EXCLUDED.source_url,
                      raw_weather = EXCLUDED.raw_weather,
                      fetched_at = EXCLUDED.fetched_at
                    """,
                    (
                        payload["match_id"],
                        payload.get("venue_id"),
                        payload.get("kickoff_time"),
                        payload.get("temperature_c"),
                        payload.get("apparent_temperature_c"),
                        payload.get("humidity_pct"),
                        payload.get("precipitation_mm"),
                        payload.get("rain_probability"),
                        payload.get("wind_speed_kmh"),
                        payload.get("wind_gust_kmh"),
                        payload.get("altitude_m"),
                        payload.get("heat_stress_index"),
                        payload.get("rain_disruption_index"),
                        payload.get("wind_disruption_index"),
                        payload.get("altitude_stress_index"),
                        payload.get("environment_difficulty_index"),
                        payload.get("environment_summary"),
                        payload.get("data_status", "data_unavailable"),
                        payload.get("reason"),
                        payload.get("source"),
                        payload.get("source_url", ""),
                        json.dumps(payload.get("raw_weather", {}), ensure_ascii=False),
                        payload.get("fetched_at") or datetime.now(timezone.utc),
                    ),
                )
            conn.commit()

    def load_match_environment(self, match_id: str) -> dict | None:
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
                    SELECT e.match_id, e.venue_id, e.kickoff_time, e.temperature_c,
                           e.apparent_temperature_c, e.humidity_pct, e.precipitation_mm,
                           e.rain_probability, e.wind_speed_kmh, e.wind_gust_kmh, e.altitude_m,
                           e.heat_stress_index, e.rain_disruption_index, e.wind_disruption_index,
                           e.altitude_stress_index, e.environment_difficulty_index,
                           e.environment_summary, e.data_status, e.reason, e.source,
                           e.source_url, e.fetched_at,
                           v.venue_id, v.venue_name, v.tournament_name, v.host_city, v.city,
                           v.country, v.latitude, v.longitude, v.altitude_m, v.capacity,
                           v.pitch_type, v.roof_type, v.source, v.source_url,
                           v.coordinate_source_url, v.source_venue_ids, v.aliases, v.metadata,
                           v.updated_at
                    FROM match_environment_features e
                    LEFT JOIN venues v ON v.venue_id = e.venue_id
                    WHERE e.match_id = %s
                    """,
                    (match_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        venue = None
        if row[22]:
            venue = self._row_to_venue(row[22:])
        return {
            "match_id": row[0],
            "venue_id": row[1],
            "kickoff_time": row[2],
            "temperature_c": row[3],
            "apparent_temperature_c": row[4],
            "humidity_pct": row[5],
            "precipitation_mm": row[6],
            "rain_probability": row[7],
            "wind_speed_kmh": row[8],
            "wind_gust_kmh": row[9],
            "altitude_m": row[10],
            "heat_stress_index": row[11],
            "rain_disruption_index": row[12],
            "wind_disruption_index": row[13],
            "altitude_stress_index": row[14],
            "environment_difficulty_index": row[15],
            "environment_summary": row[16],
            "data_status": row[17],
            "reason": row[18],
            "source": row[19],
            "source_url": row[20],
            "fetched_at": row[21],
            "venue": venue,
        }

    def upsert_data_historical_matches(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"loaded": 0}
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO data_historical_matches
                          (competition, edition_year, match_date, stage, home_team, away_team,
                           home_score, away_score, winner_team, source, source_url, source_path,
                           confidence, data_status, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (competition, edition_year, stage, home_team, away_team, match_date)
                        DO UPDATE SET
                          home_score = EXCLUDED.home_score,
                          away_score = EXCLUDED.away_score,
                          winner_team = EXCLUDED.winner_team,
                          source = EXCLUDED.source,
                          source_url = EXCLUDED.source_url,
                          source_path = EXCLUDED.source_path,
                          confidence = EXCLUDED.confidence,
                          data_status = EXCLUDED.data_status,
                          payload = EXCLUDED.payload
                        """,
                        (
                            row.get("competition", "FIFA World Cup"),
                            row.get("edition_year"),
                            row.get("match_date"),
                            row.get("stage", ""),
                            row.get("home_team", ""),
                            row.get("away_team", ""),
                            row.get("home_score"),
                            row.get("away_score"),
                            row.get("winner_team", ""),
                            row.get("source", ""),
                            row.get("source_url", ""),
                            row.get("source_path", ""),
                            row.get("confidence", 0.8),
                            row.get("data_status", "published"),
                            _json_dumps(row.get("payload", row)),
                        ),
                    )
            conn.commit()
        return {"loaded": len(rows)}

    def upsert_data_team_squads(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"loaded": 0}
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO data_team_squads
                          (competition, edition_year, team_name, player_name, shirt_number,
                           position, source, source_url, source_path, confidence, data_status, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (competition, edition_year, team_name, player_name)
                        DO UPDATE SET
                          shirt_number = EXCLUDED.shirt_number,
                          position = EXCLUDED.position,
                          source = EXCLUDED.source,
                          source_url = EXCLUDED.source_url,
                          source_path = EXCLUDED.source_path,
                          confidence = EXCLUDED.confidence,
                          data_status = EXCLUDED.data_status,
                          payload = EXCLUDED.payload
                        """,
                        (
                            row.get("competition", "FIFA World Cup"),
                            row.get("edition_year"),
                            row.get("team_name", ""),
                            row.get("player_name", ""),
                            row.get("shirt_number", ""),
                            row.get("position", ""),
                            row.get("source", ""),
                            row.get("source_url", ""),
                            row.get("source_path", ""),
                            row.get("confidence", 0.7),
                            row.get("data_status", "staged"),
                            _json_dumps(row.get("payload", row)),
                        ),
                    )
            conn.commit()
        return {"loaded": len(rows)}

    def upsert_data_odds_snapshots(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"loaded": 0}
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO data_odds_snapshots
                          (match_id, market, bookmaker, home_price, draw_price, away_price,
                           implied_home_prob, implied_draw_prob, implied_away_prob, source,
                           source_url, observed_at, confidence, data_status, payload, source_match_key)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source, source_match_key, bookmaker, market)
                        DO UPDATE SET
                          home_price = EXCLUDED.home_price,
                          draw_price = EXCLUDED.draw_price,
                          away_price = EXCLUDED.away_price,
                          implied_home_prob = EXCLUDED.implied_home_prob,
                          implied_draw_prob = EXCLUDED.implied_draw_prob,
                          implied_away_prob = EXCLUDED.implied_away_prob,
                          source_url = EXCLUDED.source_url,
                          observed_at = EXCLUDED.observed_at,
                          confidence = EXCLUDED.confidence,
                          data_status = EXCLUDED.data_status,
                          payload = EXCLUDED.payload
                        """,
                        (
                            row.get("match_id", ""),
                            row.get("market", "1x2"),
                            row.get("bookmaker", ""),
                            row.get("home_price"),
                            row.get("draw_price"),
                            row.get("away_price"),
                            row.get("implied_home_prob"),
                            row.get("implied_draw_prob"),
                            row.get("implied_away_prob"),
                            row.get("source", ""),
                            row.get("source_url", ""),
                            row.get("observed_at") or datetime.now(timezone.utc),
                            row.get("confidence", 0.6),
                            row.get("data_status", "staged"),
                            _json_dumps(row.get("payload", row)),
                            row.get("source_match_key", ""),
                        ),
                    )
            conn.commit()
        return {"loaded": len(rows)}

    def upsert_data_team_form_snapshots(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"loaded": 0}
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO data_team_form_snapshots
                          (team_id, team_name, snapshot_date, source, source_url,
                           matches_considered, form_score, attack_score, defense_score,
                           confidence, data_status, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (team_id, team_name, snapshot_date, source)
                        DO UPDATE SET
                          source_url = EXCLUDED.source_url,
                          matches_considered = EXCLUDED.matches_considered,
                          form_score = EXCLUDED.form_score,
                          attack_score = EXCLUDED.attack_score,
                          defense_score = EXCLUDED.defense_score,
                          confidence = EXCLUDED.confidence,
                          data_status = EXCLUDED.data_status,
                          payload = EXCLUDED.payload
                        """,
                        (
                            row.get("team_id", ""),
                            row.get("team_name", ""),
                            row.get("snapshot_date"),
                            row.get("source", ""),
                            row.get("source_url", ""),
                            row.get("matches_considered"),
                            row.get("form_score"),
                            row.get("attack_score"),
                            row.get("defense_score"),
                            row.get("confidence", 0.7),
                            row.get("data_status", "published"),
                            _json_dumps(row.get("payload", row)),
                        ),
                    )
            conn.commit()
        return {"loaded": len(rows)}

    def upsert_staging_open_source_records(self, rows: list[dict]) -> dict[str, int]:
        if not self.enabled or not rows:
            return {"loaded": 0}
        self.init_schema()
        conn = self._connect()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO staging_open_source_records
                          (dataset_key, source_path, record_key, record_type, quality_status, payload)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (dataset_key, source_path, record_key)
                        DO UPDATE SET
                          record_type = EXCLUDED.record_type,
                          quality_status = EXCLUDED.quality_status,
                          payload = EXCLUDED.payload,
                          imported_at = now()
                        """,
                        (
                            row.get("dataset_key", ""),
                            row.get("source_path", ""),
                            row.get("record_key", ""),
                            row.get("record_type", ""),
                            row.get("quality_status", "unreviewed"),
                            _json_dumps(row.get("payload", row)),
                        ),
                    )
            conn.commit()
        return {"loaded": len(rows)}

    def _row_to_venue(self, row: tuple) -> dict:
        return {
            "venue_id": row[0],
            "venue_name": row[1],
            "tournament_name": row[2],
            "host_city": row[3],
            "city": row[4],
            "country": row[5],
            "latitude": row[6],
            "longitude": row[7],
            "altitude_m": row[8],
            "capacity": row[9],
            "pitch_type": row[10],
            "roof_type": row[11],
            "source": row[12],
            "source_url": row[13],
            "coordinate_source_url": row[14],
            "source_venue_ids": row[15] or [],
            "aliases": row[16] or [],
            "metadata": row[17] or {},
            "updated_at": row[18],
        }

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
