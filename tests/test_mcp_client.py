"""`build_mcp_client` builds one connection per configured MCP server, and `load_mcp_tools`
returns the agent's tools in a deterministic (per-server, name-sorted) order, with the
application-called file-sharing tool separated out of them."""

import json
from types import SimpleNamespace
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import HttpUrl, SecretStr
from pytest import MonkeyPatch

import dial_deep_research.app.mcp_tools as tools_mod
from dial_deep_research.app.mcp_tools import build_mcp_client, load_mcp_tools
from dial_deep_research.app_properties import MCPClientSettings, MCPServerType


def _connection(client: MultiServerMCPClient, server_name: str) -> Any:
    return client.connections[server_name]


def _deployment_server(
    server_name: str = "rag",
    deployment_id: str = "generic-rag",
    server_type: MCPServerType = "generic_rag",
    file_sharing_tool: str | None = "get_citation_url",
) -> MCPClientSettings:
    # A document server must name its file-sharing tool, so the default names a valid one. A
    # server naming none is a dataset server, which has no files to share.
    return MCPClientSettings(
        server_name=server_name,
        server_type=server_type,
        deployment_id=deployment_id,
        file_sharing_tool=file_sharing_tool,
    )


def _dataset_server(server_name: str = "datasets") -> MCPClientSettings:
    """A server naming no file-sharing tool, which only a dataset server may do."""
    return _deployment_server(
        server_name=server_name,
        deployment_id="statgpt-mcp",
        server_type="statgpt",
        file_sharing_tool=None,
    )


def _direct_server(
    server_name: str = "rag",
    server_type: MCPServerType = "generic_rag",
    url: str = "http://localhost:8000/mcp",
    api_key: str = "local-secret",
) -> MCPClientSettings:
    # Bypass validation: this suite exercises build_mcp_client, not property parsing. Direct
    # mode is debug-gated and requires a $env:{...} placeholder (covered in test_app_properties);
    # here we construct an instance whose connection already holds the resolved JSON bundle.
    bundle = json.dumps({"url": url, "api_key": api_key})
    return MCPClientSettings.model_construct(
        server_name=server_name,
        server_type=server_type,
        file_sharing_tool=None,
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
            _direct_server(
                server_name="datasets",
                url="http://localhost:9000/mcp",
                api_key="k",
                server_type="statgpt",
            ),
        ],
        bearer_token="jwt-123",
    )

    assert set(client.connections) == {"rag", "datasets"}
    assert client.connections["rag"]["url"] == "http://core:8080/v1/deployments/generic-rag/mcp"
    assert client.connections["rag"]["headers"]["Authorization"] == "Bearer jwt-123"
    assert client.connections["datasets"]["url"] == "http://localhost:9000/mcp"
    assert client.connections["datasets"]["headers"] == {"api-key": "k"}


def _fake_tool(name: str) -> Any:
    # load_mcp_tools only reads `.name` (sort key), `.args_schema` (hoist step, skipped for
    # non-dict), and sets `.handle_tool_error`; a namespace satisfies all three.
    return SimpleNamespace(name=name, args_schema=None, handle_tool_error=False)


def _patch_get_tools(monkeypatch: MonkeyPatch, tools_by_server: dict[str, list[Any]]) -> None:
    async def fake_get_tools(*, server_name: str) -> list[Any]:
        return list(tools_by_server[server_name])

    monkeypatch.setattr(
        tools_mod, "build_mcp_client", lambda *a, **k: SimpleNamespace(get_tools=fake_get_tools)
    )


async def test_tools_are_name_sorted_regardless_of_listing_order(monkeypatch: MonkeyPatch) -> None:
    server = _deployment_server()

    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("zebra"), _fake_tool("alpha")]})
    first = (await load_mcp_tools([server])).agent_tools

    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("alpha"), _fake_tool("zebra")]})
    second = (await load_mcp_tools([server])).agent_tools

    assert [t.name for t in first] == ["alpha", "zebra"]
    assert [t.name for t in first] == [t.name for t in second]


