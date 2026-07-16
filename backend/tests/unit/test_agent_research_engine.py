"""ResearchAnswerEngine tests."""

from __future__ import annotations

import json

from wcpa.agents.agent_context_builder import build_match_context
from wcpa.agents.firecrawl_client import FirecrawlCallError
from wcpa.agents.research_engine import (
    EvidenceCollection,
    _collect_web_evidence,
    _deterministic_research_answer,
    _finalize_answer,
    _quality_min_total,
    _research_messages,
    _looks_like_prediction_report,
    _supported_claims,
    build_research_plan,
    stream_research_answer,
)
from wcpa.agents.search_policy import SearchBudget
from wcpa.agents.search_service import SearchServiceResult
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


def test_completed_match_uses_post_match_queries_and_score():
    req = _request(
        message="请详细复盘这场比赛。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "eng-arg",
            "data": {"status": "complete"},
        },
        toolIntent="post_match_report",
    )
    context = {
        "match": {
            "home_team_raw": "英格兰",
            "away_team_raw": "阿根廷",
            "home_score": 1,
            "away_score": 2,
            "status": "complete",
            "stage": "SF",
        }
    }

    plan = build_research_plan(req, context, {"enabled": False})

    assert plan.intent == "post_match_report"
    assert "England 1-2 Argentina" in plan.queries[0]
    assert "match report" in plan.queries[0]
    assert not any("injuries" in query or "preview" in query for query in plan.queries)
    assert plan.output_contract["forbid_speculative_recap"] is True


def test_post_match_button_prompt_cannot_trigger_prediction_branch():
    prompt = (
        "请联网检索权威赛后战报，详细复盘这场比赛：按时间顺序说明进球和关键事件，"
        "分析双方攻守变化、换人调整与胜负手，并给每组赛况事实标注来源。"
        "不要根据比分或球队印象推测比赛过程。"
    )
    req = _request(
        message=prompt,
        context={"currentPage": "worldcup-dashboard", "currentMatchId": "eng-arg", "data": {"status": "complete"}},
        toolIntent="post_match_report",
    )
    context = {
        "match": {
            "home_team_raw": "英格兰",
            "away_team_raw": "阿根廷",
            "home_score": 1,
            "away_score": 2,
            "status": "complete",
            "stage": "SF",
        }
    }

    plan = build_research_plan(req, context, {"enabled": False})

    assert plan.intent == "post_match_report"
    assert "prediction_required" not in plan.output_contract


def test_web_evidence_keeps_successful_results_when_later_query_fails(monkeypatch):
    req = _request(toolIntent="post_match_report")
    context = {
        "match": {
            "home_team_raw": "英格兰",
            "away_team_raw": "阿根廷",
            "home_score": 1,
            "away_score": 2,
            "status": "complete",
            "stage": "SF",
        }
    }
    plan = build_research_plan(req, context, {"enabled": False})
    calls = 0

    def partial_search(query, limit=None, budget=None):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise FirecrawlCallError("second query timed out")
        source = QualifiedSource(
            title="Argentina beat England 2-1 in World Cup semifinal match report",
            url="https://apnews.com/article/england-argentina-world-cup-semifinal",
            domain="apnews.com",
            snippet="Argentina defeated England 2-1 after two goals in the semifinal.",
            published_at="2026-07-15",
            source_quality_score=1.0,
            raw={},
            source_type="wire",
        )
        video = QualifiedSource(
            title="England vs Argentina semifinal preview and prediction",
            url="https://youtube.com/watch?v=preview",
            domain="youtube.com",
            snippet="A pre-match prediction video.",
            published_at="2026-07-14",
            source_quality_score=0.55,
            raw={},
            source_type="video",
        )
        return SearchServiceResult(query=query, search_id="search-1", sources=[source, video], raw={})

    monkeypatch.setattr("wcpa.agents.research_engine.search_web", partial_search)
    collection = _collect_web_evidence(
        plan,
        SearchBudget(2, 4, 0, 3, 12000, 0),
    )

    assert len(collection.sources) == 1
    assert collection.sources[0]["domain"] == "apnews.com"
    assert all(source["domain"] != "youtube.com" for source in collection.sources)
    assert collection.errors
    assert any(item.get("sourceType") == "search_error" for item in collection.filtered)


