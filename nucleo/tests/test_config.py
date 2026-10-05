import pytest
from pydantic import ValidationError

from azul.config import Settings


def test_defaults(settings):
    assert settings.host == "127.0.0.1"
    assert settings.port == 8710
    assert settings.brain_model == "claude-opus-5-5"
    assert settings.monthly_budget_usd == 50.0
    assert settings.budget_warning_usd == 40.0
    assert settings.anthropic_api_key is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AZUL_PORT", "9000")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")

    settings = Settings(_env_file=None)

    assert settings.port == 9000
    assert settings.anthropic_api_key.get_secret_value() == "clave-de-prueba"


def test_secrets_are_hidden_in_repr(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "clave-secreta")

    assert "clave-secreta" not in repr(Settings(_env_file=None))


def test_warning_must_be_below_budget():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, monthly_budget_usd=30, budget_warning_usd=30)
