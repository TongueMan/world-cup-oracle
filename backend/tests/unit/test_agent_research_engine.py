"""ResearchAnswerEngine tests."""

from __future__ import annotations

import json

from wcpa.agents.agent_context_builder import build_match_context
from wcpa.agents.firecrawl_client import FirecrawlCallError
from wcpa.agents.research_engine import (
    _finalize_answer,
    _quality_min_total,
    _research_messages,
    _supported_claims,
    build_research_plan,
    stream_research_answer,
)
from wcpa.agents.source_quality import QualifiedSource
from wcpa.agents.research_quality import evaluate_research_answer
from wcpa.schemas.agent_chat import AgentResearchRequest


def _request(**overrides):
    payload = {
        "message": "请问明天巴西踢挪威的比赛你怎么看",
        "context": {
            "currentPage": "worldcup-dashboard",
            "data": {
                "home_team_raw": "巴西",
                "away_team_raw": "挪威",
                "stage": "16 强赛",
            },
        },
        "history": [],
        "llmConfig": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "apiKey": "",
            "searchEnabled": False,
        },
        "searchMode": "local_only",
        "toolIntent": "match_analysis",
    }
    payload.update(overrides)
    return AgentResearchRequest.model_validate(payload)


def test_research_plan_generates_product_queries():
    req = _request()
    context = {"match": {"home_team_raw": "巴西", "away_team_raw": "挪威", "stage": "16 强赛"}}

    plan = build_research_plan(req, context, {"enabled": False})

    assert len(plan.queries) >= 6
    assert any("official" in query for query in plan.queries)
    assert any("injuries" in query or "lineup" in query for query in plan.queries)
    assert any("tactical" in query for query in plan.queries)
    assert any("head to head" in query for query in plan.queries)


def test_tournament_champion_question_uses_global_queries():
    req = _request(
        message="如果让你预测本次世界杯冠军，哪些国家夺冠概率最大？",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452517",
            "data": {"scope": "tournament"},
        },
        toolIntent="general",
    )
    events = list(stream_research_answer(req))
    text = "".join(events)

    assert "winner prediction favorites" in text
    assert "巴西 vs 挪威" not in text
    assert "event: confirmation_required" not in text