def test_post_match_prompt_separates_local_score_from_event_evidence():
    req = _request(message="具体说说这场比赛怎么踢的", toolIntent="post_match_report")
    context = {
        "match": {
            "home_team_raw": "英格兰",
            "away_team_raw": "阿根廷",
            "home_score": 1,
            "away_score": 2,
            "status": "complete",
        },
        "prediction": {
            "home_win_probability": 0.321,
            "draw_probability": 0.229,
            "away_win_probability": 0.449,
        },
    }
    plan = build_research_plan(req, context, {"enabled": False})

    messages = _research_messages(req, context, plan, [], [], "")
    combined = "\n".join(message["content"] for message in messages)

    assert "does not support event chronology or tactics" in combined
    assert "不得把推测写成比赛过程" in combined
    assert "home_win_probability" not in messages[-1]["content"]


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


def test_tournament_prediction_refuses_to_invent_forecast_without_bound_artifact():
    req = _request(
        message="那就请你预测世界杯冠军是谁",
        context={
            "currentPage": "worldcup-dashboard",
            "activeTab": "bracket",
            "data": {"scope": "page", "tab": "bracket", "totalMatches": 31, "placeholderMatches": 2},
        },
        searchMode="local_only",
        toolIntent="general",
    )

    text = "".join(stream_research_answer(req))

    assert "当前没有有效冠军预测" in text
    assert "旧阶段结果" in text
    assert "均匀概率" in text
    assert "巴西：约" not in text


def test_tournament_prediction_replaces_thin_refusal_with_truthful_unavailable_state():
    req = _request(
        message="请问你对于本届世界杯冠军的更加看好谁夺冠呢",
        context={
            "currentPage": "worldcup-dashboard",
            "activeTab": "bracket",
            "data": {"scope": "page", "tab": "bracket", "totalMatches": 31, "placeholderMatches": 2},
        },
        toolIntent="general",
    )
    context = {"scope": "page", "page": req.context.data, "environment": {}, "bracket": {}, "team_history": {}}
    plan = build_research_plan(req, context, {"enabled": False})

    answer = _finalize_answer(
        "目前没有足够数据支持我给出一个明确的看好对象。",
        [{"citationId": 1, "relevanceScore": 0.8}, {"citationId": 2, "relevanceScore": 0.8}],
        request=req,
        context=context,
        plan=plan,
    )

    assert "当前没有有效冠军预测" in answer
    assert "默认球队强度" in answer
    assert "巴西" not in answer
    assert "没有足够数据支持我给出一个明确的看好对象" not in answer


def test_page_context_does_not_fall_back_to_default_match():
    req = _request(
        message="请分析当前赛程表页面。",
        context={
            "currentPage": "worldcup-dashboard",
            "activeTab": "bracket",
            "data": {
                "scope": "page",
                "tab": "bracket",
                "totalMatches": 31,
                "placeholderMatches": 9,
            },
        },
        toolIntent="general",
    )

    text = "".join(stream_research_answer(req))

    assert "Brazil vs Norway" not in text
    assert "当前页面概览" in text
    assert "31" in text


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


