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
    # Reasoning-model knob (gpt-oss and other "thinking" models exposed via the
    # OpenAI API). When non-empty, generation calls request this effort level
    # (low|medium|high) and short classification/grading calls are forced to
    # "low"; token budgets get reasoning headroom so thinking never truncates the
    # actual output. Leave EMPTY for non-reasoning backends (vLLM/Qwen) so the
    # provider-specific param is never sent.
    llm_reasoning_effort: str = ""
    # Phase 4: True ONLY when the served generation model accepts image content
    # parts (a VL model). Gates query-time image context end-to-end: the
    # assembler resolves page images and generate() attaches them. The ratified
    # ADR keeps this FALSE on the 24 GB prod host (text 7B-AWQ; zero query-time
    # VLM calls); flipping it is the documented ≥48 GB upgrade path.
    llm_multimodal: bool = False

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

    # --- object store (MinIO, Phase 2: figure crops + page renders) ---
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin-dev-only"
    minio_secure: bool = False  # internal Docker network; TLS terminates at proxy
    minio_bucket_figures: str = "figures"
    minio_bucket_pages: str = "pages"

    # --- VLM / visual path ---
    vlm_base_url: str = "http://vlm:8002"
    visual_path: str = "degraded"  # degraded | full
    # Figure captioning (Phase 2): the worker calls vlm_base_url `/caption`
    # (Qwen2.5-VL-7B). Enabled only when visual_path == "full" (prod GPU host);
    # in degraded/dev, figures keep their document captions.
    captioner_timeout_s: int = 120

    # --- visual page retrieval (Phase 2: ColQwen2 multivector, docs_pages) ---
    colqwen_base_url: str = "http://colqwen:8003"
    colqwen_timeout_s: int = 120
    docs_pages_collection: str = "docs_pages"
    page_render_max_px: int = 1024      # longest edge of the page PNG
    colqwen_dim: int = 128              # per-patch multivector dimension
    # Binary quantization on docs_pages (spec): ~32× storage cut for the
    # multivector page index. Off only for debugging.
    docs_pages_binary_quantization: bool = True

    # --- auth ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7

    # --- ingestion ---
    storage_dir: str = "/data/documents"
    # Phase 2 parser: docling (layout-aware, PDF/DOCX/PPTX/XLSX) with the
    # legacy parser as explicit fallback and for plain-text types.
    parser_backend: Literal["docling", "legacy"] = "docling"
    ocr_languages: tuple[str, ...] = ("deu", "eng")  # Rule 8: DE-dominant corpus
    # Pre-staged Docling model artifacts (Rule 2). None = library default cache
    # (dev convenience); prod compose sets /models/docling.
    docling_artifacts_path: str | None = None
    ingest_queue: str = "ingest:queue"
    ingest_dlq: str = "ingest:dlq"  # dead-letter list (Phase 2, admin-requeueable)
    eval_queue: str = "eval:queue"
    # Async LLM-as-judge eval. On the single-CPU dev model it competes with chat
    # for Ollama, so disable in dev; enable on the prod GPU. (The eval pipeline is
    # still fully tested.)
    eval_enabled: bool = True
    chunk_target_chars: int = 1200
    chunk_overlap_chars: int = 150
    # Phase 2 semantic chunker (token-based; see app/ingestion/chunker.py).
    # Token counts use a deterministic chars-per-token estimator until the real
    # Qwen tokenizer is provisioned (estimator is swappable, config over code).
    chunk_min_tokens: int = 350
    chunk_max_tokens: int = 600
    chunk_overlap_ratio: float = 0.15
    table_row_serialize_threshold: int = 8  # >N rows → additional row chunks

    # --- retrieval / cache ---
    retrieval_top_k: int = 20
    retrieval_top_n: int = 5
    # Phase 3 visual retrieval: pages returned by MAX_SIM, capped (spec: top 4).
    visual_top_k_pages: int = 4
    # Phase 3 metadata path: max documents listed by a metadata lookup.
    metadata_max_documents: int = 10
    # Phase 3 context assembler: hard budgets for what reaches the generator.
    # Token budget sized to the dev 3B context (prod VL-32B raises it via env).
    context_token_budget: int = 3000
    context_max_images: int = 4  # spec: ≤4 page images per answer
    # RRF constant for merging text-chunk and page-image rankings (standard 60).
    fusion_rrf_k: int = 60
    retrieval_p95_target_ms: int = 800
    semantic_cache_collection: str = "semantic_cache"
    semantic_cache_similarity: float = 0.95
    semantic_cache_ttl_s: int = 86400
    # Phase 3: periodic sweep of expired cache entries (worker idle loop).
    semantic_cache_purge_interval_s: int = 3600

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
    # Phase 5 global admission control: a cap on concurrent in-flight chat turns
    # across ALL users, so a burst can't exhaust the vLLM queue / GPU. Sized to
    # the vLLM --max-num-seqs (48) with headroom; env-tuned on the prod host.
    global_max_inflight: int = 40

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
