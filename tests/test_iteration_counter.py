"""The research-agent node counts its own iterations.

`research_iteration` is a channel of the research graph, and research-agent is the
`create_agent` graph used directly as a subgraph node: `IterationCounterMiddleware.state_schema`
shares the channel with the agent graph, and `after_agent` increments it once per node run. The
gate out of research-agent therefore reads a count that includes the just-finished iteration —
the last permitted one too, which research-review never sees.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.state import ResearchState, build_initial_state
from dial_deep_research.app.research.tools import build_finish_iteration_tool


class _FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def _finish_immediately() -> Iterator[AIMessage]:
    while True:
        yield AIMessage(
            content="", tool_calls=[{"name": "finish_iteration", "args": {}, "id": "call_1"}]
        )


def _one_iteration_graph(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The real research-agent as the only node of a graph over the research state."""
    monkeypatch.setattr(
        nodes,
        "get_chat_model",
        lambda model_config: _FakeToolCallingModel(messages=_finish_immediately()),
    )
    agent = nodes.build_research_agent(
        tools=[build_finish_iteration_tool()], today_date="2026-07-16", client_name="ACME"
    )
    builder = StateGraph(ResearchState)
    builder.add_node(node="research-agent", action=agent)
    builder.add_edge(start_key=START, end_key="research-agent")
    builder.add_edge(start_key="research-agent", end_key=END)
    return builder.compile()


def _initial_state() -> dict[str, Any]:
    prep = PrepState(current_query="q", plan=Plan(steps=["step one"]))
    return dict(build_initial_state(prep))


async def test_the_first_iteration_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _one_iteration_graph(monkeypatch)

    final = await graph.ainvoke(_initial_state())

    assert final["research_iteration"] == 1


async def test_the_count_flows_through_the_subgraph_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent's value is read and written back, not recomputed from an agent-local default."""
    graph = _one_iteration_graph(monkeypatch)

    final = await graph.ainvoke({**_initial_state(), "research_iteration": 4})

    assert final["research_iteration"] == 5
