"""Generate a grounded, user-facing champion forecast report."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from wcpa.schemas.artifact import (
    ChampionProbability,
    PredictionAgentReport,
    PredictionReportFigure,
    PredictionReportReference,
    PredictionReportSection,
    TournamentPrediction,
)
from wcpa.shared.paths import PREDICTIONS_DIR


REPORT_DIR = PREDICTIONS_DIR / "reports"

TEAM_NAMES = {
    "ARG": "阿根廷", "BRA": "巴西", "ENG": "英格兰", "ESP": "西班牙",
    "FRA": "法国", "GER": "德国", "NED": "荷兰", "POR": "葡萄牙",
    "MAR": "摩洛哥", "USA": "美国", "MEX": "墨西哥", "JPN": "日本",
}

COMPONENT_NAMES = {
    "strength": "球队实力",
    "goals": "进球模型",
    "market": "市场赔率",
    "web_semantic": "联网语义",
    "neutral_prior": "中性先验",
}


def build_prediction_report(prediction: TournamentPrediction) -> PredictionAgentReport:
    """Build a report whose claims and figures are fully backed by the saved prediction."""

    _require_reportable_prediction(prediction)
    state = prediction.current_tournament_state
    anchor = state.requested_anchor if state else "current"
    rows = sorted(
        (row for row in prediction.champion_probabilities if row.is_alive and row.probability > 0),
        key=lambda row: (-row.probability, row.team_id),
    )
    leader = rows[0]
    rivals = rows[1:4]
    summary = _summary(prediction, leader, rivals)
    references = _references(prediction)
    evidence_citations = [item.reference_id for item in references if item.url][:8]
    figures = _figures(prediction, rows, leader)
    sections = [
        PredictionReportSection(
            title="预测结论",
            body=summary,
            bullets=_conclusion_bullets(prediction, leader),
            kind="summary",
            figure_refs=["champion_probability_chart"],
        ),
        PredictionReportSection(
            title=f"为什么是{_team_name(leader.team_id)}领先",
            body=_leader_reason(prediction, leader),
            bullets=_leader_reason_bullets(prediction, leader),
            kind="reasoning",
            citations=["model-1"],
            figure_refs=["champion_scenario_chart", "team_feature_chart"],
        ),
        PredictionReportSection(
            title="决定冠军归属的比赛",
            body=_match_summary(prediction),
            bullets=_match_bullets(prediction),
            kind="matches",
            citations=["model-1"],
            figure_refs=["match_model_comparison"],
        ),
        PredictionReportSection(
            title="新闻、阵容、赔率与比赛环境",
            body=_evidence_body(prediction),
            bullets=_evidence_bullets(prediction),
            kind="evidence",
            citations=evidence_citations,
            figure_refs=["evidence_cards"],
        ),
        PredictionReportSection(
            title="模型是怎样得到这个数字的",
            body=(
                "这套方法可以概括为“赛况锁定、对阵级多源融合、条件冠军模拟”。"
                "系统先冻结当前已经发生的比赛，再为每支存活球队保存排名、Elo、本届赛事状态、"
                "攻防表现、世界杯经验和阵容可用度。每场对阵由球队实力、进球分布和可验证的市场"
                "信息共同给出概率，随后按世界杯加时和点球规则重复推演剩余赛程。"
            ),
            bullets=[
                "第一步：锁定已完成赛果，未确定的对阵只保留为赛程分支。",
                "第二步：对每个真实对阵计算常规时间、加时和点球后的晋级概率。",
                f"第三步：重复模拟 {prediction.simulation_count:,} 次，以最终夺冠次数形成冠军概率。",
                "实时新闻只有在事实、对象和影响方向都足够明确时才会改变概率；否则只作为比赛背景展示。",
            ],
            kind="method",
            citations=["model-1"],
            figure_refs=["team_feature_chart", "match_model_comparison"],
        ),
        PredictionReportSection(
            title="什么情况会改变当前结论",
            body=_change_conditions(prediction, leader),
            bullets=_uncertainty_bullets(prediction, leader),
            kind="uncertainty",
        ),
    ]
    return PredictionAgentReport(
        report_id=_report_id(prediction, anchor),
        artifact_id=prediction.artifact_id,
        anchor=anchor,
        generated_at=datetime.now(timezone.utc),
        status="generated",
        headline=f"{_team_name(leader.team_id)}当前夺冠概率最高：{leader.probability:.1%}",
        summary=summary,
        title=f"2026 世界杯{state.anchor_label if state else '当前阶段'}冠军预测报告",
        abstract=summary,
        methodology_note="报告只解释本次预测中已经保存的赛程、球队特征、比赛概率和可追溯外部来源。",
        references=references,
        figures=figures,
        data_disclosure=_data_disclosure(prediction),
        sections=sections,
        caveats=["这是随赛况变化的概率判断，不是确定赛果。", "赔率仅用于识别市场分歧，不构成投注建议。"],
        source_artifact_version=prediction.artifact_version,
    )


def attach_and_cache_report(prediction: TournamentPrediction) -> TournamentPrediction:
    report = build_prediction_report(prediction)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{report.report_id}.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    return prediction.model_copy(update={"prediction_report": report})


def load_cached_report(prediction: TournamentPrediction) -> PredictionAgentReport | None:
    state = prediction.current_tournament_state
    report_id = _report_id(prediction, state.requested_anchor if state else "current")
    path = REPORT_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    try:
        report = PredictionAgentReport.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return report if report.source_artifact_version == prediction.artifact_version else None


def _require_reportable_prediction(prediction: TournamentPrediction) -> None:
    quality = prediction.data_quality_report
    state = prediction.current_tournament_state
    rows = [row for row in prediction.champion_probabilities if row.is_alive and row.probability > 0]
    if (
        prediction.publication_status != "published"
        or not prediction.data_verified
        or quality is None
        or quality.status != "ready"
        or state is None
        or state.validation_status != "ready"
        or not rows
        or abs(sum(row.probability for row in rows) - 1.0) > 1e-6
    ):
        raise ValueError("A report requires a verified published prediction with valid champion probabilities.")


def _summary(
    prediction: TournamentPrediction,
    leader: ChampionProbability,
    rivals: list[ChampionProbability],
) -> str:
    rival_text = "、".join(f"{_team_name(row.team_id)} {row.probability:.1%}" for row in rivals)
    structural = _structural_advantage(prediction, leader)
    return (
        f"截至{_as_of(prediction)}，{_team_name(leader.team_id)}的夺冠概率为 {leader.probability:.1%}，"
        f"高于{rival_text or '其余存活球队'}。{structural}"
        "这个数字来自对剩余真实赛程的重复模拟，不是按球队名单平均分配。"
    )


def _conclusion_bullets(prediction: TournamentPrediction, leader: ChampionProbability) -> list[str]:
    state = prediction.current_tournament_state
    bullets = [
        f"当前阶段：{state.anchor_label if state else '未知'}。",
        f"冠军概率覆盖 {len(prediction.champion_probabilities)} 支仍有夺冠可能的球队。",
        f"{_team_name(leader.team_id)}在 {prediction.simulation_count:,} 次模拟中夺冠 {leader.probability:.1%}。",
    ]
    if _has_locked_final_place(prediction, leader.team_id):
        bullets.append(f"{_team_name(leader.team_id)}已经进入决赛，因此不再承担半决赛出局风险。")
    return bullets


def _leader_reason(prediction: TournamentPrediction, leader: ChampionProbability) -> str:
    scenarios = _leader_scenarios(leader)
    if _has_locked_final_place(prediction, leader.team_id) and scenarios:
        return (
            f"{_team_name(leader.team_id)}领先的首要原因是已经锁定决赛席位。"
            "当前总概率由不同潜在决赛对手出现的机会，以及该队面对每个对手时的模拟胜率共同组成。"
        )
    return (
        f"{_team_name(leader.team_id)}的领先来自球队基础特征和剩余对阵共同作用。"
        "下面只展示模拟中真实出现过的关键对手，不用抽象术语代替比赛情景。"
    )


def _leader_reason_bullets(
    prediction: TournamentPrediction,
    leader: ChampionProbability,
) -> list[str]:
    bullets = []
    for item in _leader_scenarios(leader)[:4]:
        opponent = _team_name(str(item["opponent_team_id"]))
        bullets.append(
            f"对手为{opponent}的情景出现 {item['encounter_probability']:.1%}；"
            f"在该情景下，{_team_name(leader.team_id)}夺冠约 {item['conditional_win_probability']:.1%}。"
        )
    trace = next((item for item in prediction.reasoning_traces if item.target_id == leader.team_id), None)
    if trace:
        bullets.append(trace.summary)
        strongest = "、".join(
            f"{item.get('name')} {float(item.get('value') or 0):.2f}"
            for item in trace.top_factors[:3]
        )
        if strongest:
            bullets.append(f"保存的球队特征中，相对较强的项目为：{strongest}。")
    return bullets or ["当前预测没有保存足够的对手情景分解，不能进一步解释领先原因。"]


def _match_summary(prediction: TournamentPrediction) -> str:
    if not _all_match_predictions(prediction):
        return "当前剩余赛程中没有双方都已确定、且已经生成单场概率的比赛。"
    return (
        "下面展示已确定对阵的最终融合结果，并同时列出球队实力、进球模型和市场赔率各自的判断。"
        "分量之间出现分歧时，报告会直接呈现分歧，而不是只给一个最终数字。"
    )


def _match_bullets(prediction: TournamentPrediction) -> list[str]:
    bullets = []
    for match in _all_match_predictions(prediction)[:4]:
        home = _team_name(match.home_team_id)
        away = _team_name(match.away_team_id)
        bullets.append(
            f"{home} vs {away}：常规时间主胜 {match.home_win_prob:.1%}、平局 {match.draw_prob:.1%}、"
            f"客胜 {match.away_win_prob:.1%}；计入加时和点球后，晋级概率为 "
            f"{home} {match.home_advancement_prob:.1%}、{away} {match.away_advancement_prob:.1%}。"
        )
        for component in match.probability_components:
            bullets.append(
                f"{COMPONENT_NAMES.get(component.name, component.name)}判断：主胜 {component.home_win_prob:.1%}、"
                f"平局 {component.draw_prob:.1%}、客胜 {component.away_win_prob:.1%}，"
                f"在本场融合中的实际权重 {component.effective_weight:.1%}。"
            )
    return bullets[:10] or ["暂无已生成的单场概率。"]


def _evidence_body(prediction: TournamentPrediction) -> str:
    external = [
        evidence
        for match in _all_match_predictions(prediction)
        for evidence in match.evidence
        if evidence.source_type != "model_prior"
    ]
    applied = sum(1 for item in external if item.model_usage in {"applied", "model_input"})
    contextual = len(external) - applied
    return (
        f"本次报告保存了 {len(external)} 条外部证据，其中 {applied} 条实际进入概率，"
        f"{contextual} 条只用于解释背景。每条线索都会标明具体内容和使用方式，不再用“覆盖 100%”代替分析。"
    )


def _evidence_bullets(prediction: TournamentPrediction) -> list[str]:
    bullets = []
    for match in _all_match_predictions(prediction):
        match_label = f"{_team_name(match.home_team_id)} vs {_team_name(match.away_team_id)}"
        for evidence in match.evidence:
            if evidence.source_type == "model_prior":
                continue
            fact = evidence.detail or evidence.claim
            usage = {
                "applied": "已直接修正概率",
                "model_input": "已作为模型输入",
                "context_only": "仅作背景说明",
            }.get(evidence.model_usage, "仅作背景说明")
            bullets.append(
                f"{match_label}｜{evidence.claim}。{fact if fact != evidence.claim else ''}"
                f"{evidence.impact_summary}（{usage}）"
            )
    return bullets[:12] or ["本次没有获取到可追溯的赛前外部证据。"]


def _change_conditions(prediction: TournamentPrediction, leader: ChampionProbability) -> str:
    scenarios = _leader_scenarios(leader)
    if scenarios:
        best = max(scenarios, key=lambda item: item["conditional_win_probability"])
        worst = min(scenarios, key=lambda item: item["conditional_win_probability"])
        return (
            f"对{_team_name(leader.team_id)}而言，更有利的潜在对手是{_team_name(str(best['opponent_team_id']))}"
            f"（情景夺冠率约 {best['conditional_win_probability']:.1%}），更困难的对手是"
            f"{_team_name(str(worst['opponent_team_id']))}（约 {worst['conditional_win_probability']:.1%}）。"
            "半决赛结果会先改变决赛对手分布，随后新的首发、伤停、赔率和比赛环境再改变决赛单场概率。"
        )
    return "新的赛果、确认首发、重大伤停和市场赔率变化都可能改变当前排序，系统需要重新生成报告后再展示新结论。"


def _uncertainty_bullets(
    prediction: TournamentPrediction,
    leader: ChampionProbability,
) -> list[str]:
    missing = prediction.data_quality_report.missing if prediction.data_quality_report else []
    bullets = ["点球专项能力缺失时使用中性先验，涉及点球的情景不应被过度解读。"]
    scenarios = prediction.scenario_match_predictions
    if scenarios:
        missing_market = sum(1 for match in scenarios if "market_odds" in match.missing_fields)
        bullets.insert(
            0,
            f"系统已分别计算 {len(scenarios)} 个潜在对阵；其中 {missing_market} 个没有匹配到可靠赔率，"
            "这些情景只使用保存的球队特征和通过校验的赛前线索，不会补写市场数字。",
        )
    if missing:
        bullets.append("当前已知缺口：" + "、".join(_missing_label(item) for item in missing[:6]) + "。")
    return bullets


def _references(prediction: TournamentPrediction) -> list[PredictionReportReference]:
    refs = [
        PredictionReportReference(
            reference_id="model-1",
            label="本次保存的赛程、球队特征与模型输出",
            source_name="世界杯预测系统",
            kind="model",
            note="包含当前赛事状态、球队输入、单场分量和模拟情景。",
        )
    ]
    seen = set()
    for match in _all_match_predictions(prediction):
        for evidence in match.evidence:
            if not evidence.url or evidence.url in seen or evidence.source_type == "model_prior":
                continue
            seen.add(evidence.url)
            usage = {
                "applied": "已修正概率",
                "model_input": "已进入模型",
                "context_only": "仅作背景",
            }.get(evidence.model_usage, "仅作背景")
            refs.append(
                PredictionReportReference(
                    reference_id=f"src-{len(refs)}",
                    label=evidence.claim[:90],
                    source_name=evidence.source_name,
                    url=evidence.url,
                    kind=evidence.source_type,
                    note=f"{usage}。{evidence.impact_summary}",
                )
            )
    return refs[:16]


def _figures(
    prediction: TournamentPrediction,
    rows: list[ChampionProbability],
    leader: ChampionProbability,
) -> list[PredictionReportFigure]:
    return [
        PredictionReportFigure(
            figure_id="champion_probability_chart",
            title="当前冠军概率",
            kind="champion_probability",
            description="每一条数据都来自本次正式模拟结果。",
            data={
                "teams": [
                    {"team_id": row.team_id, "team_name": _team_name(row.team_id), "probability": row.probability}
                    for row in rows
                ]
            },
        ),
        PredictionReportFigure(
            figure_id="champion_scenario_chart",
            title=f"{_team_name(leader.team_id)}的潜在对手情景",
            kind="champion_scenarios",
            description="对手出现概率与该情景下的夺冠概率分开计算。",
            data={"leader_team_id": leader.team_id, "scenarios": _leader_scenarios(leader)},
        ),
        PredictionReportFigure(
            figure_id="match_model_comparison",
            title="单场模型与市场分歧",
            kind="match_model_comparison",
            description="比较各概率分量与最终融合结果。",
            data={
                "matches": [
                    {
                        "match_id": match.match_id,
                        "home_team_id": match.home_team_id,
                        "away_team_id": match.away_team_id,
                        "final": {
                            "home": match.home_win_prob,
                            "draw": match.draw_prob,
                            "away": match.away_win_prob,
                            "home_advance": match.home_advancement_prob,
                            "away_advance": match.away_advancement_prob,
                        },
                        "components": [component.model_dump(mode="json") for component in match.probability_components],
                    }
                    for match in _all_match_predictions(prediction)
                ]
            },
        ),
        PredictionReportFigure(
            figure_id="team_feature_chart",
            title="球队模型输入对比",
            kind="team_features",
            description="展示本次预测实际保存的球队输入，不使用默认强队标签。",
            data={"teams": [item.model_dump(mode="json") for item in prediction.team_features]},
        ),
        PredictionReportFigure(
            figure_id="evidence_cards",
            title="赛前证据及其使用方式",
            kind="evidence_cards",
            description="区分真正入模的证据和只用于背景说明的线索。",
            data={
                "items": [
                    {
                        "match_id": match.match_id,
                        "home_team_id": match.home_team_id,
                        "away_team_id": match.away_team_id,
                        **evidence.model_dump(mode="json"),
                    }
                    for match in _all_match_predictions(prediction)
                    for evidence in match.evidence
                    if evidence.source_type != "model_prior"
                ]
            },
        ),
    ]


def _leader_scenarios(leader: ChampionProbability) -> list[dict]:
    scenarios = []
    for item in leader.key_matchups:
        encounter = float(item.get("encounter_probability") or 0)
        elimination = float(item.get("elimination_probability") or 0)
        if encounter <= 0:
            continue
        conditional_loss = min(1.0, max(0.0, elimination / encounter))
        scenarios.append(
            {
                "opponent_team_id": item.get("opponent_team_id"),
                "round": item.get("round"),
                "encounter_probability": encounter,
                "conditional_win_probability": 1 - conditional_loss,
                "unconditional_elimination_probability": elimination,
            }
        )
    return scenarios


def _all_match_predictions(prediction: TournamentPrediction):
    return [*prediction.match_predictions, *prediction.scenario_match_predictions]


def _structural_advantage(prediction: TournamentPrediction, leader: ChampionProbability) -> str:
    if _has_locked_final_place(prediction, leader.team_id):
        return f"{_team_name(leader.team_id)}已经进入决赛，这是当前领先的主要结构性原因。"
    return "当前领先同时受到球队输入和剩余对阵的影响。"


def _has_locked_final_place(prediction: TournamentPrediction, team_id: str) -> bool:
    state = prediction.current_tournament_state
    return bool(state and any(
        match.stage == "Final" and team_id in {match.home_team_id, match.away_team_id}
        for match in state.remaining_matches
    ))


def _data_disclosure(prediction: TournamentPrediction) -> str:
    unresolved = sum(
        1
        for match in (prediction.current_tournament_state.remaining_matches if prediction.current_tournament_state else [])
        if not match.home_team_id or not match.away_team_id or match.home_team_id == "TBD" or match.away_team_id == "TBD"
    )
    if unresolved:
        return (
            f"剩余赛程中有 {unresolved} 场尚未确定完整对阵；这些比赛会按球队特征进行情景模拟，"
            "但在双方确定前不会声称已经接入对应的临场赔率、阵容或新闻。"
        )
    return "剩余比赛对阵均已确定，报告展示本次预测中实际保存的数据和外部证据。"


def _as_of(prediction: TournamentPrediction) -> str:
    value = prediction.input_data_as_of or prediction.generated_at
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "当前输入时间"


def _missing_label(value: str) -> str:
    return {
        "market_odds": "赔率盘口",
        "confirmed_lineup_or_injuries": "确认首发与伤停",
        "fresh_web_evidence": "最新联网证据",
        "schedule_snapshot_stale": "赛程更新时间",
        "schedule_sync_not_success": "赛程同步状态",
    }.get(value, value.replace("_", " "))


def _report_id(prediction: TournamentPrediction, anchor: str) -> str:
    raw = f"{prediction.artifact_id}:{anchor}:{prediction.schedule_hash}:{prediction.generated_at}:{prediction.artifact_version}"
    return f"prediction-report-{anchor}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _team_name(team_id: str | None) -> str:
    if not team_id:
        return "待定"
    return TEAM_NAMES.get(team_id, team_id)
