"""Research-specific tools: the finish sentinel research-agent uses to end an iteration.

MCP tool loading is shared across agents and lives in `app/mcp_tools.py`.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

FINISH_ITERATION_RESULT = "Research iteration complete; handing off to the research review."


def build_finish_iteration_tool() -> BaseTool:
    """A no-op sentinel: research-agent calls it to end the current iteration.

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
