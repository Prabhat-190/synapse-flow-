"""Application configuration via pydantic-settings."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    atlas_env: str = "development"
    atlas_api_key: SecretStr = SecretStr("dev-secret-key-change-in-production")

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.0-flash"
    fallback_model: str = "gemini-1.5-flash"

    database_url: str = "postgresql+asyncpg://atlas:atlas@localhost:5433/atlas"
    sync_database_url: str = "postgresql://atlas:atlas@localhost:5433/atlas"

    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = "redis://localhost:6380/1"
    celery_result_backend: str = "redis://localhost:6380/2"

    max_context_tokens: int = 128_000
    compression_threshold: float = 0.85
    never_silent_truncation: bool = True

    prompt_injection_threshold: float = 0.45
    rate_limit_rpm: int = 60

    otel_exporter_otlp_endpoint: str = ""
    log_level: str = "INFO"

    embedding_dim: int = Field(default=768, description="pgvector embedding dimension")


@lru_cache
def get_settings() -> Settings:
    return Settings()
