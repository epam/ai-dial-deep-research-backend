"""Tools for the research graph: MCP-loaded research tools + the finish sentinel.

The MCP-client construction and tool preparation (schema hoisting, error handling)
move here from the retired `app/agent.py` so the researcher node can reuse them.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool, tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection

from dial_deep_research.app_properties import MCPClientSettings
from dial_deep_research.settings import settings
from dial_deep_research.utils.json_schema_fixes import hoist_defs_to_root

logger = logging.getLogger(__name__)

FINISH_ITERATION_RESULT = "Research iteration complete; handing off to the reviewer."


def build_mcp_client(
    mcp_servers: list[MCPClientSettings], bearer_token: str | None = None
) -> MultiServerMCPClient:
    """Build a fresh per-request MCP client with one connection per configured server.

    Each server is either deployment- or direct-mode (see `MCPClientSettings`). Deployment
    mode builds the Core URL from `dial_url` and forwards the request bearer token (when
    present) as `Authorization: Bearer`; direct mode uses the server's `url` and static
    `api_key`.
    """
    connections: dict[str, Connection] = {}
    for server in mcp_servers:
        if server.deployment_id is not None:
            base = settings.dial_url.encoded_string().rstrip("/")
            url = f"{base}/v1/deployments/{server.deployment_id}/mcp"
            headers = {}
            if bearer_token:
                headers["Authorization"] = f"Bearer {bearer_token}"
        elif server.url is not None:
            url = server.url.encoded_string()
            api_key = server.api_key.get_secret_value() if server.api_key else ""
            headers = {"api-key": api_key}
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
    text as its result with `status="error"`; the researcher then receives it as a
    `ToolMessage` and can retry with corrected args.
    """
    for t in tools:
        t.handle_tool_error = True
    return tools


def build_finish_iteration_tool() -> BaseTool:
    """A no-op sentinel: the researcher calls it to end the current iteration.

    `return_direct=True` makes `create_agent` exit its loop right after this tool
    executes, so the iteration ends with no further model round-trip. It only signals
    completion — the graph (not this tool) decides whether to review or report.
    """

    @tool(return_direct=True)
    def finish_iteration() -> str:
        """Call this when you have finished researching the current plan.

        Signals that this research iteration is complete. Do not pass any arguments.
        """
        return FINISH_ITERATION_RESULT

    return finish_iteration


def _dump_tool_schemas_to_json(tools: list[BaseTool], dp: Path) -> None:
    if dp.exists():
        shutil.rmtree(dp)
    dp.mkdir(parents=True, exist_ok=False)
    for t in tools:
        fname = dp / f"{t.name}.json"
        with open(fname, "w") as f:
            json.dump(t.args_schema, f, indent=2, default=str, ensure_ascii=False)


async def load_research_tools(
    mcp_servers: list[MCPClientSettings], bearer_token: str | None = None
) -> list[BaseTool]:
    """Fetch the MCP tools, hoist their schemas, add the finish sentinel, wire error handling.

    Tools are fetched per server so each server's `tools_to_include` filter applies (an empty
    filter includes all of that server's tools).
    """
    mcp_client = build_mcp_client(mcp_servers, bearer_token=bearer_token)
    tools: list[BaseTool] = []
    for server in mcp_servers:
        server_tools = await mcp_client.get_tools(server_name=server.server_name)
        available = [t.name for t in server_tools]
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
                "MCP server '%s': fetched %d tool(s) %s; including all",
                server.server_name,
                len(available),
                available,
            )
        tools.extend(server_tools)
    logger.info("Loaded %d research tool(s) across %d MCP server(s)", len(tools), len(mcp_servers))

    # TODO: either remove or use envvar
    dump_tool_schemas = False
    if dump_tool_schemas:
        tool_schemas_base_dp = Path("data") / "tool_schemas" / datetime.now().isoformat()
        _dump_tool_schemas_to_json(tools, tool_schemas_base_dp / "raw")

    tools = hoist_defs_to_root(tools)
    tools.append(build_finish_iteration_tool())
    return enable_tool_error_handling(tools)