def test_post_match_quality_gate_rejects_prediction_report():
    answer = (
        "### 结论倾向\n阿根廷胜，置信度65%。\n"
        "### 常规时间概率\n英格兰32.1%，平局22.9%，阿根廷44.9%。\n"
        "### 模型推断\nstrength: 权重53%。neutral_prior: 权重18%。\n"
        "### 来源与边界\n本次采用8条联网来源。[1][2][3][4]"
    )
    sources = [
        {"citationId": index, "relevanceScore": 0.9}
        for index in range(1, 5)
    ]

    report = evaluate_research_answer(
        answer=answer,
        sources=sources,
        context={"match": {"home_team_raw": "英格兰", "away_team_raw": "阿根廷"}},
        min_total=20,
        post_match_required=True,
    )

    assert not report.passed
    assert any("错误输出了赛前预测" in issue for issue in report.issues)
    assert _looks_like_prediction_report(answer)


def test_post_match_model_fallback_preserves_retrieved_evidence():
    answer = _deterministic_research_answer(
        {
            "intent": "post_match_report",
            "match": {
                "home_team_raw": "英格兰",
                "away_team_raw": "阿根廷",
                "home_score": 1,
                "away_score": 2,
            },
        },
        [
            {
                "citationId": 1,
                "title": "England 1-2 Argentina match report",
                "snippet": "Argentina advanced after a 2-1 semifinal win.",
            }
        ],
        [],
        reason="模型连接不可用。",
    )

    assert "已取得的赛后证据摘录" in answer
    assert "England 1-2 Argentina match report" in answer
    assert "没有取得可采用的赛后战报" not in answer


def test_post_match_stream_repairs_prediction_shaped_model_answer(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")
    monkeypatch.setattr(
        "wcpa.agents.research_engine.build_match_context",
        lambda _match_id: {
            "match": {
                "home_team_raw": "英格兰",
                "away_team_raw": "阿根廷",
                "home_score": 1,
                "away_score": 2,
                "status": "complete",
                "stage": "SF",
            },
            "prediction": {"home_win_probability": 0.321, "away_win_probability": 0.449},
            "bracket": {},
            "environment": {},
            "team_history": {},
        },
    )
    sources = [
        {
            "citationId": index,
            "title": f"Post-match report {index}",
            "url": f"https://example{index}.com/report",
            "domain": f"example{index}.com",
            "snippet": "England and Argentina semifinal match report with goals and substitutions.",
            "source": "firecrawl",
            "relevanceScore": 0.9,
            "sourceQualityScore": 0.9,
            "sourceType": "media",
            "excerpt": "England and Argentina match chronology, goals, saves and substitutions.",
            "supportedClaims": [],
        }
        for index in range(1, 5)
    ]
    monkeypatch.setattr(
        "wcpa.agents.research_engine._collect_web_evidence",
        lambda _plan, _budget: EvidenceCollection(sources=sources, filtered=[], errors=[]),
    )
    calls = 0

    def fake_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield (
                "### 结论倾向\n英格兰32.1%，阿根廷44.9%。\n"
                "### 常规时间概率\n平局22.9%。\n"
                "### 模型推断\nstrength: 53%，neutral_prior: 18%。"
            )
            return
        yield (
            "### 比赛结论\n阿根廷以2-1击败英格兰，以下只整理来源明确支持的赛况。[1]\n"
            "### 进球与关键事件\n报道记录了双方进球、扑救和关键事件，具体时间线逐项依据赛后来源整理。[1][2]\n"
            "### 比赛如何展开\n上半场与下半场的比赛走势、双方攻守转换和场面变化均以报道正文为准，"
            "不从最终比分反推控球或压迫效果。[2][3]\n"
            "### 双方调整与胜负手\n换人调整、阵型变化和决定性回合只采用来源已经说明的内容，"
            "未被报道支持的球员与分钟不会写入复盘。[3][4]\n"
            "### 证据边界\n四条来源共同支持比赛身份和主要赛况；如果分钟或技术统计存在冲突，"
            "应明确标记差异并等待官方比赛报告，而不是选择更戏剧化的说法。[1][2][3][4]\n"
            "这是一份赛后复盘结构校验文本，重点验证系统不会再把胜平负概率、模型权重和赛前倾向当作比赛过程。"
        )

    monkeypatch.setattr("wcpa.agents.research_engine.stream_chat_completion", fake_stream)
    req = _request(
        message="请联网详细复盘已经结束的比赛，不要根据比分推测过程。",
        context={"currentPage": "worldcup-dashboard", "currentMatchId": "eng-arg", "data": {"status": "complete"}},
        llmConfig={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "apiKey": "sk-test",
            "searchEnabled": True,
        },
        searchMode="required",
        toolIntent="post_match_report",
    )

    text = "".join(stream_research_answer(req))

    assert calls == 2
    assert '"answer": "### 比赛结论' in text
    assert '"predictionQuality": null' in text


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
    assert "路径情景推演" in answer
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


def test_research_stream_local_only_explains_bracket_placeholders(monkeypatch):
    req = _request(
        message="决赛 W101 vs W102 是哪两支球队？不要编。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537",
        },
        toolIntent="general",
    )
    monkeypatch.setattr(
        "wcpa.agents.research_engine.build_match_context",
        lambda _match_id: {
            "match": {"home_team_raw": "W101", "away_team_raw": "W102", "stage": "Final", "status": "scheduled"},
            "bracket": {"has_placeholders": True},
            "environment": {},
            "team_history": {},
        },
    )
    text = "".join(stream_research_answer(req))

    assert "淘汰赛路径占位" in text
    assert "不是已确定球队" in text
    assert "TBD" in text or "尚未确定" in text
    assert "美国队" not in text
    assert "比利时队" not in text


