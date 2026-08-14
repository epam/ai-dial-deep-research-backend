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

# The two rules the tool can catch the model breaking. Each is written once here and used in
# three places — the research-agent system prompt, this tool's description, and the corrective
# note in its response — so the model never meets the same rule in two different wordings.
RULE_ONCE_PER_TURN = (
    f"Never call {UPDATE_STATUS_TOOL_NAME} more than once in one turn. If several lines of work"
    " start at once, name them all in a single status."
)
RULE_NEVER_ALONE = (
    f"Never make {UPDATE_STATUS_TOOL_NAME} the only tool call of a turn. Always call it together"
    " with at least one other tool, normally the first tool call of the step it announces."
)
# Not catchable in the tool's own response: by the time it runs, the iteration is already ending.
RULE_NOT_WITH_FINISH = (
    f"Never call {UPDATE_STATUS_TOOL_NAME} together with {FINISH_TOOL_NAME}. Ending the iteration"
    " is not a step to announce."
)

UPDATE_STATUS_RESULT = "Status shown to the user."
_MISUSE_PREFIX = "You used this tool incorrectly."

# When to announce, written once and used both here and in the research-agent system prompt.
# Deliberately says nothing about what the steps should be: the model must follow its prompt, so
# any illustration of a sequence of steps would be read as a research method to imitate.
WHEN_TO_ANNOUNCE = """\
Announce a new step whenever the work you are about to do is no longer what the status now on
screen describes. One iteration normally passes through several such steps, and each one deserves
its own status.

Do not leave one status standing over a long run of tool calls. The user reads it as what you are
doing at this moment, so a line that has stopped matching the work misleads — a rough status that
is current beats a precise one that is stale. A single status covering a whole iteration is far
too few.

How you investigate is entirely yours to decide. This governs only how often you say what you are
doing, never what you do."""

# How to word a status, written once and used both here and in the research-agent system prompt.
HOW_TO_WRITE_STATUS = """\
Write the step you are starting in five to eight words, and never more than twenty — the user
reads it on one narrow line. Good statuses look like "Looking for US GDP forecasts" or "Searching
for latest risks to economic outlook"."""

_UPDATE_STATUS_DESCRIPTION = f"""\
Tell the user what you are working on right now. Each status replaces the one before it.

{HOW_TO_WRITE_STATUS}

{WHEN_TO_ANNOUNCE}

Rules:
- {RULE_ONCE_PER_TURN}
- {RULE_NEVER_ALONE}
- {RULE_NOT_WITH_FINISH}
"""


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
    batch the model asked for in this turn.
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
    def update_status(status: str, state: Annotated[dict[str, Any], InjectedState]) -> str:
        broken = _broken_rules(state.get("messages") or [])
        if not broken:
            return UPDATE_STATUS_RESULT
        return " ".join([UPDATE_STATUS_RESULT, _MISUSE_PREFIX, *broken])

    return update_status
