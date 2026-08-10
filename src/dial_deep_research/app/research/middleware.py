"""Research-agent-specific middleware: forced tool choice, and the iteration counter.

Shared middleware (the image budget) lives in `app/middleware.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, ModelRequest, ModelResponse
from langgraph.runtime import Runtime


class ForceToolChoiceMiddleware(AgentMiddleware):
    """Re-issue every model call with `tool_choice="any"`.

    `create_agent` always calls the model with `tool_choice=None`. We override that to
    `"any"` so research-agent can never emit a free-form assistant message — every step
    is either an MCP tool call or `finish_iteration`. This removes any path for the model
    to write a premature summary or report; the report is a separate node.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        return await handler(request.override(tool_choice="any"))


class _AgentStateWithIterationCounter(AgentState):
    research_iteration: int


class IterationCounterMiddleware(AgentMiddleware):
    """Count the just-finished iteration in the research graph's `research_iteration` channel.

    The node that does the work records the count — the research loop's mirror of the report
    node recording `report_version`. Research-agent is the `create_agent` graph used directly
    as a subgraph node, so the counting happens here, in `after_agent`, which runs once per
    node run, when the iteration has finished
    (https://docs.langchain.com/oss/python/langchain/middleware/custom — the hooks table and
    "Custom state schema").

    `state_schema` is what lets the hook see the counter at all. The agent graph is a graph of
    its own, not part of the research graph, and a subgraph is isolated: whatever the parent
    state holds, the subgraph receives only the keys in its own input schema, keeps only its
    own declared channels, and hands back only its output schema. Declaring
    `research_iteration` here puts the channel in all three, and langgraph then maps it to the
    research graph's same-named channel at the node boundary: the parent's count flows in, the
    hook increments it, the result flows back
    (https://docs.langchain.com/oss/python/langgraph/use-subgraphs#add-a-subgraph-as-a-node —
    "the subgraph reads from and writes to the parent's state channels automatically").
    Without the declaration the hook's state simply has no such key, no matter what
    `ResearchState` declares.

    Sync-only is deliberate: the hook is pure in-memory work, and langgraph's node wrapper
    falls back to the sync fn on async runs.
    """

    state_schema = _AgentStateWithIterationCounter

    def after_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        return {"research_iteration": state["research_iteration"] + 1}
