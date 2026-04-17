"""
Centralized configuration via pydantic-settings.

Every setting is loaded from environment variables with sensible defaults
for local development. In production, these are injected via K8s ConfigMaps
and Secrets — never committed to source control.
"""

from __future__ import annotations

import enum
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, enum.Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings with validation and type safety."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────
    app_name: str = "eval-engine"
    app_env: Environment = Environment.DEVELOPMENT
    app_debug: bool = False
    app_version: str = "1.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 4

    # ── Security ─────────────────────────────────────────
    secret_key: str = "change-me-to-a-64-char-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    api_key_header: str = "X-API-Key"
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── PostgreSQL ───────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://eval:eval_secret@localhost:5432/eval_engine"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    redis_cache_ttl: int = 300

    # ── Celery ───────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_worker_concurrency: int = 8
    celery_task_soft_time_limit: int = 300
    celery_task_hard_time_limit: int = 600

    # ── S3 / MinIO ───────────────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket_name: str = "eval-engine"
    s3_region: str = "us-east-1"
    s3_presigned_url_expiry: int = 3600

    # ── Observability ────────────────────────────────────
    sentry_dsn: str = ""
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Rate Limiting ────────────────────────────────────
    rate_limit_default: int = 100
    rate_limit_window_seconds: int = 60

    # ── OpenTelemetry ────────────────────────────────────
    otel_enabled: bool = True
    otel_service_name: str = "eval-engine"
    otel_exporter: str = "jaeger"  # "jaeger" | "otlp" | "console"
    otel_endpoint: str = "http://localhost:4317"
    otel_sample_rate: float = 1.0  # 1.0 in dev, 0.1 in prod

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Warn if using the default secret key (insecure for production)."""
        if v == "change-me-to-a-64-char-random-string":
            import warnings

            warnings.warn(
                "Using default SECRET_KEY — this is insecure for production.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Enforce strict validation in production environments."""
        if self.app_env == Environment.PRODUCTION:
            if self.app_debug:
                raise ValueError("DEBUG must be disabled in production")
            if not self.sentry_dsn:
                raise ValueError("SENTRY_DSN is required in production")
            if self.secret_key == "change-me-to-a-64-char-random-string":
                raise ValueError("SECRET_KEY must be changed in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton settings instance, cached after first call.

    Using lru_cache instead of a module-level global ensures the settings
    object is created lazily — important for testing where we may want
    to override environment variables before the first import.
    """
    return Settings()
