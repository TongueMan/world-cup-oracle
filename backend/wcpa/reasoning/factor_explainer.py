"""因子贡献解释 — MVP 桩。"""
from wcpa.schemas.artifact import ReasoningTrace
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.artifact import TeamFeatures

def explain_factors(match_id: str, prediction: MatchPrediction,
                    home_features: TeamFeatures, away_features: TeamFeatures) -> ReasoningTrace:
    """解释预测因子 — MVP: 从 reason_codes 生成简单文本。"""
    factors = []
    if "ranking_gap" in prediction.reason_codes:
        factors.append({"name": "ranking_gap", "impact": abs(home_features.normalized_fifa_rank - away_features.normalized_fifa_rank)})
    if "recent_form" in prediction.reason_codes:
        factors.append({"name": "recent_form", "impact": abs(home_features.recent_form - away_features.recent_form)})
    if "attack_advantage" in prediction.reason_codes:
        factors.append({"name": "attack_advantage", "impact": abs(home_features.attack - away_features.attack)})
    if "defense_advantage" in prediction.reason_codes:
        factors.append({"name": "defense_advantage", "impact": abs(home_features.defense - away_features.defense)})
    
    factors.sort(key=lambda x: x["impact"], reverse=True)
    
    summary = f"预测 {prediction.winner_team_id} 胜出，比分 {prediction.predicted_score}。"
    
    return ReasoningTrace(
        target_id=match_id,
        summary=summary,
        top_factors=factors[:5],
        assumptions=["MVP 阶段使用 fixture 数据，未接入实时伤停。"],
    )
