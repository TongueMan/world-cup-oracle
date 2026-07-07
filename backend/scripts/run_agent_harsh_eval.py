"""Run harsh product-level Agent evaluation cases.

This script intentionally lives as a UTF-8 file so Chinese prompts are not
corrupted by PowerShell pipe encoding.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from wcpa.agents.research_engine import stream_research_answer
from wcpa.schemas.agent_chat import AgentResearchRequest


ROOT = Path(__file__).resolve().parents[2]
USA_BEL = "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515"
FINAL = "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537"
QF_W93 = "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452527"


def main() -> None:
    _load_env(ROOT / ".env")
    results = [_run_case(case) for case in _cases()]
    output = ROOT / "outputs" / "agent_harsh_eval_round3.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in results:
        _safe_print_json(row)
    print(f"WROTE {output.relative_to(ROOT)}")


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _cases() -> list[dict[str, Any]]:
    history = [
        {"role": "assistant", "content": "决赛 W101 vs W102 中，W101 是美国队，W102 是比利时队。"},
        {
            "role": "user",
            "content": "你刚才把 W101 和 W102 当成具体球队是错的。它们是占位符。接下来必须按北京时间说。",
        },
    ]
    return [
        {
            "id": "HX3-001",
            "mode": "local_only",
            "match": USA_BEL,
            "q": "美国 vs 比利时什么时候踢？场地到底是不是 Lumen Field / Seattle Stadium？只说确定事实。",
            "risk": ["adopted_sources", "local_context", "战术对位", "历史与状态"],
        },
        {
            "id": "HX3-002",
            "mode": "local_only",
            "match": USA_BEL,
            "q": "Lumen Field 是人工草皮吗？世界杯这场怎么处理？请区分确定和待确认。",
            "must": ["本地结构化数据没有确认", "不能仅凭场馆常识断言"],
            "risk": ["最核心的环境变量", "是人工草皮", "全封闭式顶棚"],
        },
        {
            "id": "HX3-003",
            "mode": "local_only",
            "match": FINAL,
            "q": "决赛 W101 vs W102 是什么意思？请不要编造具体球队。",
            "must": ["W101", "W102"],
            "risk": ["美国 vs", "比利时 vs", "巴西 vs", "法国 vs", "英格兰 vs", "阿根廷 vs"],
        },
        {
            "id": "HX3-004",
            "mode": "local_only",
            "match": QF_W93,
            "q": "W93 vs W94 这场 1/4 决赛怎么分析？先解释 W93 和 W94 来源，再给情景推演。",
            "must": ["W93", "W94", "葡萄牙", "西班牙", "美国", "比利时"],
            "risk": ["已经确定", "双方分别是"],
        },
        {
            "id": "HX3-005",
            "mode": "local_only",
            "match": USA_BEL,
            "q": "预测美国 vs 比利时三个比分，按概率排序，但不要使用引用角标。",
            "risk": ["[1]", "[2]", "[3]", "历史与状态", "战术对位"],
        },
        {
            "id": "HX3-006",
            "mode": "required",
            "match": USA_BEL,
            "q": "Balogun 到底能不能出战美国 vs 比利时？请给来源，并区分确定事实和待确认。",
            "must": ["Balogun"],
            "risk": ["一定无法出战", "无法出战"],
        },
        {
            "id": "HX3-007",
            "mode": "required",
            "match": USA_BEL,
            "q": "比利时上一轮怎么晋级的？别只给当前比赛中心。",
            "must": ["塞内加尔", "晋级方"],
            "risk": ["美国 vs 比利时是一场", "焦点战"],
        },
        {
            "id": "HX3-008",
            "mode": "local_only",
            "match": FINAL,
            "q": "基于我刚才的纠正，重新解释决赛 W101 vs W102，并说明你修正了什么。",
            "history": history,
            "must": ["占位符", "北京时间"],
            "risk": ["美国队", "比利时队"],
        },
    ]


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    context = {
        "currentPage": "worldcup-dashboard",
        "activeTab": "matches",
        "currentMatchId": case["match"],
    }
    api_key = os.environ.get("WCPA_LLM_API_KEY", "")
    model = os.environ.get("WCPA_LLM_MODEL", "deepseek-chat") or "deepseek-chat"
    base_url = os.environ.get("WCPA_LLM_BASE_URL") or None
    provider = "deepseek" if not base_url or "deepseek" in base_url.lower() else "custom"
    request = AgentResearchRequest.model_validate(
        {
            "message": case["q"],
            "context": context,
            "history": case.get("history", []),
            "llmConfig": {
                "provider": provider,
                "model": model,
                "apiKey": api_key,
                "baseURL": base_url,
                "searchEnabled": case["mode"] == "required",
            },
            "searchMode": case["mode"],
            "toolIntent": "general",
        }
    )
    started = time.time()
    answer_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    diagnostics: dict[str, Any] = {}
    try:
        for raw in stream_research_answer(request):
            event, data = _parse_sse(raw)
            if event == "token":
                answer_parts.append(data.get("content", ""))
            elif event == "sources":
                sources = data.get("results") or []
            elif event == "error":
                errors.append(data.get("message") or str(data))
            elif event == "done":
                if data.get("answer") and not answer_parts:
                    answer_parts.append(data.get("answer"))
                diagnostics = data.get("diagnostics") or diagnostics
                sources = data.get("sources") or sources
    except Exception as exc:  # noqa: BLE001 - eval harness should keep going
        errors.append(f"EXCEPTION: {type(exc).__name__}: {exc}")

    answer = "".join(answer_parts)
    citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    source_ids = {int(source.get("citationId") or 0) for source in sources}
    source_ids.discard(0)
    sources_by_id = {int(source.get("citationId") or 0): source for source in sources if source.get("citationId")}
    unsupported_citation_ids = sorted(
        citation_id
        for citation_id in citation_ids & set(sources_by_id)
        if not sources_by_id[citation_id].get("supportedClaims")
    )
    quality_payload = diagnostics.get("quality") or {}
    return {
        "id": case["id"],
        "mode": case["mode"],
        "seconds": round(time.time() - started, 1),
        "errors": errors,
        "source_count": len(sources),
        "risk_hits": [item for item in case.get("risk", []) if item in answer],
        "must_misses": [item for item in case.get("must", []) if item not in answer],
        "invalid_citations": sorted(citation_ids - source_ids) if source_ids else sorted(citation_ids),
        "unsupported_citations": unsupported_citation_ids,
        "supported_claim_source_count": sum(1 for source in sources if source.get("supportedClaims")),
        "quality": quality_payload.get("total"),
        "quality_issues": quality_payload.get("issues") or [],
        "answer_excerpt": answer[:1000].replace("\n", " "),
        "sources": [
            {
                "id": source.get("citationId"),
                "title": source.get("title"),
                "domain": source.get("domain"),
                "relevance": source.get("relevanceScore"),
                "supportedClaims": source.get("supportedClaims") or [],
            }
            for source in sources[:5]
        ],
    }


def _parse_sse(raw: str) -> tuple[str, dict[str, Any]]:
    if not raw.startswith("event:"):
        return "", {}
    event = raw.split("\n", 1)[0].replace("event:", "").strip()
    data_line = next((line for line in raw.splitlines() if line.startswith("data:")), "data: {}")
    try:
        data = json.loads(data_line.removeprefix("data:").strip())
    except ValueError as exc:
        data = {"parse_error": str(exc), "raw": data_line[:300]}
    return event, data


def _safe_print_json(row: dict[str, Any]) -> None:
    text = json.dumps(row, ensure_ascii=False)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")


if __name__ == "__main__":
    main()
