"""Idempotent PostgreSQL migrations for durable product data."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


BOOTSTRAP_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_id TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        migration_id="2026070701_agent_data_governance",
        description="Agent workflow tracing, data health snapshots, source staging tables, and read indexes.",
        sql="""
CREATE TABLE IF NOT EXISTS data_health_snapshots (
  id BIGSERIAL PRIMARY KEY,
  snapshot_type TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'ok',
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS agent_workflow_runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL DEFAULT '',
  match_id TEXT NOT NULL DEFAULT '',
  workflow_name TEXT NOT NULL DEFAULT 'agent_research',
  intent TEXT NOT NULL DEFAULT '',
  search_mode TEXT NOT NULL DEFAULT '',
  message_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'running',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  latency_ms INTEGER,
  input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  context_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  quality_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_workflow_steps (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_workflow_runs(run_id) ON DELETE CASCADE,
  step_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  latency_ms INTEGER,
  input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS eval_regression_runs (
  run_id TEXT PRIMARY KEY,
  suite_name TEXT NOT NULL,
  config_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'running',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  summary JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS eval_regression_results (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES eval_regression_runs(run_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  case_type TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  score DOUBLE PRECISION,
  risk_level TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS data_source_inventories (
  id BIGSERIAL PRIMARY KEY,
  source_key TEXT NOT NULL,
  source_path TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT '',
  record_count INTEGER,
  file_count INTEGER,
  coverage_status TEXT NOT NULL DEFAULT 'unknown',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  scanned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS data_historical_matches (
  id BIGSERIAL PRIMARY KEY,
  competition TEXT NOT NULL DEFAULT 'FIFA World Cup',
  edition_year INTEGER,
  match_date DATE,
  stage TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  home_score INTEGER,
  away_score INTEGER,
  winner_team TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
  data_status TEXT NOT NULL DEFAULT 'staged',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (competition, edition_year, stage, home_team, away_team, match_date)
);

CREATE TABLE IF NOT EXISTS data_team_squads (
  id BIGSERIAL PRIMARY KEY,
  competition TEXT NOT NULL DEFAULT 'FIFA World Cup',
  edition_year INTEGER,
  team_name TEXT NOT NULL,
  player_name TEXT NOT NULL,
  shirt_number TEXT NOT NULL DEFAULT '',
  position TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
  data_status TEXT NOT NULL DEFAULT 'staged',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (competition, edition_year, team_name, player_name)
);

CREATE TABLE IF NOT EXISTS data_injury_suspension_reports (
  id BIGSERIAL PRIMARY KEY,
  team_id TEXT NOT NULL DEFAULT '',
  team_name TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  report_type TEXT NOT NULL DEFAULT '',
  availability_status TEXT NOT NULL DEFAULT 'unknown',
  effective_match_id TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  data_status TEXT NOT NULL DEFAULT 'staged',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS data_odds_snapshots (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL DEFAULT '',
  market TEXT NOT NULL DEFAULT '',
  bookmaker TEXT NOT NULL DEFAULT '',
  home_price DOUBLE PRECISION,
  draw_price DOUBLE PRECISION,
  away_price DOUBLE PRECISION,
  implied_home_prob DOUBLE PRECISION,
  implied_draw_prob DOUBLE PRECISION,
  implied_away_prob DOUBLE PRECISION,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.6,
  data_status TEXT NOT NULL DEFAULT 'staged',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS data_team_form_snapshots (
  id BIGSERIAL PRIMARY KEY,
  team_id TEXT NOT NULL DEFAULT '',
  team_name TEXT NOT NULL DEFAULT '',
  snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  matches_considered INTEGER,
  form_score DOUBLE PRECISION,
  attack_score DOUBLE PRECISION,
  defense_score DOUBLE PRECISION,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  data_status TEXT NOT NULL DEFAULT 'staged',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (team_id, team_name, snapshot_date, source)
);

CREATE TABLE IF NOT EXISTS staging_open_source_records (
  id BIGSERIAL PRIMARY KEY,
  dataset_key TEXT NOT NULL,
  source_path TEXT NOT NULL,
  record_key TEXT NOT NULL,
  record_type TEXT NOT NULL DEFAULT '',
  quality_status TEXT NOT NULL DEFAULT 'unreviewed',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (dataset_key, source_path, record_key)
);

CREATE INDEX IF NOT EXISTS idx_worldcup_matches_stage_status_kickoff
  ON worldcup_matches (stage, status, kickoff_time);
CREATE INDEX IF NOT EXISTS idx_worldcup_matches_home_team ON worldcup_matches (home_team_id);
CREATE INDEX IF NOT EXISTS idx_worldcup_matches_away_team ON worldcup_matches (away_team_id);
CREATE INDEX IF NOT EXISTS idx_worldcup_matches_winner_team ON worldcup_matches (winner_team_id);
CREATE INDEX IF NOT EXISTS idx_worldcup_matches_metadata_gin ON worldcup_matches USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_worldcup_standings_group_points ON worldcup_standings (group_name, points DESC);
CREATE INDEX IF NOT EXISTS idx_bing_knowledge_records_type_fetched ON bing_knowledge_records (record_type, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_bing_knowledge_records_payload_gin ON bing_knowledge_records USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_source_snapshots_key_cred_fetched ON source_snapshots (source_key, credibility, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_snapshots_payload_gin ON source_snapshots USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_agent_runs_match_agent_created ON agent_runs (match_id, agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_search_runs_match_intent_status_created
  ON agent_search_runs (match_id, search_intent, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_search_results_run_rank ON agent_search_results (run_id, rank, id);
CREATE INDEX IF NOT EXISTS idx_agent_search_results_domain_fetched ON agent_search_results (domain, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_search_results_raw_payload_gin ON agent_search_results USING GIN (raw_payload);
CREATE INDEX IF NOT EXISTS idx_agent_evidence_match_type_conf
  ON agent_evidence_snapshots (match_id, evidence_type, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_venues_aliases_gin ON venues USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_match_venues_venue ON match_venues (venue_id);
CREATE INDEX IF NOT EXISTS idx_match_environment_status_kickoff
  ON match_environment_features (data_status, kickoff_time);
CREATE INDEX IF NOT EXISTS idx_match_environment_raw_weather_gin
  ON match_environment_features USING GIN (raw_weather);
CREATE INDEX IF NOT EXISTS idx_data_health_snapshots_type_generated
  ON data_health_snapshots (snapshot_type, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_workflow_runs_match_intent_created
  ON agent_workflow_runs (match_id, intent, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_workflow_runs_status_created
  ON agent_workflow_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_workflow_steps_run_step
  ON agent_workflow_steps (run_id, step_name, started_at);
CREATE INDEX IF NOT EXISTS idx_eval_regression_results_run_case
  ON eval_regression_results (run_id, case_id);
CREATE INDEX IF NOT EXISTS idx_data_source_inventories_key_scanned
  ON data_source_inventories (source_key, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_historical_matches_year_team
  ON data_historical_matches (edition_year, home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_data_historical_matches_payload_gin
  ON data_historical_matches USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_data_team_squads_team_year
  ON data_team_squads (team_name, edition_year);
CREATE INDEX IF NOT EXISTS idx_data_injury_reports_team_player
  ON data_injury_suspension_reports (team_id, player_name, availability_status, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_odds_snapshots_match_market_observed
  ON data_odds_snapshots (match_id, market, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_team_form_snapshots_team_date
  ON data_team_form_snapshots (team_id, team_name, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_staging_open_source_dataset_type
  ON staging_open_source_records (dataset_key, record_type, quality_status);
CREATE INDEX IF NOT EXISTS idx_staging_open_source_payload_gin
  ON staging_open_source_records USING GIN (payload);
""",
    ),
    Migration(
        migration_id="2026070702_odds_source_key",
        description="Add source_match_key to odds snapshots for idempotent historical odds imports.",
        sql="""
ALTER TABLE data_odds_snapshots
  ADD COLUMN IF NOT EXISTS source_match_key TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_data_odds_snapshots_source_match_bookmaker_market
  ON data_odds_snapshots (source, source_match_key, bookmaker, market);

CREATE INDEX IF NOT EXISTS idx_data_odds_snapshots_source_match_key
  ON data_odds_snapshots (source_match_key);
""",
    ),
    Migration(
        migration_id="2026070703_odds_source_market_observed_index",
        description="Optimize latest historical odds queries by source and market.",
        sql="""
CREATE INDEX IF NOT EXISTS idx_data_odds_snapshots_source_market_observed
  ON data_odds_snapshots (source, market, observed_at DESC);
""",
    ),
    Migration(
        migration_id="2026070704_agent_workflow_started_index",
        description="Optimize recent Agent workflow trace queries by start time.",
        sql="""
CREATE INDEX IF NOT EXISTS idx_agent_workflow_runs_started_desc
  ON agent_workflow_runs (started_at DESC);
""",
    ),
)


def apply_migrations(conn) -> list[str]:
    """Apply pending migrations and return the applied migration ids."""

    applied: list[str] = []
    with conn.cursor() as cur:
        cur.execute(BOOTSTRAP_SCHEMA_MIGRATIONS_SQL)
        for migration in MIGRATIONS:
            cur.execute(
                "SELECT checksum FROM schema_migrations WHERE migration_id = %s",
                (migration.migration_id,),
            )
            row = cur.fetchone()
            if row:
                if row[0] != migration.checksum:
                    raise RuntimeError(f"Migration checksum mismatch: {migration.migration_id}")
                continue
            cur.execute(migration.sql)
            cur.execute(
                """
                INSERT INTO schema_migrations (migration_id, checksum, description)
                VALUES (%s, %s, %s)
                """,
                (migration.migration_id, migration.checksum, migration.description),
            )
            applied.append(migration.migration_id)
    return applied
