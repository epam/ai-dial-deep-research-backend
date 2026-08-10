"""The silent hand-off from preparation to research.

`StopAfterResearchStartMiddleware` ends the preparation agent's loop once `start_research`
succeeded, so the launch turn's answer is the report alone. Two invariants:

- it jumps only on `PrepState.research_started`, so a **rejected** `start_research` (the gate
  leaves the flag false) still returns to the model and the agent answers the user;
- its `before_model` hook declares `can_jump_to=["end"]`. Without that declaration the agent
  graph gives the middleware node no END destination and the returned `jump_to` is ignored —
  `langchain.agents.factory._get_can_jump_to` is what reads it while compiling the graph.
"""

from __future__ import annotations

from langchain.agents.factory import _get_can_jump_to

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.preparation.middleware import StopAfterResearchStartMiddleware


def _prep_state(*, research_started: bool) -> PrepState:
    return PrepState(
        current_query="q",
        plan=Plan(steps=["step"]),
        plan_approved=True,
        research_started=research_started,
    )


def test_started_research_jumps_to_the_end_of_the_agent_loop() -> None:
    middleware = StopAfterResearchStartMiddleware(_prep_state(research_started=True))
    assert middleware.before_model({}, None) == {"jump_to": "end"}  # type: ignore[arg-type]


def test_an_approved_plan_alone_does_not_end_the_loop() -> None:
    # `start_research` was not called (or its gate rejected the call): the model runs again and
    # replies to the user.
    middleware = StopAfterResearchStartMiddleware(_prep_state(research_started=False))
    assert middleware.before_model({}, None) is None  # type: ignore[arg-type]


def test_the_hook_declares_that_it_can_jump_to_the_end() -> None:
    middleware = StopAfterResearchStartMiddleware(_prep_state(research_started=True))
    assert _get_can_jump_to(middleware, "before_model") == ["end"]
