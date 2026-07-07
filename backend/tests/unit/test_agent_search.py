"""Agent Firecrawl-backed search and evidence policy tests."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from wcpa.agents.agent_answer_service import generate_agent_answer
from wcpa.agents.agent_search_planner import build_search_plan
from wcpa.agents.match_analysis_inputs import build_match_data_coverage
from wcpa.agents.match_resolution import extract_team_ids
from wcpa.agents.match_tool_service import run_match_tool
from wcpa.agents.source_quality import QualifiedSource, score_match_relevance
from wcpa.agents.search import search_capability, search_web
from wcpa.agents.search_policy import evaluate_search_authorization, load_search_deployment_config
from wcpa.schemas.agent_chat import AgentLLMConfig


def _response(url: str, payload: dict) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(200, json=payload, request=request)


def _clear_search_env(monkeypatch):
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "")
    monkeypatch.setenv("SEARCH_PROVIDER", "")


def test_search_capability_requires_firecrawl_deployment(monkeypatch):
    _clear_search_env(monkeypatch)

    capability = search_capability()

    assert capability.enabled is False
    assert capability.provider is None


def test_firecrawl_search_adapter_uses_configured_key_when_available(monkeypatch):
    _clear_search_env(monkeypatch)
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")
    monkeypatch.setenv("WCPA_FIRECRAWL_API_KEY", "fc-test")

    def fake_post(url: str, headers: dict, json: dict, timeout: int):
        assert url == "https://api.firecrawl.dev/v2/search"
        assert headers["Authorization"] == "Bearer fc-test"
        assert json["query"] == "brazil france news"
        return _response(
            url,
            {
                "success": True,
                "data": [
                    {
                        "title": "Brazil France team news",
                        "url": "https://www.bbc.com/sport/football/example",
                        "snippet": "lineup notes",
                    }
                ],
            },
        )

    monkeypatch.setattr("wcpa.agents.firecrawl_client.httpx.post", fake_post)

    rows = search_web("brazil france news", limit=3)

    assert rows[0].source == "firecrawl"
    assert rows[0].url == "https://www.bbc.com/sport/football/example"


def test_firecrawl_keyless_search_adapter(monkeypatch):
    _clear_search_env(monkeypatch)
    monkeypatch.delenv("WCPA_FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")

    capability = search_capability()
    assert capability.enabled is True
    assert "Keyless" in capability.message

    def fake_post(url: str, headers: dict, json: dict, timeout: int):
        assert url == "https://api.firecrawl.dev/v2/search"
        assert "Authorization" not in headers
        return _response(
            url,
            {
                "success": True,
                "data": [
                    {
                        "title": "Firecrawl keyless works",
                        "url": "https://www.firecrawl.dev/blog/firecrawl-keyless-launch",
                        "snippet": "No API key required for a trial request.",
                    }
                ],
            },
        )

    monkeypatch.setattr("wcpa.agents.firecrawl_client.httpx.post", fake_post)

    rows = search_web("firecrawl keyless", limit=1)

    assert rows[0].source == "firecrawl"


def test_firecrawl_is_enabled_by_default_when_not_explicitly_disabled(monkeypatch):
    monkeypatch.delenv("WCPA_WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("WCPA_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)

    capability = search_capability()

    assert capability.enabled is True
    assert capability.provider == "firecrawl"
    assert "Keyless" in capability.message


def test_search_authorization_requires_request_opt_in(monkeypatch):
    _clear_search_env(monkeypatch)
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")

    auth = evaluate_search_authorization("analyze", request_search_enabled=False)

    assert auth.deployment_search_enabled is True
    assert auth.can_search is False
    assert "未勾选" in auth.message


def test_search_authorization_allows_firecrawl_keyless(monkeypatch):
    _clear_search_env(monkeypatch)
    monkeypatch.setenv("WCPA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WCPA_SEARCH_PROVIDER", "firecrawl")

    auth = evaluate_search_authorization("analyze", request_search_enabled=True)

    assert auth.deployment_search_enabled is True
    assert auth.can_search is True
    assert "Keyless" in auth.message


def test_search_plan_is_bounded(monkeypatch):
    monkeypatch.setenv("WCPA_FIRECRAWL_MAX_QUERIES_PER_REQUEST", "1")
    budget = load_search_deployment_config().budget
    context = {"match": {"home_team_raw": "巴西", "away_team_raw": "法国", "stage": "Final"}}
    coverage = build_match_data_coverage(context)

    plan = build_search_plan("report", context, coverage, budget)

    assert len(plan.queries) == 1
    assert plan.intent == "pre_match_report"


def test_completed_match_analysis_prioritizes_match_report_queries(monkeypatch):
    monkeypatch.setenv("WCPA_FIRECRAWL_MAX_QUERIES_PER_REQUEST", "3")
    budget = load_search_deployment_config().budget
    context = {
        "match": {
            "home_team_raw": "巴拉圭",
            "away_team_raw": "法国",
            "stage": "16 强赛",
            "status": "complete",
        }
    }
    coverage = build_match_data_coverage(context)

    plan = build_search_plan(
        "analyze",
        context,
        coverage,
        budget,
        "请分析这场比赛，补充进球过程和战报",
    )

    assert len(plan.queries) == 3
    assert "Paraguay vs France" in plan.queries[0]
    assert "match report" in plan.queries[0]
    assert "goals" in plan.queries[0]
    assert "match stats" in plan.queries[2]


def test_analyze_without_search_opt_in_does_not_call_firecrawl(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Firecrawl should not be called when request search is disabled")

    monkeypatch.setattr("wcpa.agents.search_service.search_web", fail_if_called)
    monkeypatch.setattr(
        "wcpa.agents.match_tool_service.build_match_context",
        lambda match_id: {
            "match": {
                "match_id": match_id,
                "home_team_raw": "巴西",
                "away_team_raw": "法国",
                "stage": "Final",
                "status": "complete",
                "home_score": 1,
                "away_score": 0,
            },
            "environment": {},
        },
    )
    request_config = AgentLLMConfig.model_validate(
        {"provider": "deepseek", "model": "deepseek-chat", "apiKey": "", "searchEnabled": False}
    )

    result = run_match_tool("m1", "analyze", request_config)

    assert result.used_search is False
    assert result.run_id is None
    assert "technical_stats" in result.missing_local_fields


def test_question_team_conflict_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        "wcpa.agents.match_tool_service.build_match_context",
        lambda match_id: {
            "match": {
                "match_id": match_id,
                "home_team_id": "COL",
                "away_team_id": "GHA",
                "home_team_raw": "哥伦比亚",
                "away_team_raw": "加纳",
                "stage": "R32",
            },
            "environment": {},
        },
    )
    monkeypatch.setattr(
        "wcpa.agents.match_resolution.find_matches_by_teams",
        lambda team_ids: [{"match_id": "sui-alg", "label": "瑞士 vs 阿尔及利亚"}],
    )
    config = AgentLLMConfig.model_validate(
        {"provider": "deepseek", "model": "deepseek-chat", "apiKey": "", "searchEnabled": False}
    )

    result = run_match_tool("col-gha", "analyze", config, "帮我分析瑞士和阿尔及利亚")

    assert result.status == "needs_confirmation"
    assert result.confirmation
    assert result.confirmation["requestedTeams"] == ["SUI", "ALG"]


def test_team_extraction_handles_chinese_and_english_aliases():
    assert extract_team_ids("Switzerland vs Algeria match report")[:2] == ["SUI", "ALG"]
    assert extract_team_ids("瑞士和阿尔及利亚这场比赛")[:2] == ["SUI", "ALG"]


def test_match_source_relevance_requires_both_teams():
    context = {
        "match": {
            "home_team_id": "SUI",
            "away_team_id": "ALG",
            "home_team_raw": "瑞士",
            "away_team_raw": "阿尔及利亚",
            "stage": "R32",
        }
    }
    good = QualifiedSource(
        title="Switzerland 2-0 Algeria FIFA World Cup match report",
        url="https://www.fifa.com/example",
        domain="fifa.com",
        snippet="World Cup report",
        published_at=None,
        source_quality_score=0.95,
        raw={},
        source_type="official",
    )
    weak = QualifiedSource(
        title="Ghana scores and highlights",
        url="https://www.espn.com/example",
        domain="espn.com",
        snippet="Ghana news",
        published_at=None,
        source_quality_score=0.95,
        raw={},
    )

    assert score_match_relevance(good, context)[0] >= 0.7
    assert score_match_relevance(weak, context)[0] < 0.7


def test_environment_source_relevance_accepts_venue_without_team_names():
    context = {
        "match": {
            "home_team_id": "USA",
            "away_team_id": "BEL",
            "home_team_raw": "美国",
            "away_team_raw": "比利时",
            "stage": "R16",
        },
        "environment": {
            "venue": {
                "venue_name": "Lumen Field",
                "tournament_name": "Seattle Stadium",
                "host_city": "Seattle",
                "aliases": ["Seattle Stadium", "Lumen Field"],
            }
        },
        "intent": "weather_environment",
    }
    venue_source = QualifiedSource(
        title="FIFA World Cup 2026 stadium pitch plans for Lumen Field",
        url="https://www.fifa.com/example",
        domain="fifa.com",
        snippet="Seattle Stadium grass pitch and venue conditions",
        published_at=None,
        source_quality_score=0.95,
        raw={},
        source_type="official",
    )

    score, reason = score_match_relevance(venue_source, context)

    assert score >= 0.55
    assert "场馆" in reason or "草皮" in reason


def test_agent_answer_serializes_datetime_context(monkeypatch):
    context = {
        "match": {
            "match_id": "m1",
            "home_team_raw": "巴拉圭",
            "away_team_raw": "法国",
            "stage": "16 强赛",
            "status": "complete",
            "kickoff_at": datetime(2026, 7, 5, 5, 0, tzinfo=timezone.utc),
        },
        "environment": {
            "fetched_at": datetime(2026, 7, 5, 6, 0, tzinfo=timezone.utc),
        },
    }
    config = AgentLLMConfig.model_validate(
        {"provider": "deepseek", "model": "deepseek-chat", "apiKey": "sk-test", "searchEnabled": True}
    )
    captured: dict[str, list[dict[str, str]]] = {}

    def fake_stream(provider, api_key, messages):
        captured["messages"] = messages
        return iter(["ok"])

    monkeypatch.setattr("wcpa.agents.agent_answer_service.stream_chat_completion", fake_stream)

    answer = generate_agent_answer(
        tool_name="analyze",
        context=context,
        coverage=build_match_data_coverage(context),
        sources=[],
        used_search=False,
        search_error="",
        llm_config=config,
    )

    assert answer == "ok"
    assert "2026" in captured["messages"][1]["content"]
