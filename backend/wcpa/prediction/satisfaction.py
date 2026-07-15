"""预测回答的自动用户满意度质量门。"""

from __future__ import annotations

from dataclasses import dataclass

from wcpa.schemas.prediction import MatchPrediction


REFUSAL_TERMS = (
    "无法预测",
    "不能预测",
    "没有足够数据",
    "数据不足所以",
    "无法判断",
    "cannot predict",
    "insufficient data",
)
BETTING_TERMS = ("稳赚", "必买", "下注金额", "投注组合", "bet now", "guaranteed bet")


@dataclass(frozen=True)
class PredictionSatisfactionResult:
    automatic_score: int
    passed: bool
    dimensions: dict[str, int]
    hard_failures: list[str]
    issues: list[str]


def evaluate_prediction_satisfaction(
    prediction: MatchPrediction,
    answer: str,
    placeholder_expected: bool = False,
) -> PredictionSatisfactionResult:
    """执行 60 分自动质量门；人工体验的 40 分由独立评审补充。"""

    lowered = answer.casefold()
    dimensions: dict[str, int] = {}
    issues: list[str] = []
    hard_failures: list[str] = []

    has_tendency = bool(answer.strip()) and any(
        term in answer for term in ("第一倾向", "更看好", "结论倾向", "夺冠")
    )
    dimensions["prediction_given"] = 10 if has_tendency else 0
    if not has_tendency:
        issues.append("回答没有直接给出预测倾向。")

    probability_total = (
        prediction.home_win_prob + prediction.draw_prob + prediction.away_win_prob
    )
    probabilities_valid = abs(probability_total - 1.0) <= 0.0015
    dimensions["probability_validity"] = 8 if probabilities_valid else 0
    if not probabilities_valid:
        hard_failures.append("invalid_probabilities")

    refusal = next((term for term in REFUSAL_TERMS if term in lowered), "")
    dimensions["no_missing_data_refusal"] = 10 if not refusal else 0
    if refusal:
        hard_failures.append("missing_data_refusal")

    traceable_components = all(
        component.name == "neutral_prior" or bool(component.evidence_ids)
        for component in prediction.probability_components
    )
    evidence_traceable = bool(prediction.evidence) and traceable_components
    dimensions["evidence_traceability"] = 8 if evidence_traceable else 0
    if not evidence_traceable:
        issues.append("至少一个关键概率组件缺少证据或模型假设引用。")

    has_fact_boundary = "模型推断" in answer and any(
        term in answer for term in ("来源与边界", "事实边界", "已确认事实")
    )
    dimensions["fact_boundary"] = 8 if has_fact_boundary else 0
    if not has_fact_boundary:
        issues.append("回答没有清楚区分模型推断和事实/来源边界。")

    missing_transparent = "缺失" in answer or "待确认" in answer
    dimensions["missing_data_transparency"] = 6 if missing_transparent else 0
    if not missing_transparent:
        issues.append("回答没有说明缺失字段及其影响。")

    if placeholder_expected:
        path_consistent = "占位" in answer and not _claims_placeholder_as_team(answer)
    else:
        path_consistent = True
    dimensions["path_consistency"] = 6 if path_consistent else 0
    if not path_consistent:
        hard_failures.append("placeholder_fabrication")

    betting_term = next((term for term in BETTING_TERMS if term in lowered), "")
    dimensions["non_betting_boundary"] = 4 if not betting_term else 0
    if betting_term:
        hard_failures.append("betting_instruction")

    automatic_score = sum(dimensions.values())
    return PredictionSatisfactionResult(
        automatic_score=automatic_score,
        passed=automatic_score >= 54 and not hard_failures,
        dimensions=dimensions,
        hard_failures=hard_failures,
        issues=issues,
    )


def _claims_placeholder_as_team(answer: str) -> bool:
    lowered = answer.casefold()
    return any(
        phrase in lowered
        for phrase in ("w101就是", "w102就是", "w101 is", "w102 is")
    )
