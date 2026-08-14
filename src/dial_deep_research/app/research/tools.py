"""Research-specific tools: the finish sentinel that ends an iteration, and the status tool.

MCP tool loading is shared across agents and lives in `app/mcp_tools.py`.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState

FINISH_ITERATION_RESULT = "Research iteration complete; handing off to the research review."

FINISH_TOOL_NAME = "finish_iteration"
UPDATE_STATUS_TOOL_NAME = "update_status"

# The two rules the tool can catch the model breaking. They live here because `_broken_rules`
# quotes them back verbatim in the corrective response, and the research-agent system prompt renders
# these same strings — so the correction the model reads is word for word the rule it broke. The
# prompt states the remaining status rules itself, having no second reader.
RULE_ONCE_PER_TURN = (
    f"Never call {UPDATE_STATUS_TOOL_NAME} more than once in one turn. If several lines of work"
    " start at once, name them all in a single status."
)
RULE_NEVER_ALONE = (
    f"Never make {UPDATE_STATUS_TOOL_NAME} the only tool call of a turn. Always call it together"
    " with at least one other tool, normally the first tool call of the step it announces."
)

UPDATE_STATUS_RESULT = "Status shown to the user."
_MISUSE_PREFIX = "You used this tool incorrectly."

# The `status` argument's own description: what to write in it. It documents the argument, so it
# travels with the argument rather than sitting in the prompt — the model reads it where it fills
# the value in.
HOW_TO_WRITE_STATUS = """\
Write the step you are starting in five to eight words, and never more than twenty — the user
reads it on one narrow line. Good statuses look like "Looking for US GDP forecasts" or "Searching
for latest risks to economic outlook"."""

_UPDATE_STATUS_DESCRIPTION = """\
Tell the user what you are working on right now. Each status replaces the one before it."""


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


def _broken_rules(messages: list[BaseMessage]) -> list[str]:
    """The rules the calling assistant message broke, judged from its own tool calls.

    The last message is the `AIMessage` carrying this call, so its `tool_calls` are the whole
    batch the model asked for in this turn. Calling the status tool together with the finish
    sentinel is not judged here: by the time this runs the iteration is already ending, so a
    correction would arrive with nowhere to apply it.
    """
    tool_calls = getattr(messages[-1], "tool_calls", []) if messages else []
    if not tool_calls:
        return []
    status_calls = [tc for tc in tool_calls if tc["name"] == UPDATE_STATUS_TOOL_NAME]
    broken = []
    if len(status_calls) > 1:
        broken.append(RULE_ONCE_PER_TURN)
    if len(status_calls) == len(tool_calls):
        broken.append(RULE_NEVER_ALONE)
    return broken


def build_update_status_tool() -> BaseTool:
    """Lets research-agent tell the user what it is doing; the runner renders it as a stage.

    The tool itself shows nothing: it reports the call, and `ResearchRunner` turns it into the
    open activity stage. That split lets the runner see the whole tool-call batch of one
    message, which is what the "at most one status, never alone, never with the finish
    sentinel" rules are judged against.

    The injected state is only read to answer the model when it broke one of those rules. It
    holds the assistant message carrying this call, so the call's siblings are visible here.
    """

    @tool(UPDATE_STATUS_TOOL_NAME, description=_UPDATE_STATUS_DESCRIPTION)
    def update_status(
        status: Annotated[str, HOW_TO_WRITE_STATUS],
        state: Annotated[dict[str, Any], InjectedState],
    ) -> str:
        broken = _broken_rules(state.get("messages") or [])
        if not broken:
            return UPDATE_STATUS_RESULT
        return " ".join([UPDATE_STATUS_RESULT, _MISUSE_PREFIX, *broken])

    return update_status
