import pytest
from pydantic import ValidationError

from dial_deep_research.channel_config import ChannelConfig
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


@pytest.mark.parametrize("var", ["MCP_SERVER_NAME", "MCP_URL", "MCP_API_KEY"])
def test_empty_required_string_is_rejected(var: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(var, "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == (var.lower(),) for err in excinfo.value.errors())


@pytest.mark.parametrize(
    "overrides",
    [
        {"channel_name": ""},
        {"prompts.client_name": ""},
        {"prompts.agent_name": ""},
        {"prompts.data_sources_descriptions": ""},
    ],
)
def test_empty_channel_config_string_is_rejected(overrides: dict[str, str]) -> None:
    data: dict = {
        "channel_name": "test-channel",
        "prompts": {
            "client_name": "Test Corp",
            "agent_name": "Test Deep Research",
            "data_sources_descriptions": "## report\n\nA report.",
        },
    }
    for dotted, value in overrides.items():
        target = data
        *parents, leaf = dotted.split(".")
        for key in parents:
            target = target[key]
        target[leaf] = value
    with pytest.raises(ValidationError):
        ChannelConfig.model_validate(data)


@pytest.mark.parametrize("var", ["DIAL_URL", "MCP_URL"])
@pytest.mark.parametrize("raw", ["not-a-url", "localhost:8080", "ftp://host/x"])
def test_non_http_url_is_rejected(var: str, raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(var, raw)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert any(err["loc"] == (var.lower(),) for err in excinfo.value.errors())
