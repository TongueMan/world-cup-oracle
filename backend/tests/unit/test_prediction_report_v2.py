"""Human-readable prediction report regressions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from wcpa.prediction_report import build_prediction_report
from wcpa.schemas.artifact import (
    ChampionProbability,
    DataQualityReport,
    DataSourceStatus,
    FeatureModuleStatus,
    TournamentPrediction,
    TournamentState,
)


def test_report_uses_human_language_and_keeps_internal_ids_out_of_body():
    artifact = TournamentPrediction(
        artifact_id="wc2026-internal-id",
        artifact_version="4.0.0",
        publication_status="published",
        data_verified=True,
        simulation_count=10_000,
        generated_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        input_data_as_of=datetime(2026, 7, 14, tzinfo=timezone.utc),
        current_tournament_state=TournamentState(
            requested_anchor="post_qf",
            anchor_label="四强阶段",
            completed_match_ids=["QF-1"],
            remaining_match_ids=["SF-1", "SF-2", "Final"],
            alive_teams=["ARG", "FRA", "ENG", "ESP"],
            validation_status="ready",
        ),
        champion_probabilities=[
            ChampionProbability(team_id="ARG", probability=0.54),
            ChampionProbability(team_id="FRA", probability=0.46),
        ],
        feature_modules={
            "market": FeatureModuleStatus(
                enabled=True,
                status="available",
                coverage=1,
                message="赔率盘口已进入 100% 的单场概率。",
            )
        },
        data_sources=[
            DataSourceStatus(
                source_key="api_football_odds:SF-1",
                status="available",
                credibility="B",
                records=1,
                message="赔率可用。",
            )
        ],
        data_quality_report=DataQualityReport(status="ready", missing=[], message="ready"),
    )

    report = build_prediction_report(artifact)
    public_text = " ".join(
        [
            report.title,
            report.abstract,
            report.summary,
            report.data_disclosure,
            *[section.title + section.body + " ".join(section.bullets) for section in report.sections],
            *report.caveats,
        ]
    )

    assert report.title == "2026 世界杯四强阶段冠军预测报告"
    assert "阿根廷" in report.abstract
    assert "artifact" not in public_text.lower()
    assert "candidate" not in public_text.lower()
    assert "seed" not in public_text.lower()
    assert "透明试算" not in public_text
    assert "进决赛概率" not in public_text
    assert "路径风险" not in public_text
    assert report.references
    assert report.figures
    assert all(figure.data for figure in report.figures)


def test_champion_probability_contract_rejects_removed_advancement_fields():
    with pytest.raises(ValidationError):
        ChampionProbability.model_validate(
            {
                "team_id": "ARG",
                "probability": 0.5,
                "reach_final_probability": 0.8,
            }
        )

    payload = ChampionProbability(team_id="ARG", probability=0.5).model_dump()
    assert not any(key.startswith("reach_") for key in payload)
    assert "path_risk" not in payload


def test_report_generation_refuses_unverified_empty_prediction():
    artifact = TournamentPrediction(
        artifact_id="wc2026-unverified",
        artifact_version="4.0.0",
        publication_status="candidate",
        simulation_count=10_000,
        data_verified=False,
        current_tournament_state=TournamentState(
            requested_anchor="current",
            anchor_label="当前赛况",
            validation_status="ready",
        ),
        champion_probabilities=[],
        data_quality_report=DataQualityReport(status="data_unavailable", missing=["champion_probabilities_empty"]),
    )

    try:
        build_prediction_report(artifact)
    except ValueError as exc:
        assert "verified published prediction" in str(exc)
    else:
        raise AssertionError("unverified prediction must not produce a user-facing report")
