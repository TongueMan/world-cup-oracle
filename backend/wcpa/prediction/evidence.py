"""多源证据的降级等级与置信度边界。"""

from __future__ import annotations

from wcpa.schemas.prediction import DataGrade, PredictionContext


GRADE_CONFIDENCE_CAPS: dict[DataGrade, float] = {
    "A": 0.90,
    "B": 0.78,
    "C": 0.65,
    "D": 0.50,
    "E": 0.35,
}


def assess_data_grade(
    context: PredictionContext,
    structured_features_available: bool,
) -> tuple[DataGrade, list[str]]:
    """根据可用组件评估数据等级，同时保留显式缺失字段。"""

    missing = list(dict.fromkeys(context.missing_fields))
    structured = context.structured_data_available and structured_features_available
    has_market = bool(context.odds)
    has_web = context.web_search_succeeded and (
        context.semantic_signal is not None
        or any(item.source_type == "web" for item in context.evidence)
    )

    if not structured:
        missing.append("structured_team_features")
    if not has_market:
        missing.append("market_odds")
    if not context.lineup_data_available:
        missing.append("confirmed_lineup_or_injuries")
    if context.web_search_attempted and not context.web_search_succeeded:
        missing.append("fresh_web_evidence")

    missing = list(dict.fromkeys(missing))
    if context.data_grade_override is not None:
        return context.data_grade_override, missing
    if structured and has_market and context.lineup_data_available and has_web:
        return "A", missing
    if structured and has_market:
        return "B", missing
    if structured:
        return "C", missing
    if has_web:
        return "D", missing
    return "E", missing


def confidence_cap_for(grade: DataGrade) -> float:
    return GRADE_CONFIDENCE_CAPS[grade]


def degradation_assumptions(grade: DataGrade, missing_fields: list[str]) -> list[str]:
    """生成人类可理解、不会拒绝预测的降级说明。"""

    assumptions = [f"数据等级 {grade}，缺失项只降低置信度，不停止预测。"]
    if "market_odds" in missing_fields:
        assumptions.append("缺少可靠赔率，融合权重已转移到实力、进球和可用语义证据。")
    if "confirmed_lineup_or_injuries" in missing_fields:
        assumptions.append("首发或伤停未完全确认，未施加未经证据支持的阵容修正。")
    if "structured_team_features" in missing_fields:
        assumptions.append("结构化球队特征不足，使用联网语义与中性先验完成低置信度预测。")
    if "fresh_web_evidence" in missing_fields:
        assumptions.append("联网证据不可用，继续使用本地信息和模型先验。")
    return assumptions
