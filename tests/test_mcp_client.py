"""`build_mcp_client` builds one connection per configured MCP server."""

import json
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import HttpUrl, SecretStr
from pytest import MonkeyPatch

import dial_deep_research.app.mcp_tools as tools_mod
from dial_deep_research.app.mcp_tools import build_mcp_client
from dial_deep_research.app_properties import MCPClientSettings


def _connection(client: MultiServerMCPClient, server_name: str) -> Any:
    return client.connections[server_name]


def _deployment_server(
    server_name: str = "rag", deployment_id: str = "generic-rag"
) -> MCPClientSettings:
    return MCPClientSettings(server_name=server_name, deployment_id=deployment_id)


def _direct_server(
    server_name: str = "rag",
    url: str = "http://localhost:8000/mcp",
    api_key: str = "local-secret",
) -> MCPClientSettings:
    # Bypass validation: this suite exercises build_mcp_client, not property parsing. Direct
    # mode is debug-gated and requires a $env:{...} placeholder (covered in test_app_properties);
    # here we construct an instance whose connection already holds the resolved JSON bundle.
    bundle = json.dumps({"url": url, "api_key": api_key})
    return MCPClientSettings.model_construct(
        server_name=server_name,
        connection=SecretStr(bundle),
        deployment_id=None,
        tools_to_include=[],
    )


def test_deployment_mode_builds_core_url_and_forwards_bearer(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "dial_url", HttpUrl("http://core:8080"))

    client = build_mcp_client([_deployment_server()], bearer_token="jwt-123")
    conn = _connection(client, "rag")

    assert conn["transport"] == "streamable_http"
    assert conn["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert conn["headers"]["Authorization"] == "Bearer jwt-123"
    # api-key is injected by SDK header propagation, not set here.
    assert "api-key" not in conn["headers"]


def test_deployment_mode_without_bearer_omits_authorization(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "dial_url", HttpUrl("http://core:8080"))

    conn = _connection(build_mcp_client([_deployment_server()], bearer_token=None), "rag")

    assert conn["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert conn["headers"] == {}


def test_direct_mode_uses_static_key_and_url() -> None:
    # A bearer must be ignored in direct mode.
    conn = _connection(build_mcp_client([_direct_server()], bearer_token="jwt-ignored"), "rag")

    assert conn["url"] == "http://localhost:8000/mcp"
    assert conn["headers"] == {"api-key": "local-secret"}
    assert "Authorization" not in conn["headers"]


def test_multiple_servers_build_independent_connections(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "dial_url", HttpUrl("http://core:8080"))

    client = build_mcp_client(
        [
            _deployment_server(server_name="rag", deployment_id="generic-rag"),
            _direct_server(server_name="charts", url="http://localhost:9000/mcp", api_key="k"),
        ],
        bearer_token="jwt-123",
    )

    assert set(client.connections) == {"rag", "charts"}
    assert client.connections["rag"]["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert client.connections["rag"]["headers"]["Authorization"] == "Bearer jwt-123"
    assert client.connections["charts"]["url"] == "http://localhost:9000/mcp"
    assert client.connections["charts"]["headers"] == {"api-key": "k"}