def test_environment_question_uses_venue_queries_from_structured_context():
    req = _request(
        message="Lumen Field 是人工草皮吗？世界杯这场怎么处理？",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")

    plan = build_research_plan(req, context, {"enabled": False})

    assert plan.intent == "weather_environment"
    assert any("Lumen Field" in query or "Seattle Stadium" in query for query in plan.queries)
    assert context["environment"]["venue"]["venue_name"] == "Lumen Field"


def test_pitch_question_without_pitch_evidence_is_guarded():
    req = _request(
        message="Lumen Field 是人工草皮吗？世界杯这场怎么处理？请区分确定和待确认。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer(
        "Lumen Field 是人工草皮，这是本场最核心的环境变量。",
        [],
        request=req,
        context=context,
        plan=plan,
    )

    assert "本地结构化数据没有确认" in answer
    assert "不能仅凭场馆常识断言" in answer
    assert "最核心的环境变量" not in answer


def test_quality_threshold_respects_local_boundary_contracts():
    req = _request(
        message="Lumen Field 是人工草皮吗？世界杯这场怎么处理？请区分确定和待确认。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        searchMode="local_only",
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")
    plan = build_research_plan(req, context, {"enabled": False})

    assert _quality_min_total(req, plan, []) == 8


def test_facts_only_contract_overrides_long_analysis():
    req = _request(
        message="美国 vs 比利时什么时候踢？场地到底是不是 Lumen Field / Seattle Stadium？只说确定事实。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer("这里是一段很长的赛前分析。", [], request=req, context=context, plan=plan)

    assert "确定事实" in answer
    assert "Lumen Field" in answer
    assert "Seattle Stadium" in answer
    assert "很长的赛前分析" not in answer


def test_previous_match_report_uses_local_previous_match():
    req = _request(
        message="比利时上一轮怎么晋级的？别只给当前比赛中心。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        searchMode="local_only",
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515")
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer("美国 vs 比利时是一场焦点战。", [], request=req, context=context, plan=plan)

    assert plan.intent == "previous_match_report"
    assert "比利时" in answer
    assert "塞内加尔" in answer
    assert "晋级方" in answer


def test_balogun_focus_removes_unrequested_player_noise():
    req = _request(message="Balogun 到底能不能踢美国 vs 比利时？请区分确定和待确认。")
    context = {"match": {"home_team_raw": "美国", "away_team_raw": "比利时"}}
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer(
        "Balogun 可以出战。\n\nPulisic 无法出战，这需要确认。",
        [{"citationId": 1}],
        request=req,
        context=context,
        plan=plan,
    )

    assert "Balogun 可以出战" in answer
    assert "Pulisic" not in answer
    assert "无法出战" not in answer


def test_supported_claims_extract_balogun_availability():
    req = _request(message="Balogun 到底能不能踢美国 vs 比利时？")
    context = {"match": {"home_team_raw": "美国", "away_team_raw": "比利时"}}
    plan = build_research_plan(req, context, {"enabled": False})
    source = QualifiedSource(
        title="Why Folarin Balogun Can Play For USA vs. Belgium Despite Red Card",
        url="https://www.foxsports.com/example",
        domain="foxsports.com",
        snippet="Folarin Balogun is available for selection against Belgium after a red card.",
        published_at=None,
        source_quality_score=0.95,
        raw={},
        excerpt="Folarin Balogun can play for USA vs Belgium despite his red card suspension issue.",
    )

    claims = _supported_claims(source, plan)

    assert any(item["type"] == "player_availability" for item in claims)
    assert any("Balogun" in item["claim"] for item in claims)


def test_quality_gate_checks_citation_supported_claims():
    answer = "Balogun 可以出战美国对比利时。[1]\n普利西奇确定无法出战。[1]"
    sources = [
        {
            "citationId": 1,
            "relevanceScore": 0.9,
            "supportedClaims": [
                {
                    "type": "player_availability",
                    "claim": "Folarin Balogun 可出战或可供美国队选择",
                    "evidence": "Balogun can play for USA vs Belgium.",
                }
            ],
        }
    ]

    report = evaluate_research_answer(
        answer=answer,
        sources=sources,
        context={"match": {"home_team_raw": "美国", "away_team_raw": "比利时"}},
        min_total=20,
    )

    assert report.dimensions["citation_coverage"] == 2
    assert any("未明显匹配" in issue for issue in report.issues)


def test_quality_gate_does_not_require_sources_for_local_answers():
    report = evaluate_research_answer(
        answer="确定事实：比赛美国 vs 比利时。场馆 Lumen Field。",
        sources=[],
        context={"match": {"home_team_raw": "美国", "away_team_raw": "比利时"}},
        min_total=8,
        source_required=False,
        structure_required=False,
        concise_allowed=True,
    )

    assert report.dimensions["source_quality"] == 5
    assert report.dimensions["citation_coverage"] == 5
    assert not any("来源" in issue for issue in report.issues)
    assert not any("过短" in issue or "结构" in issue for issue in report.issues)


def test_local_answer_removes_unsupported_personnel_names_without_rosters():
    req = _request(message="W93 vs W94 怎么分析？")
    context = {
        "match": {
            "home_team_raw": "W93",
            "away_team_raw": "W94",
            "stage": "QF",
        },
        "bracket": {"has_placeholders": True},
    }
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer(
        "比利时的德布劳内、卢卡库等人会决定比赛走势。",
        [],
        request=req,
        context=context,
        plan=plan,
    )

    assert "德布劳内" not in answer
    assert "卢卡库" not in answer
    assert "淘汰赛路径占位" in answer
    assert "不是已确定球队" in answer


def test_research_messages_include_history_corrections_and_bracket_placeholders():
    req = _request(
        message="决赛 W101 vs W102 是什么意思？",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537",
        },
        history=[
            {"role": "user", "content": "你刚才把 W101 当成球队了，这是错的。"},
            {"role": "assistant", "content": "收到，W101 就是美国队，W102 就是比利时队。"},
            {"role": "user", "content": "接下来都按北京时间说。"},
        ],
        toolIntent="general",
    )
    context = build_match_context("SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537")
    plan = build_research_plan(req, context, {"enabled": False})

    messages = _research_messages(req, context, plan, [], [], "")
    payload_text = messages[-1]["content"]

    assert "W101" in payload_text
    assert "has_placeholders" in payload_text
    assert "你刚才把 W101 当成球队了" in payload_text
    assert "接下来都按北京时间说" in payload_text
    assert "W101 就是美国队" not in payload_text
    assert "W102 就是比利时队" not in payload_text
    assert "teams.current_rosters" in payload_text
    assert "不得点名具体球员/教练作为当前事实" in payload_text


def test_finalize_answer_removes_citations_without_sources_and_invalid_ids():
    assert _finalize_answer("场地已确认。[1] 但天气待确认。[2]", []) == "场地已确认。 但天气待确认。"
    assert _finalize_answer("结论一。[1] 结论二。[9]", [{"citationId": 1}]) == "结论一。[1] 结论二。"


def test_finalize_answer_removes_internal_terms():
    answer = _finalize_answer("由于 adopted_sources 为空，我不会引用。\n\n场地已确认。", [])

    assert "adopted_sources" not in answer
    assert "场地已确认" in answer


def test_quality_gate_scores_citations_and_forbidden_content():
    answer = (
        "### 一句话判断\n巴西 vs 挪威会是一场强弱对冲明显的比赛。[1]\n"
        "### 历史/状态\n巴西整体实力更强。[1]\n"
        "### 关键球员与阵容\n阵容仍需赛前确认。[2]\n"
        "### 战术对位\n挪威会依赖高点和反击。[2]\n"
        "### 环境因素\n天气需要临场确认。\n"
        "### 胜负手\n巴西边路压制是关键。\n"
        "### 风险不确定性\n如果挪威定位球效率高，比赛会更接近。"
    )
    sources = [
        {"citationId": 1, "relevanceScore": 0.9},
        {"citationId": 2, "relevanceScore": 0.8},
        {"citationId": 3, "relevanceScore": 0.7},
        {"citationId": 4, "relevanceScore": 0.7},
    ]

    report = evaluate_research_answer(
        answer=answer,
        sources=sources,
        context={"match": {"home_team_raw": "巴西", "away_team_raw": "挪威"}},
        min_total=20,
    )

    assert report.passed
    assert report.dimensions["citation_coverage"] >= 4


def test_research_stream_local_only_emits_quality_and_done():
    events = list(stream_research_answer(_request()))
    text = "".join(events)

    assert "event: query_plan" in text
    assert "event: evidence_ready" in text
    assert "event: quality_check" in text
    assert "event: done" in text
    assert "run_id" not in text


def test_research_stream_local_only_respects_facts_only_contract():
    req = _request(
        message="美国 vs 比利时什么时候踢？场地到底是不是 Lumen Field / Seattle Stadium？只说确定事实。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        toolIntent="general",
    )
    text = "".join(stream_research_answer(req))

    assert "确定事实" in text
    assert "Lumen Field" in text
    assert "联网状态" not in text


def test_research_stream_local_only_prioritizes_pitch_boundary_over_facts_only():
    req = _request(
        message="Lumen Field 是人工草皮吗？请只说确定和待确认。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452515",
        },
        toolIntent="general",
    )
    text = "".join(stream_research_answer(req))

    assert "确定事实" in text
    assert "待确认" in text
    assert "本地结构化数据没有确认" in text
    assert "不能仅凭场馆常识断言" in text


def test_research_stream_local_only_explains_bracket_placeholders():
    req = _request(
        message="决赛 W101 vs W102 是哪两支球队？不要编。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537",
        },
        toolIntent="general",
    )
    text = "".join(stream_research_answer(req))

    assert "淘汰赛路径占位" in text
    assert "不是已确定球队" in text
    assert "W101" in text
    assert "W102" in text
    assert "美国队" not in text
    assert "比利时队" not in text


def test_research_stream_required_search_reports_config_error(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    req = _request(searchMode="required")
    events = list(stream_research_answer(req))
    payloads = [event for event in events if "event: error" in event]

    assert payloads
    assert "联网研究不可用" in payloads[0]


def test_research_stream_firecrawl_402_degrades_without_stalling(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")

    def fail_search(*args, **kwargs):
        raise FirecrawlCallError(
            "Firecrawl credits are exhausted or the account requires billing.",
            status_code=402,
        )

    monkeypatch.setattr("wcpa.agents.research_engine.search_web", fail_search)
    req = _request(searchMode="required")

    events = list(stream_research_answer(req))
    text = "".join(events)

    assert "event: search_warning" in text
    assert "Firecrawl 额度已用尽" in text
    assert "event: done" in text


def test_sse_payloads_are_valid_json():
    for event in stream_research_answer(_request()):
        data_line = next(line for line in event.splitlines() if line.startswith("data:"))
        json.loads(data_line.removeprefix("data:").strip())


def test_followup_web_search_keeps_historical_head_to_head_intent():
    req = AgentResearchRequest.model_validate(
        {
            "message": "本地没有就请你联网搜索查找一下这都不会吗？",
            "context": {
                "currentPage": "worldcup-dashboard",
                "data": {"home_team_raw": "瑞士", "away_team_raw": "哥伦比亚"},
            },
            "history": [
                {
                    "role": "user",
                    "content": "请你查一下历史数据看看历史上瑞士和哥伦比亚交手的结果分别是什么",
                },
                {"role": "assistant", "content": "本地结构化数据中没有历史交手记录。"},
                {"role": "user", "content": "我说的是历史上，不是局限于2026世界杯"},
            ],
            "llmConfig": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "apiKey": "sk-test",
                "searchEnabled": False,
            },
            "searchMode": "local_only",
            "toolIntent": "general",
        }
    )
    plan = build_research_plan(
        req,
        {"match": {"home_team_raw": "瑞士", "away_team_raw": "哥伦比亚"}},
        {"enabled": False},
    )

    assert plan.intent == "head_to_head_history"
    assert any("Switzerland Colombia head to head" in query for query in plan.queries)
