"""Strict real-data loading and readiness validation.

Production prediction must use verified external or manually curated real data.
Fixture/demo data is intentionally rejected in strict mode.
"""

from __future__ import annotations

import json
from pathlib import Path

from wcpa.schemas.artifact import DataQualityReport, DataSourceStatus
from wcpa.schemas.match import Match
from wcpa.schemas.narrative import NarrativeProfile
from wcpa.schemas.team import Team
from wcpa.shared.paths import NORMALIZED_DIR


REAL_TEAMS_FILE = NORMALIZED_DIR / "teams.real.json"
REAL_MATCHES_FILE = NORMALIZED_DIR / "matches.real.json"
REAL_NARRATIVES_FILE = NORMALIZED_DIR / "narratives.real.json"

FORBIDDEN_SOURCE_MARKERS = {"fixture", "fixtures", "fixture_expansion", "fallback", "demo", "sample"}


class DataUnavailableError(RuntimeError):
    """Raised when strict production data is incomplete or unverified."""

    def __init__(self, report: DataQualityReport):
        self.report = report
        super().__init__(report.message)


def load_strict_real_dataset(
    source_statuses: list[DataSourceStatus],
) -> tuple[list[Team], list[Match], list[NarrativeProfile], DataQualityReport]:
    missing: list[str] = []
    invalid_records: list[dict] = []

    if not REAL_TEAMS_FILE.exists():
        missing.append(str(REAL_TEAMS_FILE.relative_to(NORMALIZED_DIR.parent.parent)))
    if not REAL_MATCHES_FILE.exists():
        missing.append(str(REAL_MATCHES_FILE.relative_to(NORMALIZED_DIR.parent.parent)))

    if not any(source.status == "ok" for source in source_statuses):
        missing.append("at_least_one_verified_external_source_status_ok")

    if missing:
        report = DataQualityReport(
            status="data_unavailable",
            strict=True,
            missing=missing,
            source_statuses=source_statuses,
            message="Agent 联网搜索尚未形成完整结构化世界杯数据，正式预测已停止；不会使用 fixture 或模拟数据兜底。",
        )
        raise DataUnavailableError(report)

    raw_teams = _read_json_list(REAL_TEAMS_FILE)
    raw_matches = _read_json_list(REAL_MATCHES_FILE)

    required_team_fields = {
        "team_id",
        "name",
        "confederation",
        "fifa_rank",
        "elo_rating",
        "recent_form_score",
        "attack_score",
        "defense_score",
        "squad_health_score",
        "source_key",
        "source_url",
        "verified",
    }
    required_match_fields = {
        "match_id",
        "stage",
        "home_team_id",
        "away_team_id",
        "source",
    }

    for entry in raw_teams:
        missing_fields = sorted(required_team_fields - set(entry))
        if missing_fields:
            invalid_records.append(
                {
                    "dataset": "teams",
                    "id": entry.get("team_id") or entry.get("name"),
                    "reason": "missing_required_model_fields",
                    "fields": missing_fields,
                }
            )
    for entry in raw_matches:
        missing_fields = sorted(required_match_fields - set(entry))
        if missing_fields:
            invalid_records.append(
                {
                    "dataset": "matches",
                    "id": entry.get("match_id"),
                    "reason": "missing_required_fields",
                    "fields": missing_fields,
                }
            )

    if invalid_records:
        report = DataQualityReport(
            status="invalid",
            strict=True,
            invalid_records=invalid_records[:50],
            source_statuses=source_statuses,
            message="Agent 搜索已有证据，但球队模型字段尚未结构化完整，正式预测已停止。",
        )
        raise DataUnavailableError(report)

    teams = [Team(**entry) for entry in raw_teams]
    matches = [Match(**entry) for entry in raw_matches]
    narratives = (
        [NarrativeProfile(**entry) for entry in _read_json_list(REAL_NARRATIVES_FILE)]
        if REAL_NARRATIVES_FILE.exists()
        else []
    )

    if len(teams) < 48:
        invalid_records.append({"dataset": "teams", "reason": "expected_48_teams", "count": len(teams)})
    groups = {match.group for match in matches if match.stage == "group" and match.group}
    if len(groups) < 12:
        invalid_records.append({"dataset": "matches", "reason": "expected_12_groups", "count": len(groups)})
    if len([match for match in matches if match.stage == "group"]) < 72:
        invalid_records.append({"dataset": "matches", "reason": "expected_72_group_matches"})

    for team in teams:
        if not team.verified:
            invalid_records.append({"dataset": "teams", "id": team.team_id, "reason": "not_verified"})
        if _is_forbidden_source(team.source_key) or team.data_quality == "D":
            invalid_records.append({"dataset": "teams", "id": team.team_id, "reason": "forbidden_or_low_quality_source"})

    for match in matches:
        if _is_forbidden_source(match.source):
            invalid_records.append({"dataset": "matches", "id": match.match_id, "reason": "forbidden_source"})

    if invalid_records:
        report = DataQualityReport(
            status="invalid",
            strict=True,
            invalid_records=invalid_records[:50],
            source_statuses=source_statuses,
            message="Agent 证据结构化校验失败，正式预测已停止。",
        )
        raise DataUnavailableError(report)

    report = DataQualityReport(
        status="ready",
        strict=True,
        source_statuses=source_statuses,
        message="Agent 证据与真实数据已通过严格校验。",
    )
    return teams, matches, narratives, report


def build_unavailable_report(source_statuses: list[DataSourceStatus]) -> DataQualityReport:
    return DataQualityReport(
        status="data_unavailable",
        strict=True,
        missing=["teams.real.json", "matches.real.json"],
        source_statuses=source_statuses,
        message="当前没有可用于正式预测的 Agent 结构化世界杯数据。",
    )


def _read_json_list(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list: {path}")
    return data


def _is_forbidden_source(source: str) -> bool:
    normalized = (source or "").strip().lower()
    return not normalized or normalized in FORBIDDEN_SOURCE_MARKERS
