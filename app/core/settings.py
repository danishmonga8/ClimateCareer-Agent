"""Secure application configuration loaded from environment variables."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-based settings for ClimateCareer-Agent."""

    openai_api_key: SecretStr
    openai_model: str = "gpt-5.6-luna"
    openai_timeout_seconds: float = Field(default=60, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=5)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def get_settings() -> Settings:
    """Load and validate application settings."""
    return Settings()