def test_research_stream_placeholder_prediction_uses_scenario_not_identity_shortcut(monkeypatch):
    req = _request(
        message="请预测 W101 vs W102 的决赛走势，做路径情景推演。",
        context={
            "currentPage": "worldcup-dashboard",
            "currentMatchId": "SportRadar_Soccer_InternationalWorldCup_2026_Game_53452537",
        },
        toolIntent="match_analysis",
    )
    monkeypatch.setattr(
        "wcpa.agents.research_engine.build_match_context",
        lambda _match_id: {
            "match": {"home_team_raw": "W101", "away_team_raw": "W102", "stage": "Final", "status": "scheduled"},
            "bracket": {"has_placeholders": True},
            "environment": {},
            "team_history": {},
        },
    )
    text = "".join(stream_research_answer(req))

    assert "路径情景推演" in text
    assert "淘汰赛路径占位说明" not in text
    assert "不是已确定球队" in text


def test_research_stream_required_search_reports_config_error(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    req = _request(searchMode="required")
    events = list(stream_research_answer(req))
    payloads = [event for event in events if "event: search_warning" in event]

    assert payloads
    assert "联网研究不可用" in payloads[0]
    assert any('"status": "evidence_unavailable"' in event for event in events)


def test_post_match_without_web_evidence_refuses_to_invent_recap(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")
    monkeypatch.setattr(
        "wcpa.agents.research_engine.build_match_context",
        lambda _match_id: {
            "match": {
                "home_team_raw": "英格兰",
                "away_team_raw": "阿根廷",
                "home_score": 1,
                "away_score": 2,
                "winner_team_raw": "阿根廷",
                "stage": "SF",
                "status": "complete",
            },
            "bracket": {},
            "environment": {},
            "team_history": {},
        },
    )
    monkeypatch.setattr(
        "wcpa.agents.research_engine.search_web",
        lambda *args, **kwargs: (_ for _ in ()).throw(FirecrawlCallError("timed out")),
    )
    req = _request(
        message="请联网详细复盘这场比赛。",
        context={"currentPage": "worldcup-dashboard", "currentMatchId": "eng-arg", "data": {"status": "complete"}},
        searchMode="required",
        toolIntent="post_match_report",
    )

    events = list(stream_research_answer(req))
    text = "".join(events)

    assert "不会根据比分或球队印象编造比赛是怎么踢的" in text
    assert '"status": "evidence_unavailable"' in text


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
