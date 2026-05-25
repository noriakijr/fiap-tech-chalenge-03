import pytest

from app.core.config import Settings, get_settings


def test_settings_defaults_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "CONFIDENCE_THRESHOLD",
        "PLN_TIMEOUT_SECONDS",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_model == "gpt-4o"
    assert settings.embeddings_model == "text-embedding-3-small"
    assert settings.confidence_threshold == 0.65
    assert settings.pln_timeout_seconds == 10.0
    assert settings.database_url.startswith("sqlite")
    assert settings.log_level == "INFO"


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.8")
    monkeypatch.setenv("PLN_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key == "sk-test"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.confidence_threshold == 0.8
    assert settings.pln_timeout_seconds == 5.0
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_confidence_threshold_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, confidence_threshold=1.5)


def test_pln_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, pln_timeout_seconds=0)


def test_get_settings_is_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b
