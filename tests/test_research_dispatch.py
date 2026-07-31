"""ResearchRunner streaming-dispatch unit tests.

Exercise the routing logic without a live graph: only the report node's tokens
become content, researcher tool calls become stages (finish_iteration excluded),
reviewer-injected plans are not shown, and messages arriving twice (from the
subgraph and the parent aggregate) are processed once.

Persistence is a separate path — the slice comes from the root `values` parts, not
from the updates that drive the live output.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import ValuesStreamPart
from pytest import MonkeyPatch

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import runner as runner_module
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app_properties import ApplicationProperties


class _StageSpy:
    def __init__(self) -> None:
        self.body = ""

    def append_content(self, text: str) -> None:
        self.body += text


class _ChoiceSpy:
    def __init__(self) -> None:
        self.content = ""
        self.stage_titles: list[str] = []
        self.stages: list[_StageSpy] = []

    def append_content(self, text: str) -> None:
        self.content += text

    @contextmanager
    def create_stage(self, title: str) -> Any:
        self.stage_titles.append(title)
        stage = _StageSpy()
        self.stages.append(stage)
        yield stage


def _make_runner() -> tuple[ResearchRunner, _ChoiceSpy]:
    choice = _ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]
    return runner, choice


def test_only_report_node_chunks_become_content() -> None:
    runner, choice = _make_runner()
    runner._handle_message_chunk(
        AIMessageChunk(content="report text"), {"langgraph_node": "report"}
    )
    runner._handle_message_chunk(AIMessageChunk(content="reasoning"), {"langgraph_node": "model"})
    runner._handle_message_chunk(AIMessageChunk(content="verdict"), {"langgraph_node": "reviewer"})
    # First report chunk is prefixed with a separator (separates from preparation text).
    assert choice.content == "\n\nreport text"


def test_research_tool_call_emits_stage_finish_iteration_does_not() -> None:
    runner, choice = _make_runner()
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "rag_search", "args": {"q": "x"}, "id": "call_1"},
            {"name": "finish_iteration", "args": {}, "id": "call_2"},
        ],
    )
    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates(
        {"tools": {"messages": [ToolMessage(content="hits", tool_call_id="call_1")]}}
    )
    runner._handle_updates(
        {"tools": {"messages": [ToolMessage(content="done", tool_call_id="call_2")]}}
    )
    assert len(choice.stage_titles) == 1
    assert 'rag_search' in choice.stage_titles[0]
    assert all("finish_iteration" not in t for t in choice.stage_titles)


def test_injected_plan_is_not_shown() -> None:
    runner, choice = _make_runner()
    runner._handle_updates({"reviewer": {"messages": [HumanMessage(content="next plan")]}})
    assert choice.content == ""


def test_duplicate_messages_processed_once() -> None:
    runner, choice = _make_runner()
    tool_msg = ToolMessage(content="hits", tool_call_id="call_1", id="tm1")
    ai = AIMessage(
        content="", tool_calls=[{"name": "rag_search", "args": {}, "id": "call_1"}], id="am1"
    )
    # Same messages arrive from the leaf subgraph update and the parent aggregate.
    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates({"tools": {"messages": [tool_msg]}})
    runner._handle_updates({"researcher": {"messages": [ai, tool_msg]}})
    assert len(choice.stage_titles) == 1


def test_substituted_result_adds_no_stage() -> None:
    """The drop is a model-context concern; the stage keeps what the tool returned."""
    runner, choice = _make_runner()
    ai = AIMessage(
        content="", tool_calls=[{"name": "get_page", "args": {}, "id": "call_1"}], id="am1"
    )
    original = ToolMessage(content="page text", tool_call_id="call_1", id="tm1")
    substituted = ToolMessage(content="dropped", tool_call_id="call_1", id="tm1", status="error")
    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates({"tools": {"messages": [original]}})
    runner._handle_updates({"ImageBudget.before_model": {"messages": [substituted]}})
    assert len(choice.stages) == 1
    assert "page text" in choice.stages[0].body
    assert "dropped" not in choice.stages[0].body


def _values(messages: list[Any], ns: tuple[str, ...] = ()) -> ValuesStreamPart[Any]:
    """A `stream_mode="values"` part as the graph emits it under `version="v2"`."""
    return ValuesStreamPart(type="values", ns=ns, data={"messages": messages}, interrupts=())


def test_persisted_slice_comes_from_the_last_root_values() -> None:
    """Each root `values` part replaces the slice, so the final state is what persists."""
    runner, _ = _make_runner()
    first = [HumanMessage(content="q"), AIMessage(content="a")]
    final = [*first, HumanMessage(content="plan 2"), AIMessage(content="the report")]
    runner._handle_part(_values(first))
    runner._handle_part(_values(final))
    assert runner._messages == final


def test_subgraph_values_do_not_overwrite_the_persisted_slice() -> None:
    """A subgraph's state has no reviewer or report messages — only the root's counts."""
    runner, _ = _make_runner()
    root = [HumanMessage(content="q"), AIMessage(content="the report")]
    runner._handle_part(_values(root))
    runner._handle_part(_values([HumanMessage(content="q")], ns=("researcher:abc",)))
    assert runner._messages == root


def _properties(**overrides: Any) -> ApplicationProperties:
    return ApplicationProperties.model_validate(
        {
            "prompts": {
                "client_name": "Test Corp",
                "agent_name": "Test Deep Research",
                "data_sources_descriptions": "## report\n\nA report.",
            },
            "mcp_servers": [{"server_name": "rag", "deployment_id": "generic-rag-mcp"}],
            **overrides,
        }
    )


def _approved_prep_state() -> PrepState:
    return PrepState(
        current_query="q", plan=Plan(steps=["step"]), plan_approved=True, research_started=True
    )


class _GraphStub:
    """Stands in for the compiled graph, recording the config it was invoked with."""

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    async def astream(self, _state: Any, **kwargs: Any) -> AsyncIterator[Any]:
        self._captured["config"] = kwargs["config"]
        for _ in ():  # empty stream: the dispatch paths are covered above
            yield


def _stub_graph_build(monkeypatch: MonkeyPatch, captured: dict[str, Any]) -> None:
    async def _no_tools(**_kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(runner_module, "load_mcp_tools", _no_tools)
    monkeypatch.setattr(runner_module, "build_research_graph", lambda **_kw: _GraphStub(captured))


async def test_step_budget_comes_from_the_channel_properties(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _stub_graph_build(monkeypatch, captured)
    runner, _ = _make_runner()

    await runner.run(_approved_prep_state(), properties=_properties(max_research_graph_steps=42))

    assert captured["config"]["recursion_limit"] == 42


async def test_step_budget_defaults_to_500(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _stub_graph_build(monkeypatch, captured)
    runner, _ = _make_runner()

    await runner.run(_approved_prep_state(), properties=_properties())

    assert captured["config"]["recursion_limit"] == 500


def test_substituted_message_reaches_the_persisted_slice() -> None:
    """An in-place edit is invisible in `updates` but present in the final state.

    The image-budget middleware replaces a tool result under its original id; the
    original arrives first from the subgraph, so replaying updates would keep it.
    """
    runner, _ = _make_runner()
    original = ToolMessage(content=[{"type": "image"}], tool_call_id="call_1", id="tm1")
    substituted = ToolMessage(content="dropped", tool_call_id="call_1", id="tm1", status="error")
    runner._handle_updates({"tools": {"messages": [original]}})
    runner._handle_updates({"ImageBudget.before_model": {"messages": [substituted]}})
    runner._handle_part(_values([substituted]))
    assert runner._messages == [substituted]
