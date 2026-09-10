"""Shared MCP tool loading: build the client, fetch tools, prepare their schemas.

Used by any agent that talks to the configured MCP servers (the research graph, the
playground). Agent-specific tools (e.g. the research `finish_iteration` sentinel) are
added by the caller, not here.

One `tools/list` fetch per server serves two consumers with different needs: the agent's
tools, which a model is offered, and the file-sharing tool, which only application code calls
(see the report-citations capability).
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection

from dial_deep_research.app_properties import MCPClientSettings
from dial_deep_research.settings import settings
from dial_deep_research.utils.json_schema_fixes import hoist_defs_to_root

logger = logging.getLogger(__name__)


class LoadedMcpTools(NamedTuple):
    """One turn's MCP tools, split by who may call them.

    `agent_tools` is what a model is offered. `file_sharing_tool` is the tool the configuration
    named for the application to call at report delivery, or `None` when no server named one or
    the named tool is absent from what its server advertises — the caller tells those two apart
    by the configured name, and warns only for the second (see the report-citations capability).
    """

    agent_tools: list[BaseTool]
    file_sharing_tool: BaseTool | None


def build_mcp_client(
    mcp_servers: list[MCPClientSettings], bearer_token: str | None = None
) -> MultiServerMCPClient:
    """Build a fresh per-request MCP client with one connection per configured server.

    Each server is either deployment- or direct-mode (see `MCPClientSettings`). Deployment
    mode builds the Core URL from `dial_url` and forwards the request bearer token (when
    present) as `Authorization: Bearer`; direct mode uses the server's bundled `connection`
    URL and api-key.
    """
    connections: dict[str, Connection] = {}
    for server in mcp_servers:
        if server.deployment_id is not None:
            base = settings.dial_url.encoded_string().rstrip("/")
            url = f"{base}/v1/deployments/{server.deployment_id}/mcp"
            headers = {}
            if bearer_token:
                headers["Authorization"] = f"Bearer {bearer_token}"
        elif server.connection is not None:
            bundle = server.direct_connection
            url = bundle.url.encoded_string()
            headers = {"api-key": bundle.api_key.get_secret_value()}
        else:
            raise ValueError(f"Invalid MCP server settings: {server}")
        connections[server.server_name] = {
            "transport": "streamable_http",
            "url": url,
            "headers": headers,
        }
    return MultiServerMCPClient(connections=connections)


def enable_tool_error_handling(tools: list[BaseTool]) -> list[BaseTool]:
    """Convert each tool's `ToolException` into an error `ToolMessage` instead of raising.

    Without this a `ToolException` (raised by langchain-mcp-adapters on an MCP error
    response, including the server's own pydantic rejections) bubbles past the tool node
    and fails the whole turn. `handle_tool_error=True` makes the tool return the error
    text as its result with `status="error"`; the agent then receives it as a
    `ToolMessage` and can retry with corrected args.
    """
    for t in tools:
        t.handle_tool_error = True
    return tools


def _dump_tool_schemas_to_json(tools: list[BaseTool], dp: Path) -> None:
    if dp.exists():
        shutil.rmtree(dp)
    dp.mkdir(parents=True, exist_ok=False)
    for t in tools:
        fname = dp / f"{t.name}.json"
        with open(fname, "w") as f:
            json.dump(t.args_schema, f, indent=2, default=str, ensure_ascii=False)


async def load_mcp_tools(
    mcp_servers: list[MCPClientSettings], bearer_token: str | None = None
) -> LoadedMcpTools:
    """Fetch the MCP tools, hoist their schemas, and wire error handling.

    Tools are fetched per server so each server's `tools_to_include` filter applies (an empty
    filter includes all of that server's tools).

    A server whose configuration names a file-sharing tool has that tool taken out of the
    agent's tools and returned separately. It is looked up in the server's full advertised
    list, not in the filtered one: `tools_to_include` states which tools the research agent may
    call, so naming the file-sharing tool there must not offer it to a model, and leaving it
    out must not hide it from the app.
    """
    mcp_client = build_mcp_client(mcp_servers, bearer_token=bearer_token)
    agent_tools: list[BaseTool] = []
    file_sharing_tool: BaseTool | None = None
    for server in mcp_servers:
        server_tools = await mcp_client.get_tools(server_name=server.server_name)
        available = [t.name for t in server_tools]
        if server.file_sharing_tool:
            file_sharing_tool = next(
                (t for t in server_tools if t.name == server.file_sharing_tool), None
            )
            logger.info(
                "MCP server '%s': file-sharing tool '%s' %s; it is kept out of the agent's tools",
                server.server_name,
                server.file_sharing_tool,
                "resolved" if file_sharing_tool is not None else "not advertised by the server",
            )
            server_tools = [t for t in server_tools if t.name != server.file_sharing_tool]
        if server.tools_to_include:
            allowed = set(server.tools_to_include)
            server_tools = [t for t in server_tools if t.name in allowed]
            missing = sorted(allowed - set(available))
            logger.info(
                "MCP server '%s': fetched %d tool(s) %s; filtered to %d %s (requested but "
                "not found: %s)",
                server.server_name,
                len(available),
                available,
                len(server_tools),
                [t.name for t in server_tools],
                missing or "none",
            )
        else:
            logger.info(
                "MCP server '%s': fetched %d tool(s) %s; %d of them go to the agent %s",
                server.server_name,
                len(available),
                available,
                len(server_tools),
                [t.name for t in server_tools],
            )
        # Sort by name within each server so the serialized `tools` array is byte-stable
        # across requests (server listing order is not guaranteed). A stable array is what
        # lets DIAL Core's content hashes and the provider's prompt cache match on repeated
        # calls; configured server order is preserved.
        agent_tools.extend(sorted(server_tools, key=lambda t: t.name))
    logger.info(
        "Loaded %d MCP tool(s) for the agent across %d MCP server(s)",
        len(agent_tools),
        len(mcp_servers),
    )

    # TODO: either remove or use envvar
    dump_tool_schemas = False
    if dump_tool_schemas:
        tool_schemas_base_dp = Path("data") / "tool_schemas" / datetime.now().isoformat()
        _dump_tool_schemas_to_json(agent_tools, tool_schemas_base_dp / "raw")

    # The schema fix and the error handling are both about being called by a model, so both
    # stop at the agent's tools. Hoisting exists so LangChain can dereference a schema it binds
    # to a model; the app calls the file-sharing tool with a dict input, which
    # `BaseTool._parse_input` passes through unvalidated when `args_schema` is a JSON-schema
    # dict, as an MCP tool's always is.
    hoist_defs_to_root(agent_tools)
    enable_tool_error_handling(agent_tools)
    if file_sharing_tool is not None:
        # Cleared explicitly rather than left alone: langchain-mcp-adapters installs an error
        # handler on every tool it builds, which turns an MCP error into ordinary result
        # content. The app reads this tool's result itself and needs the failure to reach it.
        file_sharing_tool.handle_tool_error = False
    return LoadedMcpTools(agent_tools=agent_tools, file_sharing_tool=file_sharing_tool)
