"""Factory for creating a securely configured OpenAI client."""

from openai import OpenAI

from app.core.settings import Settings, get_settings


def create_openai_client(settings: Settings | None = None) -> OpenAI:
    """Create an OpenAI client without exposing the API key."""
    active_settings = settings or get_settings()

    return OpenAI(
        api_key=active_settings.openai_api_key.get_secret_value(),
        timeout=active_settings.openai_timeout_seconds,
        max_retries=active_settings.openai_max_retries,
    )
