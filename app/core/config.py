"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
