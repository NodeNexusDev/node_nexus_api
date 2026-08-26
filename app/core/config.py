"""Application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    # API Key Authentication
    MASTER_API_KEY: str = ""

    # Encryption
    ENCRYPTION_SALT: str = ""  # Required in production — set via .env

    # SSH host verification
    SSH_STRICT_HOST_KEY_CHECKING: bool = True
    SSH_KNOWN_HOSTS_PATH: str = "/app/.ssh/known_hosts"

    # Persistent scheduler
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_OWNERSHIP_POLL_SECONDS: float = 5.0
    SCHEDULER_RECONCILIATION_INTERVAL_SECONDS: float = 10.0

    # Request timeout
    REQUEST_TIMEOUT: int = 300  # seconds

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100  # max requests per window
    RATE_LIMIT_WINDOW: int = 60  # window in seconds

    # Audit log retention
    AUDIT_LOG_RETENTION_DAYS: int = 90  # 0 = disabled

    # Auto-migration on startup (disable for manual migration control in prod)
    AUTO_MIGRATE: bool = True

    # Prometheus metrics
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PATH: str = "/metrics"

    # OpenTelemetry
    OTEL_ENABLED: bool = False
    OTEL_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "node-nexus-api"

    # API versioning
    SUPPORTED_API_VERSIONS: list[str] = Field(default=["1"])

    # E2E test harness endpoints (disable in production)
    E2E_ENABLED: bool = False

    # JWT Authentication
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_COOKIE_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days in seconds
    INITIAL_SUPERUSER_EMAIL: str = ""
    INITIAL_SUPERUSER_PASSWORD: str = ""


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
