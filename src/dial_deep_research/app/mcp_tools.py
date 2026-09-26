"""Shared MCP tool loading: build the client, fetch tools, prepare their schemas.

Used by any agent that talks to the configured MCP servers (the research graph, the
playground). Agent-specific tools (e.g. the research `finish_iteration` sentinel) are
added by the caller, not here.

One `tools/list` fetch per server serves consumers with different needs: the agent's tools,
which a model is offered, and the two tools the citation step calls — the file-sharing tool,
which only application code calls, and the dataset-metadata tool, which both do (see the
report-citations capability).

The client also carries the data-query capture: a tool-call interceptor that keeps the dataset
server's data-query records, which the tool messages cannot carry (see `research/data_queries.py`).
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
from langchain_mcp_adapters.interceptors import ToolCallInterceptor
from langchain_mcp_adapters.sessions import Connection

from dial_deep_research.app.research.data_queries import DataQueryCapture, DataQueryStore
from dial_deep_research.app_properties import MCPClientSettings
from dial_deep_research.settings import settings
from dial_deep_research.utils.json_schema_fixes import hoist_defs_to_root

logger = logging.getLogger(__name__)

# Bounds on one attempt of an MCP request, set here rather than inherited from the adapter's
# defaults because the tool-call retry multiplies them.
#
# Connecting and writing: a reachable server answers at once, so only an unreachable one waits
# this long — 5 s rather than the adapter's 30 s.
#
# Reading the answer: the bound is the longest silence between two chunks of the response. It is
# kept at the adapter's 300 s because exceeding it does not fail the call: `mcp` 1.x logs the read
# timeout at DEBUG and leaves the call waiting for a response that never comes. A lower bound
# would only turn slow calls that succeed today into calls that never return.
MCP_CONNECT_TIMEOUT_SECONDS = 5.0
MCP_READ_TIMEOUT_SECONDS = 300.0


class LoadedMcpTools(NamedTuple):
    """One turn's MCP tools, split by who may call them, and the client they came from.

    `agent_tools` is what a model is offered. `file_sharing_tool` and `dataset_metadata_tool` are
    the tools the configuration named for the application to call at report delivery, each
    `None` when no server named one or the named tool is absent from what its server advertises
    — the caller tells those two apart by the configured name, and warns only for the second
    (see the report-citations capability).

    The two differ in what naming them does to the agent: the file-sharing tool is taken out of
    `agent_tools`, while the dataset-metadata tool stays in it whenever the server's filter would
    offer it, because a catalogue listing is how the agent discovers which datasets exist.

    `client` is the same per-request client the tools were fetched with, kept because the
    citation step reads an MCP resource through it later in the turn (see
    `research/document_metadata.py`). It holds only the connection map, so a later read opens a
    session of its own with the same credentials.

    `data_queries` fills as the turn's tool calls run: the data-query records the client's
    capture keeps, which a data-query citation resolves against.
    """

    agent_tools: list[BaseTool]
    file_sharing_tool: BaseTool | None
    dataset_metadata_tool: BaseTool | None
    client: MultiServerMCPClient
    data_queries: DataQueryStore


def build_mcp_client(
    mcp_servers: list[MCPClientSettings],
    bearer_token: str | None = None,
    data_queries: DataQueryStore | None = None,
) -> MultiServerMCPClient:
    """Build a fresh per-request MCP client with one connection per configured server.

    Each server is either deployment- or direct-mode (see `MCPClientSettings`). Deployment
    mode builds the Core URL from `dial_url` and forwards the request bearer token (when
    present) as `Authorization: Bearer`; direct mode uses the server's bundled `connection`
    URL and api-key.

    With `data_queries`, every server naming a `data_query_meta_key` gets a capture that keeps
    its tool results' data-query records in that store.
    """
    connections: dict[str, Connection] = {}
    interceptors: list[ToolCallInterceptor] = []
    for server in mcp_servers:
        if data_queries is not None and server.data_query_meta_key:
            interceptors.append(
                DataQueryCapture(
                    server_name=server.server_name,
                    meta_key=server.data_query_meta_key,
                    store=data_queries,
                )
            )
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
            "timeout": MCP_CONNECT_TIMEOUT_SECONDS,
            "sse_read_timeout": MCP_READ_TIMEOUT_SECONDS,
        }
    return MultiServerMCPClient(connections=connections, tool_interceptors=interceptors)


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
    """Fetch the MCP tools, hoist their schemas, and turn off error conversion where needed.

    Tools are fetched per server so each server's `tools_to_include` filter applies (an empty
    filter includes all of that server's tools).

    A server whose configuration names a file-sharing tool has that tool taken out of the
    agent's tools and returned separately. A server naming a dataset-metadata tool has it
    returned as well and **left with the agent**: the app calls it to label dataset citations,
    while the agent calls it to discover which datasets exist, and those are the same listing.

    Both are looked up in the server's full advertised list, not in the filtered one:
    `tools_to_include` states which tools the research agent may call, so naming the
    file-sharing tool there must not offer it to a model, and leaving either out must not hide
    it from the app.
    """
    data_queries = DataQueryStore()
    mcp_client = build_mcp_client(mcp_servers, bearer_token=bearer_token, data_queries=data_queries)
    agent_tools: list[BaseTool] = []
    file_sharing_tool: BaseTool | None = None
    dataset_metadata_tool: BaseTool | None = None
    for server in mcp_servers:
        server_tools = await mcp_client.get_tools(server_name=server.server_name)
        available = [t.name for t in server_tools]
        if server.dataset_metadata_tool:
            dataset_metadata_tool = next(
                (t for t in server_tools if t.name == server.dataset_metadata_tool), None
            )
            logger.info(
                "MCP server '%s': dataset-metadata tool '%s' %s; it stays in the agent's tools",
                server.server_name,
                server.dataset_metadata_tool,
                "resolved" if dataset_metadata_tool is not None else "not advertised by the server",
            )
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

    # The schema fix is about being called by a model, so it stops at the agent's tools. Hoisting
    # exists so LangChain can dereference a schema it binds to a model; the app calls the
    # file-sharing tool with a dict input, which `BaseTool._parse_input` passes through
    # unvalidated when `args_schema` is a JSON-schema dict, as an MCP tool's always is.
    hoist_defs_to_root(agent_tools)
    # The agent's tools keep the error handler langchain-mcp-adapters installs: it turns a result
    # the server marks as an error into an error `ToolMessage` carrying every content block the
    # server sent, images included. A failure that is not such a result raises, and the agent's
    # `ToolFailureMiddleware` converts it.
    if file_sharing_tool is not None:
        # Cleared explicitly rather than left alone: langchain-mcp-adapters installs an error
        # handler on every tool it builds, which turns an MCP error into ordinary result
        # content. The app reads this tool's result itself and needs the failure to reach it.
        file_sharing_tool.handle_tool_error = False
    # The dataset-metadata tool's error handling is deliberately left as the agent's, because it
    # is the same object the agent is offered and one setting cannot serve both callers. Its
    # reader takes the failure off the returned message's `status` instead.
    return LoadedMcpTools(
        agent_tools=agent_tools,
        file_sharing_tool=file_sharing_tool,
        dataset_metadata_tool=dataset_metadata_tool,
        client=mcp_client,
        data_queries=data_queries,
    )
