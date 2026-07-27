"""Tests for secure environment-based settings."""

from app.core.settings import Settings


def test_api_key_is_loaded_as_a_secret(monkeypatch) -> None:
    """The API key should load without appearing in object representations."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "sk-test-placeholder"
    assert "sk-test-placeholder" not in repr(settings.openai_api_key)
