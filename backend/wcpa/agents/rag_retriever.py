"""Lightweight RAG retrieval with pgvector-ready persistence hooks.

The first production path is deliberately tolerant: if PostgreSQL, pgvector, or
an embedding provider is unavailable, retrieval falls back to local structured
context and keyword snippets instead of blocking the user-facing answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from wcpa.agents.embedding_service import EmbeddingCallError, EmbeddingConfigError, embed_text, load_embedding_config, vector_literal
from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.shared.env import env_bool, env_str


@dataclass(frozen=True)
class RagChunk:
    title: str
    content: str
    source_url: str = ""
    source: str = "local"
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RagStatus:
    enabled: bool
    vector_backend: str
    vector_available: bool
    message: str


def rag_status(repository: PostgresRepository | None = None) -> RagStatus:
    enabled = env_bool("WCPA_RAG_ENABLED", False)
    backend = env_str("WCPA_RAG_VECTOR_BACKEND", "pgvector") or "pgvector"
    if not enabled:
        return RagStatus(False, backend, False, "语义检索未启用，使用结构化数据和关键词召回。")
    repo = repository or PostgresRepository()
    if not repo.enabled:
        return RagStatus(True, backend, False, "RAG 已启用，但 PostgreSQL 不可用。")
    if backend != "pgvector":
        return RagStatus(True, backend, False, "当前仅支持 pgvector 后端。")
    return RagStatus(True, backend, True, "RAG 已启用；pgvector 表将按需初始化。")


class RagRetriever:
    def __init__(self, repository: PostgresRepository | None = None):
        self.repository = repository or PostgresRepository()
        self.status = rag_status(self.repository)

    def retrieve(self, query: str, context: dict[str, Any], limit: int = 6) -> list[RagChunk]:
        chunks = self._local_context_chunks(context)
        chunks.extend(self._keyword_chunks(query, limit=limit))
        return chunks[:limit]

    def save_web_chunks(self, sources: list[dict[str, Any]]) -> None:
        if not self.repository.enabled:
            return
        try:
            self._ensure_tables()
            conn = self.repository._connect()
        except Exception:
            return
        with conn:
            with conn.cursor() as cur:
                for source in sources:
                    content = str(source.get("excerpt") or source.get("snippet") or "").strip()
                    if not content:
                        continue
                    cur.execute(
                        """
                        INSERT INTO knowledge_chunks
                          (source, record_type, title, content, metadata, source_url, fetched_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                        RETURNING id
                        """,
                        (
                            "agent_web",
                            "web_evidence",
                            source.get("title", ""),
                            content[:4000],
                            _json_metadata(source),
                            source.get("url", ""),
                            datetime.now(timezone.utc),
                        ),
                    )
                    row = cur.fetchone()
                    chunk_id = row[0] if row else None
                    if chunk_id:
                        self._try_save_embedding(cur, int(chunk_id), content)
            conn.commit()

    def _try_save_embedding(self, cur: Any, chunk_id: int, content: str) -> None:
        config = load_embedding_config()
        if not config.enabled:
            return
        try:
            vector = embed_text(content, config)
            cur.execute(
                """
                INSERT INTO knowledge_embeddings (chunk_id, embedding, model, embedded_at)
                VALUES (%s, %s::vector, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                  embedding = EXCLUDED.embedding,
                  model = EXCLUDED.model,
                  embedded_at = EXCLUDED.embedded_at
                """,
                (chunk_id, vector_literal(vector), config.model, datetime.now(timezone.utc)),
            )
        except (EmbeddingConfigError, EmbeddingCallError, Exception):
            return

    def _ensure_tables(self) -> None:
        if not self.repository.enabled:
            return
        conn = self.repository._connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_chunks (
                      id BIGSERIAL PRIMARY KEY,
                      source TEXT NOT NULL,
                      record_type TEXT NOT NULL,
                      title TEXT NOT NULL DEFAULT '',
                      content TEXT NOT NULL,
                      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                      source_url TEXT NOT NULL DEFAULT '',
                        fetched_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            conn.commit()
        try:
            vector_conn = self.repository._connect()
            with vector_conn:
                with vector_conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                          chunk_id BIGINT PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
                          embedding vector,
                          model TEXT NOT NULL DEFAULT '',
                          embedded_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                vector_conn.commit()
        except Exception:
            # pgvector is optional for v1; keyword retrieval remains available.
            return

    def _keyword_chunks(self, query: str, limit: int) -> list[RagChunk]:
        if not self.repository.enabled:
            return []
        try:
            self._ensure_tables()
            conn = self.repository._connect()
        except Exception:
            return []
        terms = [term for term in re.split(r"\W+", query) if len(term) >= 2][:8]
        if not terms:
            return []
        clauses = " OR ".join(["content ILIKE %s OR title ILIKE %s" for _ in terms])
        params: list[str] = []
        for term in terms:
            params.extend([f"%{term}%", f"%{term}%"])
        params.append(str(limit))
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT title, content, source_url, source, metadata
                    FROM knowledge_chunks
                    WHERE {clauses}
                    ORDER BY fetched_at DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [
            RagChunk(
                title=row[0],
                content=row[1],
                source_url=row[2],
                source=row[3],
                metadata=row[4] or {},
            )
            for row in rows
        ]

    def _local_context_chunks(self, context: dict[str, Any]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        match = context.get("match") or {}
        if match:
            home = match.get("home_team_raw") or match.get("home_team_id") or "TBD"
            away = match.get("away_team_raw") or match.get("away_team_id") or "TBD"
            score = ""
            if match.get("home_score") is not None and match.get("away_score") is not None:
                score = f"，比分 {match.get('home_score')}-{match.get('away_score')}"
            chunks.append(
                RagChunk(
                    title=f"{home} vs {away}",
                    content=(
                        f"本地赛程确认：{home} vs {away}，阶段 {match.get('stage') or '未知'}，"
                        f"状态 {match.get('status') or '未知'}{score}，"
                        f"时间 {match.get('kickoff_time') or match.get('kickoff_label') or '待定'}。"
                    ),
                    source="local_worldcup",
                    metadata={"match_id": match.get("match_id")},
                )
            )
        environment = context.get("environment") or {}
        if environment:
            chunks.append(
                RagChunk(
                    title="比赛环境",
                    content=str(environment.get("summary") or environment.get("reason") or environment),
                    source="local_environment",
                )
            )
        return chunks


def _json_metadata(source: dict[str, Any]) -> str:
    import json

    return json.dumps(
        {
            "domain": source.get("domain"),
            "sourceType": source.get("sourceType"),
            "relevanceScore": source.get("relevanceScore"),
            "citationId": source.get("citationId"),
        },
        ensure_ascii=False,
    )
