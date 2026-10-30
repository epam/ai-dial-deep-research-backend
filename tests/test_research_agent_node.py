"""The research-agent node runs one iteration of the agent graph over the research state.

`create_agent` fixes the agent's conversation key as `messages`, so the node maps
`research_agent_messages` in and out and counts the iteration once the agent returns.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from dial_deep_research.app.history import CrossTurnPrepState, Plan
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.state import ResearchState, build_initial_state
from dial_deep_research.app.research.tools import build_finish_iteration_tool
from tests.mcp_fakes import BOTH_SOURCE_KINDS


class _FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


class _AbortError(Exception):
    """Raised by the fake model, as a quota error would be."""


@tool
def rag_search(query: str) -> str:
    """Search the documents."""
    return f"results for {query}"


def _search_then_finish() -> Iterator[AIMessage | Exception]:
    yield AIMessage(
        content="", tool_calls=[{"name": "rag_search", "args": {"query": "q"}, "id": "c1"}]
    )
    yield AIMessage(content="", tool_calls=[{"name": "finish_iteration", "args": {}, "id": "c2"}])


def _search_then_fail() -> Iterator[AIMessage | Exception]:
    yield AIMessage(
        content="", tool_calls=[{"name": "rag_search", "args": {"query": "q"}, "id": "c1"}]
    )
    raise _AbortError("the second model call fails")


def _search_forever() -> Iterator[AIMessage]:
    turn = 0
    while True:
        turn += 1
        yield AIMessage(
            content="",
            tool_calls=[{"name": "rag_search", "args": {"query": "q"}, "id": f"c{turn}"}],
        )


def _graph(monkeypatch: pytest.MonkeyPatch, script: Iterator[Any]) -> Any:
    """The real research-agent node as the only node of a graph over the research state."""
    monkeypatch.setattr(
        nodes, "get_chat_model", lambda model_config: _FakeToolCallingModel(messages=script)
    )
    agent = nodes.build_research_agent(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        tools=[rag_search, build_finish_iteration_tool()],
        today_date="2026-07-16",
        client_name="ACME",
        data_sources="The topics map.",
        data_sources_instructions="",
        glossary=None,
    )
    builder = StateGraph(ResearchState)
    builder.add_node(  # type: ignore[call-overload]
        node="research-agent", action=nodes.make_research_agent_node(agent)
    )
    builder.add_edge(start_key=START, end_key="research-agent")
    builder.add_edge(start_key="research-agent", end_key=END)
    return builder.compile()


def _initial_state(**overrides: Any) -> dict[str, Any]:
    prep = CrossTurnPrepState(
        current_query="How did inflation change?", plan=Plan(steps=["step one"])
    )
    return {**build_initial_state(prep), **overrides}


async def test_an_iteration_is_counted_when_it_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _graph(monkeypatch, _search_then_finish())

    final = await graph.ainvoke(_initial_state(research_iteration=4))

    assert final["research_iteration"] == 5


async def test_the_agents_conversation_comes_back_as_research_agent_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph(monkeypatch, _search_then_finish())

    final = await graph.ainvoke(_initial_state())

    messages = final["research_agent_messages"]
    assert isinstance(messages[0], HumanMessage)
    assert [type(m) for m in messages[1:]] == [AIMessage, ToolMessage, AIMessage, ToolMessage]
    assert messages[2].content == "results for q"


async def test_the_agents_stream_parts_keep_their_namespace_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner reads research-agent's own parts under `research-agent:<task id>` and the key
    `messages`; running the agent inside a node function keeps both."""
    graph = _graph(monkeypatch, _search_then_finish())

    parts = [
        part
        async for part in graph.astream(
            _initial_state(),
            stream_mode=["updates", "values", "tasks"],
            subgraphs=True,
            version="v2",
        )
    ]

    agent_parts = [part for part in parts if part["ns"]]
    assert agent_parts
    assert all(
        len(part["ns"]) == 1 and part["ns"][0].startswith("research-agent:") for part in agent_parts
    )
    agent_values = [part["data"] for part in agent_parts if part["type"] == "values"]
    assert agent_values and all("messages" in data for data in agent_values)
    # The first one arrives as the iteration starts, holding its input.
    assert len(agent_values[0]["messages"]) == 1
    agent_updates = [part["data"] for part in agent_parts if part["type"] == "updates"]
    assert any("messages" in update for data in agent_updates for update in data.values() if update)
    root_values = [part["data"] for part in parts if not part["ns"] and part["type"] == "values"]
    assert all("messages" not in data for data in root_values)


async def test_a_failure_inside_the_iteration_leaves_the_count_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph(monkeypatch, _search_then_fail())
    root_states: list[dict[str, Any]] = []

    with pytest.raises(_AbortError):
        async for part in graph.astream(
            _initial_state(research_iteration=2), stream_mode="values", version="v2"
        ):
            root_states.append(part["data"])

    assert [state["research_iteration"] for state in root_states] == [2]


async def test_the_step_budget_bounds_the_agents_own_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`recursion_limit` applies to each graph run: the agent's run inside the node exhausts it,
    though the research graph itself takes only one step."""
    graph = _graph(monkeypatch, _search_forever())

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(_initial_state(), config={"recursion_limit": 6})
