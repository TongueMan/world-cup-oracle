"""Interactive Agent chat API tests."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from wcpa.api.server import app
from wcpa.agents.providers import ProviderCallError, ResolvedProvider, _safe_upstream_error


def _chat_body(search_enabled: bool = False) -> dict:
    return {
        "message": "请分析一下巴西队最近的世界杯前景",
        "context": {"currentPage": "dashboard", "activeTab": "matches"},
        "history": [],
        "llmConfig": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "apiKey": "sk-test-secret",
            "searchEnabled": search_enabled,
        },
    }


def test_capabilities_report_keyless_search_enabled_by_default(monkeypatch):
    monkeypatch.delenv("WCPA_WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("WCPA_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("WCPA_FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("WCPA_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    response = TestClient(app).get("/api/agents/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["search"]["enabled"] is True
    assert body["search"]["provider"] == "firecrawl"
    assert "Keyless" in body["search"]["message"]
    assert {item["id"] for item in body["providers"]} >= {"deepseek", "qwen", "openrouter", "custom"}


def test_chat_stream_accepts_keyless_search_by_default(monkeypatch):
    monkeypatch.delenv("WCPA_WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("WCPA_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("WCPA_FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("WCPA_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    monkeypatch.setattr(
        "wcpa.api.routes.agents.stream_research_answer",
        lambda request: iter(['event: done\ndata: {"status":"ok","answer":""}\n\n']),
    )

    response = TestClient(app).post("/api/agents/chat/stream", json=_chat_body(search_enabled=True))

    assert response.status_code == 200


def test_chat_stream_sse_event_order(monkeypatch):
    def fake_stream(
        provider: ResolvedProvider,
        api_key: str,
        messages: list[dict[str, str]],
        temperature: float = 0.35,
        timeout: float = 90.0,
    ):
        assert api_key == "sk-test-secret"
        assert provider.model == "deepseek-chat"
        yield "你好"
        yield "，世界杯。"

    monkeypatch.setattr("wcpa.agents.research_engine.stream_chat_completion", fake_stream)

    response = TestClient(app).post("/api/agents/chat/stream", json=_chat_body())

    assert response.status_code == 200
    text = response.text
    assert text.index("event: metadata") < text.index("event: token") < text.index("event: done")
    assert '"content": "你好' in text
    assert '"answer": "你好，世界杯。"' in text


def test_chat_stream_error_does_not_echo_api_key(monkeypatch):
    def fake_stream(*args, **kwargs):
        raise ProviderCallError("模型服务返回错误：HTTP 401")
        yield ""

    monkeypatch.setattr("wcpa.agents.research_engine.stream_chat_completion", fake_stream)

    response = TestClient(app).post("/api/agents/chat/stream", json=_chat_body())

    assert response.status_code == 200
    assert "模型生成未完成：模型服务返回错误：HTTP 401" in response.text
    assert "sk-test-secret" not in response.text


def test_provider_test_returns_sanitized_failure(monkeypatch):
    def fake_test(*args, **kwargs):
        raise ProviderCallError("模型服务返回错误：HTTP 401")

    monkeypatch.setattr("wcpa.agents.chat.test_chat_completion", fake_test)

    response = TestClient(app).post(
        "/api/agents/providers/test",
        json={"llmConfig": _chat_body()["llmConfig"]},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "模型服务返回错误：HTTP 401"
    assert "sk-test-secret" not in json.dumps(response.json(), ensure_ascii=False)


def test_streaming_upstream_error_body_is_read_before_json_parse():
    response = httpx.Response(
        401,
        stream=httpx.ByteStream(b'{"error":{"message":"invalid api key"}}'),
    )

    assert _safe_upstream_error(response) == "模型服务返回错误：invalid api key"
