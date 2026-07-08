"""Tools for the research graph: MCP-loaded research tools + the finish sentinel.

The MCP-client construction and tool preparation (schema hoisting, error handling)
move here from the retired `app/agent.py` so the researcher node can reuse them.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from langchain_core.tools import BaseTool, tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.settings import settings
from dial_deep_research.utils.json_schema_fixes import hoist_defs_to_root

FINISH_ITERATION_RESULT = "Research iteration complete; handing off to the reviewer."


def build_mcp_client() -> MultiServerMCPClient:
    """Build a fresh per-request MCP client for the generic-RAG server."""
    return MultiServerMCPClient(
        connections={
            settings.mcp_server_name: {
                "transport": "streamable_http",
                "url": settings.mcp_url.encoded_string(),
                "headers": {"api-key": settings.mcp_api_key.get_secret_value()},
            }
        }
    )


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


async def load_research_tools() -> list[BaseTool]:
    """Fetch the MCP tools, hoist their schemas, add the finish sentinel, wire error handling."""
    mcp_client = build_mcp_client()
    tools = await mcp_client.get_tools()

    # TODO: either remove or use envvar
    dump_tool_schemas = False
    if dump_tool_schemas:
        tool_schemas_base_dp = Path("data") / "tool_schemas" / datetime.now().isoformat()
        _dump_tool_schemas_to_json(tools, tool_schemas_base_dp / "raw")

    tools = hoist_defs_to_root(tools)
    tools.append(build_finish_iteration_tool())
    return enable_tool_error_handling(tools)
