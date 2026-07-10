"""`build_mcp_client` picks deployment (through Core) vs local-dev (static key) mode."""

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import HttpUrl, SecretStr
from pytest import MonkeyPatch

import dial_deep_research.app.research.tools as tools_mod
from dial_deep_research.app.research.tools import build_mcp_client


def _only_connection(client: MultiServerMCPClient) -> Any:
    connections = client.connections
    assert len(connections) == 1
    return next(iter(connections.values()))


def test_deployment_mode_builds_core_url_and_forwards_bearer(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "mcp_url", None)
    monkeypatch.setattr(tools_mod.settings, "mcp_api_key", None)
    monkeypatch.setattr(tools_mod.settings, "mcp_deployment_name", "generic-rag")
    monkeypatch.setattr(tools_mod.settings, "dial_url", HttpUrl("http://core:8080"))

    conn = _only_connection(build_mcp_client(bearer_token="jwt-123"))

    assert conn["transport"] == "streamable_http"
    assert conn["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert conn["headers"]["Authorization"] == "Bearer jwt-123"
    # api-key is injected by SDK header propagation, not set here.
    assert "api-key" not in conn["headers"]


def test_deployment_mode_without_bearer_omits_authorization(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "mcp_url", None)
    monkeypatch.setattr(tools_mod.settings, "mcp_api_key", None)
    monkeypatch.setattr(tools_mod.settings, "mcp_deployment_name", "generic-rag")
    monkeypatch.setattr(tools_mod.settings, "dial_url", HttpUrl("http://core:8080"))

    conn = _only_connection(build_mcp_client(bearer_token=None))

    assert conn["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert conn["headers"] == {}


def test_local_dev_mode_uses_static_key_and_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "mcp_url", HttpUrl("http://localhost:8000/mcp"))
    monkeypatch.setattr(tools_mod.settings, "mcp_api_key", SecretStr("local-secret"))

    # A bearer must be ignored in local-dev mode.
    conn = _only_connection(build_mcp_client(bearer_token="jwt-ignored"))

    assert conn["url"] == "http://localhost:8000/mcp"
    assert conn["headers"] == {"api-key": "local-secret"}
    assert "Authorization" not in conn["headers"]
