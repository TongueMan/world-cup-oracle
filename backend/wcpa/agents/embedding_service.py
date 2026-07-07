"""Optional OpenAI-compatible embedding client for pgvector RAG."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from wcpa.shared.env import env_str


class EmbeddingConfigError(RuntimeError):
    """Raised when embeddings are requested but not configured."""


class EmbeddingCallError(RuntimeError):
    """Raised when the embedding provider fails."""


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    api_key: str
    base_url: str

    @property
    def enabled(self) -> bool:
        return bool(self.provider and self.model and self.api_key and self.base_url)


def load_embedding_config() -> EmbeddingConfig:
    provider = env_str("WCPA_EMBEDDING_PROVIDER", "")
    return EmbeddingConfig(
        provider=provider,
        model=env_str("WCPA_EMBEDDING_MODEL", ""),
        api_key=env_str("WCPA_EMBEDDING_API_KEY", ""),
        base_url=env_str("WCPA_EMBEDDING_BASE_URL", "") or _default_base_url(provider),
    )


def embed_text(text: str, config: EmbeddingConfig | None = None) -> list[float]:
    active = config or load_embedding_config()
    if not active.enabled:
        raise EmbeddingConfigError("Embedding provider is not configured.")
    try:
        response = httpx.post(
            f"{active.base_url.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {active.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": active.model, "input": text[:8000]},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise EmbeddingCallError("Embedding provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise EmbeddingCallError("Embedding provider request failed.") from exc
    except ValueError as exc:
        raise EmbeddingCallError("Embedding provider returned invalid JSON.") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        raise EmbeddingCallError("Embedding provider returned no embedding data.")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list):
        raise EmbeddingCallError("Embedding payload missing vector.")
    return [float(value) for value in embedding]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _default_base_url(provider: str) -> str:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "qwen":
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1"
    return ""
