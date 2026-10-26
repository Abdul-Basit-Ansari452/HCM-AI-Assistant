"""Application configuration loaded from environment variables and .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Secrets are read from `.env` (or the process environment) and are never
    hardcoded or logged.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "HRMS"
    database_url: str = "sqlite:///./hrms.db"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 12 * 60
    openai_api_key: str = ""
    # Test-only override for the shared hourly AI quota.
    rate_limit_override: int | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
