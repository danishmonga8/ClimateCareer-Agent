"""Tests for secure OpenAI client creation."""

from unittest.mock import patch

from app.core.settings import Settings
from app.integrations.openai_client import create_openai_client


def test_openai_client_uses_secure_settings(monkeypatch) -> None:
    """Client creation should use settings without making an API call."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")

    settings = Settings(_env_file=None)

    with patch("app.integrations.openai_client.OpenAI") as mocked_client:
        create_openai_client(settings)

    mocked_client.assert_called_once_with(
        api_key="sk-test-placeholder",
        timeout=60,
        max_retries=2,
    )
    assert settings.openai_model == "gpt-5.6-luna"