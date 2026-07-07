from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from wcpa.agents.workflow_harness import AgentWorkflowHarness, build_evidence_packet
from wcpa.data.health import collect_data_health_snapshot
from wcpa.data.migrations import MIGRATIONS
from wcpa.data.repositories.postgres_repository import _json_dumps
from wcpa.schemas.agent_chat import AgentResearchRequest


class FakeRepository:
    enabled = True

    def __init__(self):
        self.runs = []
        self.steps = []
        self.finished = []

    def create_agent_workflow_run(self, **kwargs):
        self.runs.append(kwargs)

    def save_agent_workflow_step(self, **kwargs):
        self.steps.append(kwargs)

    def finish_agent_workflow_run(self, **kwargs):
        self.finished.append(kwargs)

    def load_table_counts(self, table_names):
        return {name: 0 for name in table_names}


def test_governance_migration_declares_trace_tables_and_indexes():
    sql = "\n".join(migration.sql for migration in MIGRATIONS)
    ids = [migration.migration_id for migration in MIGRATIONS]

    assert len(ids) == len(set(ids))
    assert "CREATE TABLE IF NOT EXISTS agent_workflow_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS data_health_snapshots" in sql
    assert "CREATE TABLE IF NOT EXISTS data_historical_matches" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_worldcup_matches_stage_status_kickoff" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_agent_search_runs_match_intent_status_created" in sql


def test_data_health_snapshot_reports_local_data_missing_from_database(tmp_path: Path):
    _write_json(tmp_path / "data/knowledge/worldcup/history.json", {"matches": [{"id": 1}]})
    _write_jsonl(tmp_path / "data/knowledge/bing/news.jsonl", [{"title": "injury news"}])
    _write_json(tmp_path / "data/seeds/venues_seed.json", [{"venue_id": "v1"}])
    (tmp_path / "开源数据/世界杯/worldcup-master/2026--usa").mkdir(parents=True)
    (tmp_path / "开源数据/世界杯/worldcup-master/2026--usa/squad.txt").write_text(
        "Team squad", encoding="utf-8"
    )

    snapshot = collect_data_health_snapshot(FakeRepository(), tmp_path)
    domains = {item["domain"] for item in snapshot["payload"]["missing_domains"]}

    assert snapshot["status"] == "attention_required"
    assert "historical_worldcup_matches" in domains
    assert "worldcup_squads" in domains
    assert "injury_suspension_news" in domains
    assert "match_environment_features" in domains


def test_workflow_harness_masks_api_key_and_records_steps():
    request = AgentResearchRequest.model_validate(
        {
            "message": "美国 vs 比利时什么时候踢？",
            "context": {"currentMatchId": "m1", "data": {"sessionId": "s1"}},
            "history": [],
            "llmConfig": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "apiKey": "secret-value",
                "searchEnabled": False,
            },
            "searchMode": "local_only",
            "toolIntent": "general",
        }
    )
    repo = FakeRepository()
    harness = AgentWorkflowHarness.from_research_request(request, repo)

    with harness.step("build_context") as step:
        step["ok"] = True
    harness.finish("ok", output_summary={"answer_chars": 12})

    assert repo.runs[0]["run_id"] == harness.run_id
    assert repo.runs[0]["input_payload"]["llmConfig"]["apiKey"] == "***"
    assert repo.steps[0]["step_name"] == "build_context"
    assert repo.finished[0]["status"] == "ok"


def test_evidence_packet_collects_supported_claims():
    packet = build_evidence_packet(
        [
            {
                "citationId": 1,
                "url": "https://example.com",
                "supportedClaims": [
                    {"type": "venue", "claim": "场馆是 Lumen Field", "evidence": "Lumen Field"}
                ],
            }
        ],
        unknowns=["pitch_type"],
    )

    assert packet.to_summary()["source_count"] == 1
    assert packet.to_summary()["claim_count"] == 1
    assert packet.claims[0].citation_id == 1
    assert packet.unsupported_unknowns == ["pitch_type"]


def test_repository_json_dumps_handles_datetimes():
    dumped = _json_dumps({"kickoff_time": datetime(2026, 7, 7, tzinfo=timezone.utc)})

    assert "2026-07-07" in dumped


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
