"""Runtime configuration. Every value can be set via environment or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EB_", env_file=".env", extra="ignore")

    # Core
    env: str = "dev"
    database_url: str = "postgresql://eb:eb@localhost:5432/engineering_brain"
    data_dir: Path = Field(default=Path("./data"), description="Local object store root")
    wiki_dir: Path = Field(
        default=Path("./data/wiki"),
        description="Markdown wiki: its own git repository (never nested inside this project repo)",
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # Auth (dev mode uses a static user; OIDC in production)
    auth_mode: str = "dev"  # dev | oidc
    dev_user_email: str = "dev@example.com"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None

    # Embeddings. provider: tei | hash
    embedding_provider: str = "hash"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    tei_embed_url: str = "http://localhost:8080"
    tei_rerank_url: str | None = None  # None disables reranking
    rerank_candidates: int = 150
    rerank_top_k: int = 20

    # LLM. provider: anthropic | fake
    llm_provider: str = "anthropic"
    llm_model_answer: str = "claude-opus-5-5"
    llm_model_fast: str = "claude-haiku-5-5"
    llm_model_long: str = "claude-sonnet-5-5"
    llm_max_tokens: int = 16000

    # Ingest
    chunk_target_tokens: int = 400
    chunk_max_tokens: int = 800
    contextual_prefix_llm: bool = False  # LLM-written one-line summaries per chunk
    parser: str = "pypdf"  # pypdf | docling | docling-serve
    docling_serve_url: str | None = None

    # Worker
    worker_poll_seconds: float = 1.0
    worker_concurrency: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
