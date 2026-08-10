"""Middleware that ends the preparation agent's run the moment research starts.

`start_research` sets `PrepState.research_started`. Without this, `create_agent` routes from the
tool result back to the model, which writes a closing message ("research is starting") into the
same assistant content the report is about to fill — so the launch turn's answer would not be the
report alone.

Keying on `research_started` rather than on the tool call is what keeps a **rejected**
`start_research` working: the gate leaves the flag false, the loop continues to the model, and the
agent tells the user what is still missing. (This is why `@tool(return_direct=True)` is not used —
it is decided by the tool's static attribute, with the result's error status never consulted, so it
would end the turn with no answer at all.)

One case is outside this guarantee, knowingly: text the model emits on the *same* assistant message
that calls `start_research` has already been streamed by the time the tool runs, and DIAL content
cannot be retracted. The preparation prompt does not ask for such a message, which is the only
guard against it.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langgraph.runtime import Runtime

from dial_deep_research.app.history import PrepState


class StopAfterResearchStartMiddleware(AgentMiddleware):
    """Jump to the end of the agent loop once research has been marked as started."""

    def __init__(self, state: PrepState) -> None:
        super().__init__()
        self._state = state

    # `can_jump_to` is required, not decorative: without it the middleware node's conditional
    # edge gets no END destination and the returned `jump_to` is silently ignored.
    @hook_config(can_jump_to=["end"])
    def before_model(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:
        if self._state.research_started:
            return {"jump_to": "end"}
        return None
