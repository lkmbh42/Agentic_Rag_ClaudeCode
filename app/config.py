"""Central configuration.

All configurable values come from the environment (see .env.example). Nothing
load-bearing is hard-coded. This module is imported by the backend and the
worker so both share one source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- core ---
    app_env: str = "dev"
    log_level: str = "INFO"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:8080"

    # --- postgres ---
    postgres_user: str = "rag"
    postgres_password: str = "rag"
    postgres_db: str = "rag"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- qdrant ---
    qdrant_host: str = "qdrant"
    qdrant_http_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection: str = "rag_chunks"

    # --- phoenix ---
    phoenix_host: str = "phoenix"
    phoenix_port: int = 6006
    phoenix_grpc_port: int = 4317
    tracing_enabled: bool = True

    # --- LLM (OpenAI-compatible: Ollama in dev, vLLM in prod) ---
    # llm_backend names the serving backend for ops/health/rollback purposes
    # (both speak the OpenAI API; no code branches on it). Rollback = flip this
    # plus llm_base_url/llm_gen_model in env — see docs/CHANGELOG.md Phase 1.
    llm_backend: Literal["ollama", "vllm"] = "ollama"
    llm_base_url: str = "http://ollama:11434/v1"
    llm_api_key: str = "not-needed-local"
    llm_gen_model: str = "qwen2.5:3b"
    llm_class_model: str = "qwen2.5:3b"
    llm_request_timeout_s: int = 120

    # --- embeddings / reranker ---
    embeddings_base_url: str = "http://embeddings:8001"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # Backend selector (mirrors the Ollama/vLLM dev/prod split):
    #   embeddings_backend: hashing (dev, in-process) | service (prod, BGE-M3 container)
    #   reranker_backend:   lexical (dev) | service (prod, cross-encoder) | none
    embeddings_backend: str = "hashing"
    reranker_backend: str = "lexical"

    # --- VLM / visual path ---
    vlm_base_url: str = "http://vlm:8002"
    visual_path: str = "degraded"  # degraded | full

    # --- auth ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7

    # --- ingestion ---
    storage_dir: str = "/data/documents"
    ingest_queue: str = "ingest:queue"
    eval_queue: str = "eval:queue"
    # Async LLM-as-judge eval. On the single-CPU dev model it competes with chat
    # for Ollama, so disable in dev; enable on the prod GPU. (The eval pipeline is
    # still fully tested.)
    eval_enabled: bool = True
    chunk_target_chars: int = 1200
    chunk_overlap_chars: int = 150

    # --- retrieval / cache ---
    retrieval_top_k: int = 20
    retrieval_top_n: int = 5
    retrieval_p95_target_ms: int = 800
    semantic_cache_collection: str = "semantic_cache"
    semantic_cache_similarity: float = 0.95
    semantic_cache_ttl_s: int = 86400

    # --- circuit breakers / quotas ---
    max_graph_iterations: int = 25
    max_retrieval_retries: int = 2
    max_generation_retries: int = 1
    # Hallucination/grounding grader. A weak model (dev 3B) gives false negatives
    # and discards good answers, so disable in dev; keep on for the prod model.
    hallucination_check_enabled: bool = True
    max_indexing_retries: int = 3
    max_request_duration_s: int = 90
    per_user_max_inflight: int = 3
    per_user_requests_per_min: int = 60
    per_user_tokens_per_min: int = 20000

    # --- derived connection strings ---
    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        # Alembic + the LangGraph checkpointer use the sync driver.
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_psycopg(self) -> str:
        # Plain libpq URL for psycopg3 (LangGraph Postgres checkpointer).
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_http_port}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so env is parsed once per process."""
    return Settings()
