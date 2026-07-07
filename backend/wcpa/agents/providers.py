"""OpenAI-compatible provider adapter for interactive chat."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator

import httpx

from wcpa.schemas.agent_chat import AgentProviderCapability, AgentProviderModel


class ProviderConfigError(ValueError):
    """Raised when a requested model provider is not allowed."""


class ProviderCallError(RuntimeError):
    """Raised when an upstream model call fails."""


@dataclass(frozen=True)
class ProviderModel:
    id: str
    label: str
    mode: str


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    base_url: str
    models: tuple[ProviderModel, ...]
    custom_base_url: bool = False


PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        models=(
            ProviderModel("deepseek-chat", "DeepSeek Chat", "fast"),
            ProviderModel("deepseek-reasoner", "DeepSeek Reasoner", "analysis"),
        ),
    ),
    "qwen": ProviderSpec(
        id="qwen",
        label="通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=(
            ProviderModel("qwen-turbo", "Qwen Turbo", "fast"),
            ProviderModel("qwen-plus", "Qwen Plus", "balanced"),
            ProviderModel("qwen-max", "Qwen Max", "analysis"),
        ),
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=(
            ProviderModel("openai/gpt-4o-mini", "GPT-4o mini", "fast"),
            ProviderModel("anthropic/claude-3.5-sonnet", "Claude 3.5 Sonnet", "analysis"),
        ),
    ),
    "custom": ProviderSpec(
        id="custom",
        label="自定义 OpenAI-compatible 接口",
        base_url="",
        models=(),
        custom_base_url=True,
    ),
}


def provider_capabilities() -> list[AgentProviderCapability]:
    return [
        AgentProviderCapability(
            id=provider.id,
            label=provider.label,
            base_url=None if provider.custom_base_url else provider.base_url,
            custom_base_url=provider.custom_base_url,
            models=[
                AgentProviderModel(id=model.id, label=model.label, mode=model.mode)
                for model in provider.models
            ],
        )
        for provider in PROVIDERS.values()
    ]


@dataclass(frozen=True)
class ResolvedProvider:
    provider_id: str
    label: str
    base_url: str
    model: str

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def resolve_provider(provider_id: str, model: str, base_url: str | None = None) -> ResolvedProvider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderConfigError("不支持的模型服务商。")

    if provider.custom_base_url:
        if not base_url or not base_url.startswith(("https://", "http://")):
            raise ProviderConfigError("自定义服务商需要填写有效的 Base URL。")
        if not model.strip():
            raise ProviderConfigError("自定义服务商需要填写模型名。")
        return ResolvedProvider(provider.id, provider.label, base_url, model.strip())

    allowed = {item.id for item in provider.models}
    if model not in allowed:
        raise ProviderConfigError("该服务商不支持所选模型。")
    return ResolvedProvider(provider.id, provider.label, provider.base_url, model)


def stream_chat_completion(
    provider: ResolvedProvider,
    api_key: str,
    messages: list[dict[str, str]],
    temperature: float = 0.35,
    timeout: float = 90.0,
) -> Iterator[str]:
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", provider.chat_url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    raise ProviderCallError(_safe_upstream_error(response))
                for raw_line in response.iter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    token = _extract_stream_token(data)
                    if token:
                        yield token
    except ProviderCallError:
        raise
    except httpx.TimeoutException as exc:
        raise ProviderCallError("模型服务响应超时。") from exc
    except httpx.HTTPError as exc:
        raise ProviderCallError("模型服务连接失败。") from exc


def test_chat_completion(provider: ResolvedProvider, api_key: str, timeout: float = 30.0) -> None:
    payload = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": "You are a connectivity test."},
            {"role": "user", "content": "Reply with OK."},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(provider.chat_url, headers=headers, json=payload, timeout=timeout)
        if response.status_code >= 400:
            raise ProviderCallError(_safe_upstream_error(response))
        response.json()
    except ProviderCallError:
        raise
    except httpx.TimeoutException as exc:
        raise ProviderCallError("模型服务响应超时。") from exc
    except httpx.HTTPError as exc:
        raise ProviderCallError("模型服务连接失败。") from exc
    except ValueError as exc:
        raise ProviderCallError("模型服务返回了无法解析的响应。") from exc


def _extract_stream_token(data: str) -> str:
    try:
        payload = json.loads(data)
    except ValueError:
        return ""
    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    if isinstance(delta.get("content"), str):
        return delta["content"]
    message = choices[0].get("message") or {}
    return message.get("content") if isinstance(message.get("content"), str) else ""


def _safe_upstream_error(response: httpx.Response) -> str:
    try:
        response.read()
    except httpx.HTTPError:
        return f"模型服务返回错误：HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return f"模型服务返回错误：HTTP {response.status_code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        if message:
            return f"模型服务返回错误：{message}"
    return f"模型服务返回错误：HTTP {response.status_code}"
