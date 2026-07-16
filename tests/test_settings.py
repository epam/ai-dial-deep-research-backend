import pytest
from pydantic import ValidationError

from dial_deep_research.settings import Settings


def test_canonical_uppercase_log_level_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert Settings().log_level == "DEBUG"


@pytest.mark.parametrize("raw", ["warning", "Warning", "WaRnInG"])
def test_mixed_case_log_level_is_normalized(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", raw)
    assert Settings().log_level == "WARNING"


def test_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "ifno")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] in {("log_level",), ("LOG_LEVEL",)} for err in excinfo.value.errors())


def test_logging_settings_defaults_load(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LOG_FORMAT", "LOG_DATE_FORMAT", "DEEP_RESEARCH_LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert "%(otel_context)s" in settings.log_format
    assert settings.log_date_format == "%Y-%m-%d %H:%M:%S"
    assert settings.deep_research_log_level == "INFO"


def test_deep_research_log_level_is_independent_of_log_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEP_RESEARCH_LOG_LEVEL", "debug")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    settings = Settings()
    assert settings.deep_research_log_level == "DEBUG"
    assert settings.log_level == "INFO"


def test_unknown_deep_research_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEP_RESEARCH_LOG_LEVEL", "ifno")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("deep_research_log_level",) for err in excinfo.value.errors())


def test_positive_heartbeat_interval_override_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEARTBEAT_INTERVAL", "30")
    assert Settings().heartbeat_interval == 30


@pytest.mark.parametrize("raw", ["0", "-1"])
def test_non_positive_heartbeat_interval_is_rejected(
    raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEARTBEAT_INTERVAL", raw)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(
        err["loc"] in {("heartbeat_interval",), ("HEARTBEAT_INTERVAL",)}
        for err in excinfo.value.errors()
    )


def test_opik_project_name_default_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPIK_PROJECT_NAME", raising=False)
    assert Settings().opik_project_name == "deep-research"


def test_opik_project_name_override_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPIK_PROJECT_NAME", "my-experiment")
    assert Settings().opik_project_name == "my-experiment"


def test_empty_opik_project_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPIK_PROJECT_NAME", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("opik_project_name",) for err in excinfo.value.errors())


@pytest.mark.parametrize("raw", ["not-a-url", "localhost:8080", "ftp://host/x", ""])
def test_non_http_dial_url_is_rejected(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIAL_URL", raw)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("dial_url",) for err in excinfo.value.errors())


def test_missing_dial_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIAL_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("dial_url",) for err in excinfo.value.errors())
