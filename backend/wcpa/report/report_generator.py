"""报告生成器 — MVP: 将 artifact 转为 Markdown。"""
from wcpa.schemas.artifact import TournamentPrediction

def generate_report(artifact: TournamentPrediction) -> str:
    """将预测 artifact 转为 Markdown 报告。"""
    lines = [
        "# World Cup Oracle 预测报告",
        "",
        f"**届次**: {artifact.edition}",
        f"**随机种子**: {artifact.seed}",
        f"**预测模式**: {artifact.mode}",
        f"**生成时间**: {artifact.generated_at}",
        "",
        "## 冠军预测",
        "",
        f"- **综合冠军**: {artifact.champion_team_id or 'N/A'}",
        f"- **亚军**: {artifact.runner_up_team_id or 'N/A'}",
        f"- **四强**: {', '.join(artifact.semifinalists) if artifact.semifinalists else 'N/A'}",
        "",
        "## 小组赛排名",
        "",
    ]
    
    for gs in artifact.group_standings:
        lines.append(f"### {gs.group} 组")
        lines.append("| 排名 | 球队 | 积分 | 胜 | 平 | 负 | 进球 | 失球 | 净胜球 |")
        lines.append("|------|------|------|---|---|---|------|------|--------|")
        for row in gs.rows:
            lines.append(f"| {row.rank} | {row.team_id} | {row.points} | {row.won} | {row.drawn} | {row.lost} | {row.goals_for} | {row.goals_against} | {row.goal_difference} |")
        lines.append("")
    
    if artifact.bracket:
        lines.append("## 淘汰赛")
        lines.append("")
        for slot in artifact.bracket.slots:
            home = slot.home_team_id or "TBD"
            away = slot.away_team_id or "TBD"
            score = f"{slot.home_score}-{slot.away_score}" if slot.home_score is not None else "TBD"
            winner = slot.winner_team_id or "TBD"
            lines.append(f"- **{slot.round}** {slot.match_id}: {home} {score} {away} → {winner}")
        lines.append("")
    
    lines.append(f"## 比赛预测总数: {len(artifact.match_predictions)}")
    
    return "\n".join(lines)
