"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local defaults where appropriate."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ShopQuery AI"
    app_environment: Literal["development", "test", "production"] = "development"
    app_origin: str = "http://127.0.0.1:8080"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    auth_invited_emails: list[str] = Field(default_factory=list)
    auth_session_hours: int = Field(default=12, ge=1, le=168)
    api_docs_enabled: bool = False
    beta_provider_data_enabled: bool = False
    beta_login_per_ip_hour: int = Field(default=20, ge=1, le=1000)
    trusted_proxy_hosts: list[str] = Field(default_factory=list)
    beta_chat_per_user_hour: int = Field(default=30, ge=1, le=1000)
    beta_upload_per_user_hour: int = Field(default=60, ge=1, le=1000)
    beta_preview_per_user_hour: int = Field(default=180, ge=1, le=1000)
    beta_user_concurrency: int = Field(default=1, ge=1, le=10)
    beta_system_concurrency: int = Field(default=4, ge=1, le=30)
    beta_max_datasets: int = Field(default=20, ge=1, le=100)
    beta_max_user_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    guest_enabled: bool = True
    guest_ai_enabled: bool = False
    guest_session_seconds: int = Field(default=600, ge=30, le=3600)
    guest_cleanup_seconds: int = Field(default=15, ge=1, le=60)
    guest_max_sessions: int = Field(default=20, ge=1, le=100)
    guest_questions_per_session: int = Field(default=5, ge=1, le=20)
    guest_chat_per_ip_hour: int = Field(default=10, ge=1, le=100)
    guest_sessions_per_ip_hour: int = Field(default=120, ge=1, le=1000)
    guest_uploads_per_ip_hour: int = Field(default=60, ge=1, le=1000)
    guest_previews_per_ip_hour: int = Field(default=180, ge=1, le=1000)
    guest_previews_per_session: int = Field(default=40, ge=1, le=200)
    guest_system_concurrency: int = Field(default=2, ge=1, le=4)
    guest_max_files: int = Field(default=8, ge=1, le=16)
    guest_max_file_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=5 * 1024 * 1024)
    guest_max_session_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    guest_max_total_bytes: int = Field(default=128 * 1024 * 1024, ge=1024)
    guest_max_rows: int = Field(default=5000, ge=1, le=5000)
    guest_max_columns: int = Field(default=30, ge=1, le=30)
    guest_max_pages: int = Field(default=20, ge=1, le=30)
    guest_max_characters: int = Field(default=100_000, ge=1000, le=200_000)
    guest_max_chunks: int = Field(default=32, ge=1, le=60)
    guest_max_prompt_characters: int = Field(default=2000, ge=100, le=2000)
    guest_parse_timeout_seconds: int = Field(default=10, ge=1, le=20)
    guest_request_timeout_seconds: int = Field(default=120, ge=5, le=180)
    guest_worker_memory_mb: int = Field(default=768, ge=256, le=1024)
    guest_worker_cpu_seconds: int = Field(default=15, ge=1, le=30)
    ai_default_model: Literal["inetcloud-knowledge", "gemini"] = "inetcloud-knowledge"
    inetcloud_base_url: str | None = None
    inetcloud_model: Literal["knowledge"] = "knowledge"
    inetcloud_timeout_seconds: float = Field(default=60, ge=1, le=120)
    inetcloud_retry_attempts: int = Field(default=1, ge=1, le=3)
    ai_gemini_fallback_enabled: bool = False
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
    sql_join_v1_enabled: bool = False
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1_024, le=25 * 1024 * 1024)
    upload_max_rows: int = Field(default=5_000, ge=1, le=20_000)
    upload_max_columns: int = Field(default=30, ge=1, le=100)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_auth_origin(self) -> "Settings":
        parsed = HttpUrl(self.app_origin)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/"
        ):
            raise ValueError("APP_ORIGIN must be an origin without credentials or a path")
        if parsed.scheme != "https" and (
            self.app_environment == "production" or parsed.host not in {"localhost", "127.0.0.1"}
        ):
            raise ValueError("APP_ORIGIN requires HTTPS outside localhost development")
        self.app_origin = str(parsed).rstrip("/")
        self.auth_invited_emails = [email.strip().casefold() for email in self.auth_invited_emails]
        return self

    @property
    def session_cookie_name(self) -> str:
        return "__Host-shopquery_session" if self.secure_cookies else "shopquery_session"

    @property
    def secure_cookies(self) -> bool:
        return self.app_environment == "production" or self.app_origin.startswith("https://")

    @property
    def oidc_callback_url(self) -> str:
        return f"{self.app_origin}/api/auth/callback"

    @field_validator("inetcloud_base_url")
    @classmethod
    def validate_inetcloud_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = HttpUrl(value)
        if (
            parsed.scheme != "https"
            or not parsed.host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("INETCLOUD_BASE_URL must be an HTTPS URL without credentials")
        return str(parsed).rstrip("/")

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
