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


def test_empty_mcp_server_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_SERVER_NAME", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("mcp_server_name",) for err in excinfo.value.errors())


def test_deployment_mode_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_URL", raising=False)
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    monkeypatch.setenv("MCP_DEPLOYMENT_NAME", "generic-rag-mcp")
    settings = Settings()
    assert settings.mcp_url is None
    assert settings.mcp_deployment_name == "generic-rag-mcp"


def test_local_dev_mode_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("MCP_API_KEY", "local-key")
    monkeypatch.delenv("MCP_DEPLOYMENT_NAME", raising=False)
    settings = Settings()
    assert settings.mcp_url is not None
    assert settings.mcp_api_key is not None
    assert settings.mcp_api_key.get_secret_value() == "local-key"


def test_local_dev_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "http://localhost:8000/mcp")
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    monkeypatch.delenv("MCP_DEPLOYMENT_NAME", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "MCP_API_KEY" in str(excinfo.value)


def test_no_mcp_mode_configured_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_URL", raising=False)
    monkeypatch.delenv("MCP_DEPLOYMENT_NAME", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "MCP_DEPLOYMENT_NAME" in str(excinfo.value)


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


@pytest.mark.parametrize("var", ["DIAL_URL", "MCP_URL"])
@pytest.mark.parametrize("raw", ["not-a-url", "localhost:8080", "ftp://host/x"])
def test_non_http_url_is_rejected(var: str, raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(var, raw)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == (var.lower(),) for err in excinfo.value.errors())


def test_missing_dial_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIAL_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == ("dial_url",) for err in excinfo.value.errors())
