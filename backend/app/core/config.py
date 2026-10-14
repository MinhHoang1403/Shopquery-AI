"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local defaults where appropriate."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ShopQuery AI"
    gemini_api_key: str | None = None
    gemini_generation_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_request_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    gemini_retry_attempts: int = Field(default=3, ge=1, le=5)
    embedding_dimensions: int = 768
    database_setup_url: str = (
        "postgresql+psycopg://shopquery_setup:setup_password@127.0.0.1:54321/shopquery"
    )
    database_readonly_url: str = (
        "postgresql+psycopg://shopquery_reader:readonly_password@127.0.0.1:54321/shopquery"
    )
    demo_reference_date: str = "2026-10-01"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    sql_statement_timeout_ms: int = Field(default=5_000, ge=100, le=60_000)
    sql_max_rows: int = Field(default=200, ge=1, le=1_000)
    log_level: str = "INFO"

    @field_validator("embedding_dimensions")
    @classmethod
    def require_supported_embedding_size(cls, value: int) -> int:
        if value != 768:
            raise ValueError("ShopQuery AI requires 768-dimensional embeddings")
        return value

    @field_validator("gemini_embedding_model")
    @classmethod
    def require_embedding_model(cls, value: str) -> str:
        if value != "gemini-embedding-2":
            raise ValueError("GEMINI_EMBEDDING_MODEL must be gemini-embedding-2")
        return value

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def documents_directory(self) -> Path:
        return self.project_root / "data" / "documents"

    @property
    def seed_directory(self) -> Path:
        return self.project_root / "data" / "seed"


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide immutable-style settings instance."""

    return Settings()