async def test_configured_server_order_is_preserved(monkeypatch: MonkeyPatch) -> None:
    servers = [
        _deployment_server(),
        _dataset_server(),
    ]
    _patch_get_tools(
        monkeypatch,
        {
            "rag": [_fake_tool("search"), _fake_tool("get_page")],
            "datasets": [_fake_tool("plot"), _fake_tool("fetch")],
        },
    )

    tools = (await load_mcp_tools(servers)).agent_tools

    # rag's tools (name-sorted) precede the dataset server's tools (name-sorted).
    assert [t.name for t in tools] == ["get_page", "search", "fetch", "plot"]


def _file_sharing_server(
    tool_name: str = "share_documents", tools_to_include: list[str] | None = None
) -> MCPClientSettings:
    return MCPClientSettings(
        server_name="rag",
        server_type="generic_rag",
        deployment_id="generic-rag",
        tools_to_include=tools_to_include or [],
        file_sharing_tool=tool_name,
    )


async def test_the_file_sharing_tool_is_returned_apart_from_the_agents_tools(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("search"), _fake_tool("share_documents")]})

    loaded = await load_mcp_tools([_file_sharing_server()])

    assert [t.name for t in loaded.agent_tools] == ["search"]
    assert loaded.file_sharing_tool is not None
    assert loaded.file_sharing_tool.name == "share_documents"


async def test_a_filter_naming_the_file_sharing_tool_still_hides_it_from_the_agent(
    monkeypatch: MonkeyPatch,
) -> None:
    """`tools_to_include` says what the agent may call; this tool is never one of them."""
    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("search"), _fake_tool("share_documents")]})

    loaded = await load_mcp_tools(
        [_file_sharing_server(tools_to_include=["search", "share_documents"])]
    )

    assert [t.name for t in loaded.agent_tools] == ["search"]
    assert loaded.file_sharing_tool is not None


async def test_a_filter_omitting_the_file_sharing_tool_still_finds_it_for_the_app(
    monkeypatch: MonkeyPatch,
) -> None:
    """It is resolved from the server's full advertised list, not from the filtered one."""
    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("search"), _fake_tool("share_documents")]})

    loaded = await load_mcp_tools([_file_sharing_server(tools_to_include=["search"])])

    assert [t.name for t in loaded.agent_tools] == ["search"]
    assert loaded.file_sharing_tool is not None
    assert loaded.file_sharing_tool.name == "share_documents"


async def test_error_handling_is_off_on_the_file_sharing_tool_and_on_for_the_agents(
    monkeypatch: MonkeyPatch,
) -> None:
    """The adapter installs an error handler on every tool; the app needs the failure itself."""
    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("search"), _fake_tool("share_documents")]})

    loaded = await load_mcp_tools([_file_sharing_server()])

    assert loaded.file_sharing_tool is not None
    assert loaded.file_sharing_tool.handle_tool_error is False
    assert [t.handle_tool_error for t in loaded.agent_tools] == [True]


async def test_a_configured_tool_the_server_does_not_advertise_is_reported_as_absent(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_get_tools(monkeypatch, {"rag": [_fake_tool("search")]})

    loaded = await load_mcp_tools([_file_sharing_server(tool_name="copy_to_user")])

    assert loaded.file_sharing_tool is None
    assert [t.name for t in loaded.agent_tools] == ["search"]


async def test_no_configured_tool_leaves_every_tool_with_the_agent(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_get_tools(
        monkeypatch, {"datasets": [_fake_tool("search"), _fake_tool("share_documents")]}
    )

    loaded = await load_mcp_tools([_dataset_server()])

    assert [t.name for t in loaded.agent_tools] == ["search", "share_documents"]
    assert loaded.file_sharing_tool is None
