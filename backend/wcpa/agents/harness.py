"""LLM-ready multi-agent harness with deterministic fallback opinions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.schemas.debate import AgentOpinion
from wcpa.schemas.match import Match
from wcpa.schemas.prediction import MatchPrediction
from wcpa.schemas.symbolic import SymbolicSignal
from wcpa.shared.env import env_bool, env_str
from wcpa.shared.paths import CACHE_DIR
from wcpa.agents.tooling import gather_agent_evidence


AGENT_ROLES: dict[str, str] = {
    "Data Analyst Agent": "用排名、Elo、近期状态和概率模型解释胜率与比分。",
    "Tactical Analyst Agent": "分析双方攻防结构、节奏、关键对位和克制关系。",
    "Narrative Agent": "分析士气、压力、黑马故事、宿命感和球迷势能。",
    "Tarot Agent": "基于塔罗牌面解释稳定性、转折和崩盘风险。",
    "I-Ching Agent": "基于卦象解释险局、僵持、突变、加时或点球倾向。",
    "Astrology Agent": "基于四元素能量解释节奏、情绪波动和开放程度。",
}


class AgentUnavailableError(RuntimeError):
    """Raised when production LLM agents are unavailable."""


@dataclass(frozen=True)
class MatchContext:
    match: Match
    prediction: MatchPrediction
    home_team: dict[str, Any]
    away_team: dict[str, Any]
    symbolic_signal: dict[str, Any] | None = None
    narrative_profiles: list[dict[str, Any]] | None = None

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "match": self.match.model_dump(mode="json"),
            "prediction": self.prediction.model_dump(mode="json"),
            "home_team": self.home_team,
            "away_team": self.away_team,
            "symbolic_signal": self.symbolic_signal or {},
            "narrative_profiles": self.narrative_profiles or [],
        }


class AgentHarness:
    """Runs one analysis agent with cache, LLM call, and rule fallback."""

    def __init__(self, repository: PostgresRepository | None = None):
        self.repository = repository or PostgresRepository()
        self.base_url = env_str("WCPA_LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = env_str("WCPA_LLM_MODEL", "deepseek-chat")
        self.api_key = env_str("WCPA_LLM_API_KEY", "")
        self.enabled = env_bool("WCPA_ENABLE_LLM_AGENTS", False) and bool(self.api_key)

    def run_agent(self, agent_name: str, context: MatchContext) -> AgentOpinion:
        prompt = self._build_prompt(agent_name, context)
        cache_key = self._cache_key(agent_name, prompt)
        cached = self._load_cache(cache_key)
        if cached:
            return AgentOpinion(**cached)

        if not self.enabled:
            raise AgentUnavailableError("LLM agents disabled or API key missing.")

        opinion = self._call_llm(agent_name, prompt, context)
        if opinion is None:
            raise AgentUnavailableError(f"{agent_name} LLM call failed.")

        payload = opinion.model_dump(mode="json")
        self._save_cache(cache_key, context.match.match_id, agent_name, prompt, payload)
        return opinion

    def _build_prompt(self, agent_name: str, context: MatchContext) -> str:
        context_payload = context.to_prompt_payload()
        evidence = gather_agent_evidence(agent_name, context_payload)
        payload = json.dumps(
            {"context": context_payload, "tool_evidence": evidence},
            ensure_ascii=False,
            indent=2,
        )
        return (
            f"你是 World Cup Oracle 的 {agent_name}。\n"
            f"角色职责：{AGENT_ROLES[agent_name]}\n"
            "你可以使用 tool_evidence 中的知识库和联网搜索摘要，但必须在 cited_signals 中引用来源。\n"
            "不要编造未在 context 或 tool_evidence 中出现的伤停、比分、排名或赛程事实。\n"
            "请只输出 JSON，字段为 agent, support_team_id, confidence, summary, "
            "detail, reason_codes, cited_signals, risk_flags。\n"
            "象征推理只能表达不确定性，不能覆盖高置信度理性预测。\n"
            f"比赛上下文：\n{payload}"
        )

    def _call_llm(
        self, agent_name: str, prompt: str, context: MatchContext
    ) -> AgentOpinion | None:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你输出严格 JSON，不要 Markdown，不要额外解释。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
                timeout=45,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            data.setdefault("agent", agent_name)
            return AgentOpinion(**data)
        except Exception:
            return None

    def _fallback_opinion(self, agent_name: str, context: MatchContext) -> AgentOpinion:
        """Demo-only fallback. Production flow never calls this method."""
        pred = context.prediction
        winner = pred.winner_team_id
        confidence = pred.confidence
        reasons = list(pred.reason_codes)
        cited = ["rational_prediction"]
        risks: list[str] = []
        summary = f"基于当前预测，倾向 {winner or '平局'}。"
        detail = "规则兜底生成：LLM 未启用或调用失败，使用结构化信号生成观点。"

        if agent_name == "Tactical Analyst Agent":
            reasons = ["attack_defense_matchup", *reasons[:2]]
            summary = "战术面更支持攻防效率更稳定的一方。"
            cited = ["team_features", "match_prediction"]
        elif agent_name == "Narrative Agent":
            reasons = ["morale_pressure_balance"]
            confidence = max(0.35, min(0.75, confidence - 0.05))
            summary = "叙事轨关注压力与士气，暂未形成强烈反向信号。"
            cited = ["narrative_profiles"]
        elif agent_name == "Tarot Agent":
            reasons = ["tarot_turning_point"]
            confidence = 0.52
            summary = "牌面提示比赛有转折，但不足以推翻理性预测。"
            cited = ["symbolic_signal.tarot"]
            risks = ["late_swing"]
        elif agent_name == "I-Ching Agent":
            reasons = ["iching_risk"]
            confidence = 0.51
            summary = "卦象偏向险局，需要关注僵持和加时风险。"
            cited = ["symbolic_signal.iching"]
            risks = ["extra_time"]
        elif agent_name == "Astrology Agent":
            reasons = ["element_energy"]
            confidence = 0.5
            summary = "星象能量提示节奏与情绪波动，比赛开放度可能上升。"
            cited = ["symbolic_signal.astrology"]
            risks = ["emotional_volatility"]

        return AgentOpinion(
            agent=agent_name,
            support_team_id=winner,
            confidence=round(confidence, 4),
            summary=summary,
            detail=detail,
            reason_codes=reasons,
            cited_signals=cited,
            risk_flags=risks,
        )

    def _cache_key(self, agent_name: str, prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"{self.model}:{agent_name}:{digest}"

    def _load_cache(self, cache_key: str) -> dict | None:
        pg_payload = self.repository.load_agent_run(cache_key)
        if pg_payload:
            return pg_payload
        path = self._file_cache_path(cache_key)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _save_cache(
        self,
        cache_key: str,
        match_id: str,
        agent_name: str,
        prompt: str,
        payload: dict,
    ) -> None:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self.repository.save_agent_run(
            cache_key=cache_key,
            match_id=match_id,
            agent_name=agent_name,
            model=self.model,
            prompt_hash=prompt_hash,
            payload=payload,
        )
        path = self._file_cache_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _file_cache_path(self, cache_key: str) -> Path:
        safe = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return CACHE_DIR / "agent_runs" / f"{safe}.json"


def build_agent_opinions(context: MatchContext) -> list[AgentOpinion]:
    harness = AgentHarness()
    if not harness.enabled:
        raise AgentUnavailableError("LLM agents disabled or API key missing.")
    return [harness.run_agent(agent_name, context) for agent_name in AGENT_ROLES]
