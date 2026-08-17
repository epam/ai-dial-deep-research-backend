"""The activity stage: one open stage naming what research is doing right now.

Every other stage the app emits is written once its result is in and closes in the same breath.
This one opens before the work and is replaced by the next announcement, so what these tests pin
down is its lifecycle: exactly one open at a time, a close that claims nothing about the work
having finished, and none left behind when the turn ends.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from aidial_sdk.chat_completion import Status
from langchain_core.messages import AIMessage, ToolMessage
from pytest import MonkeyPatch

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research import runner as runner_module
from dial_deep_research.app.research.runner import _INITIAL_ACTIVITY, ResearchRunner
from dial_deep_research.app.research.state import build_initial_state
from dial_deep_research.app_properties import DEFAULT_REPORT_STRUCTURE, ApplicationProperties
from tests.dial_spies import ChoiceSpy

_STATUS = "update_status"


def _make_runner() -> tuple[ResearchRunner, ChoiceSpy]:
    choice = ChoiceSpy()
    return ResearchRunner(choice), choice  # type: ignore[arg-type]


def _status_call(text: str, call_id: str) -> dict[str, Any]:
    return {"name": _STATUS, "args": {"status": text}, "id": call_id}


def _properties() -> ApplicationProperties:
    return ApplicationProperties.model_validate(
        {
            "prompts": {
                "client_name": "Test Corp",
                "agent_name": "Test Deep Research",
                "data_sources_descriptions": "## report\n\nA report.",
            },
            "mcp_servers": [{"server_name": "rag", "deployment_id": "generic-rag-mcp"}],
        }
    )


def _approved_prep_state() -> PrepState:
    return PrepState(
        current_query="q", plan=Plan(steps=["step"]), plan_approved=True, research_started=True
    )


def test_a_status_opens_a_stage_and_leaves_it_open() -> None:
    runner, choice = _make_runner()
    ai = AIMessage(content="", tool_calls=[_status_call("Looking for US GDP forecasts", "c1")])

    runner._handle_updates({"model": {"messages": [ai]}})

    [stage] = choice.stages
    assert stage.title == "Looking for US GDP forecasts"
    assert stage.opened and not stage.closed


def test_the_next_status_closes_the_previous_one() -> None:
    runner, choice = _make_runner()
    first = AIMessage(content="", tool_calls=[_status_call("Looking for forecasts", "c1")], id="a1")
    second = AIMessage(
        content="", tool_calls=[_status_call("Checking 2022 figures", "c2")], id="a2"
    )

    runner._handle_updates({"model": {"messages": [first]}})
    runner._handle_updates({"model": {"messages": [second]}})

    assert choice.stage_titles == ["Looking for forecasts", "Checking 2022 figures"]
    assert choice.stages[0].status is Status.COMPLETED
    assert choice.open_stages == [choice.stages[1]]


def test_a_closed_status_stage_keeps_its_title_and_stays_empty() -> None:
    """No elapsed time, no body. The stage ends because a new step began, not because the
    announced work finished, so a duration would claim something untrue."""
    runner, choice = _make_runner()
    first = AIMessage(
        content="", tool_calls=[_status_call("Reading capacity tables", "c1")], id="1"
    )
    second = AIMessage(content="", tool_calls=[_status_call("Comparing with 2022", "c2")], id="2")

    runner._handle_updates({"model": {"messages": [first]}})
    runner._handle_updates({"model": {"messages": [second]}})

    assert choice.stages[0].title == "Reading capacity tables"
    assert choice.stages[0].body == ""


def test_a_status_stage_stays_open_across_the_tool_stages_it_covers() -> None:
    runner, choice = _make_runner()
    ai = AIMessage(
        content="",
        tool_calls=[
            _status_call("Looking for US GDP forecasts", "c1"),
            {"name": "rag_search", "args": {"q": "gdp"}, "id": "c2"},
        ],
        id="a1",
    )

    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates(
        {"tools": {"messages": [ToolMessage(content="hits", tool_call_id="c2")]}}
    )

    status_stage, tool_stage = choice.stages
    assert status_stage.opened and not status_stage.closed
    assert tool_stage.closed
    assert "rag_search" in tool_stage.title
    # The tool stage opened and closed inside the status stage's lifetime.
    assert choice.events == [
        ("open", "Looking for US GDP forecasts"),
        ("open", tool_stage.title),
        ("close", tool_stage.title),
    ]


def test_the_status_tool_gets_no_result_stage() -> None:
    runner, choice = _make_runner()
    ai = AIMessage(content="", tool_calls=[_status_call("Reading the 2023 annex", "c1")], id="a1")

    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates(
        {"tools": {"messages": [ToolMessage(content="ok", tool_call_id="c1", name=_STATUS)]}}
    )

    assert choice.stage_titles == ["Reading the 2023 annex"]


def test_two_statuses_in_one_message_make_one_stage() -> None:
    """Applying them in turn would close the first an instant after opening it, which reads as
    a step that finished."""
    runner, choice = _make_runner()
    ai = AIMessage(
        content="",
        tool_calls=[
            _status_call("Looking for GDP forecasts", "c1"),
            _status_call("Checking inflation data", "c2"),
        ],
        id="a1",
    )

    runner._handle_updates({"model": {"messages": [ai]}})

    assert choice.stage_titles == ["Looking for GDP forecasts; Checking inflation data"]
    assert choice.flashed_stages() == []


def test_a_status_sent_with_the_finish_sentinel_changes_nothing() -> None:
    runner, choice = _make_runner()
    runner._set_activity("Reading the annex")
    ai = AIMessage(
        content="",
        tool_calls=[
            _status_call("Wrapping up the iteration", "c1"),
            {"name": "finish_iteration", "args": {}, "id": "c2"},
        ],
        id="a1",
    )

    runner._handle_updates({"model": {"messages": [ai]}})

    assert choice.stage_titles == ["Reading the annex"]
    assert choice.open_stages == [choice.stages[0]]


def test_a_status_only_message_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    runner, _ = _make_runner()
    ai = AIMessage(content="", tool_calls=[_status_call("Reading the annex", "c1")], id="a1")

    with caplog.at_level("WARNING"):
        runner._handle_updates({"model": {"messages": [ai]}})

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "only tool call" in warnings[0].getMessage()
    # The status text is a tool-call argument value, which no record may carry.
    assert "Reading the annex" not in caplog.text


def test_repeated_statuses_warn_once_for_the_message(caplog: pytest.LogCaptureFixture) -> None:
    runner, _ = _make_runner()
    ai = AIMessage(
        content="",
        tool_calls=[
            _status_call("One", "c1"),
            _status_call("Two", "c2"),
            _status_call("Three", "c3"),
        ],
        id="a1",
    )

    with caplog.at_level("WARNING"):
        runner._handle_updates({"model": {"messages": [ai]}})

    assert len([r for r in caplog.records if "more than once" in r.getMessage()]) == 1


def test_correct_usage_warns_about_nothing(caplog: pytest.LogCaptureFixture) -> None:
    runner, _ = _make_runner()
    ai = AIMessage(
        content="",
        tool_calls=[
            _status_call("Looking for forecasts", "c1"),
            {"name": "rag_search", "args": {}, "id": "c2"},
        ],
        id="a1",
    )

    with caplog.at_level("WARNING"):
        runner._handle_updates({"model": {"messages": [ai]}})

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []


class _EmptyGraph:
    async def astream(self, _state: Any, **_kwargs: Any) -> AsyncIterator[Any]:
        for _ in ():
            yield


class _FailingGraph:
    async def astream(self, _state: Any, **_kwargs: Any) -> AsyncIterator[Any]:
        raise RuntimeError("the graph blew up")
        yield  # pragma: no cover - makes this an async generator


def _stub_graph(monkeypatch: MonkeyPatch, graph: Any) -> None:
    async def _no_tools(**_kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(runner_module, "load_mcp_tools", _no_tools)
    monkeypatch.setattr(runner_module, "build_research_graph", lambda **_kw: graph)


async def test_a_stage_is_open_before_the_graph_runs(monkeypatch: MonkeyPatch) -> None:
    """Otherwise the first model call of the turn would say nothing at all."""
    _stub_graph(monkeypatch, _EmptyGraph())
    runner, choice = _make_runner()

    await runner.run(_approved_prep_state(), properties=_properties())

    assert choice.stage_titles == [_INITIAL_ACTIVITY]


async def test_a_finished_run_leaves_no_stage_open(monkeypatch: MonkeyPatch) -> None:
    _stub_graph(monkeypatch, _EmptyGraph())
    runner, choice = _make_runner()

    await runner.run(_approved_prep_state(), properties=_properties())

    assert choice.open_stages == []
    assert choice.stages[0].status is Status.COMPLETED


async def test_a_failing_run_closes_the_stage_and_keeps_the_error(monkeypatch: MonkeyPatch) -> None:
    """An unclosed stage reaches the client with no status and spins there for good."""
    _stub_graph(monkeypatch, _FailingGraph())
    runner, choice = _make_runner()

    with pytest.raises(RuntimeError, match="the graph blew up"):
        await runner.run(_approved_prep_state(), properties=_properties())

    assert choice.open_stages == []
    assert choice.stages[0].status is Status.FAILED


def _research_state() -> dict[str, Any]:
    return dict(build_initial_state(_approved_prep_state()))


def _no_model(monkeypatch: MonkeyPatch) -> None:
    """Make any model call fail, so only what a node does *before* calling one can succeed."""

    def _boom(_model_config: Any) -> Any:
        raise RuntimeError("no model in this test")

    monkeypatch.setattr(nodes, "get_chat_model", _boom)


async def test_research_review_names_its_work_before_calling_a_model(
    monkeypatch: MonkeyPatch,
) -> None:
    _no_model(monkeypatch)
    seen: list[str] = []
    node = nodes.make_research_review_node(
        today_date="2026-08-14",
        max_research_iterations=10,
        emit_result_stage=lambda _outcome: None,
        emit_activity=seen.append,
    )

    with pytest.raises(RuntimeError):
        await node(_research_state())  # type: ignore[arg-type]

    assert seen == [nodes.RESEARCH_REVIEW_ACTIVITY]


async def test_the_report_node_names_its_work_before_calling_a_model(
    monkeypatch: MonkeyPatch,
) -> None:
    _no_model(monkeypatch)
    seen: list[str] = []
    node = nodes.make_report_node(
        today_date="2026-08-14",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        emit_revision_failed_stage=lambda _outcome: None,
        emit_activity=seen.append,
    )

    with pytest.raises(RuntimeError):
        await node(_research_state())  # type: ignore[arg-type]

    assert seen == [nodes.REPORT_ACTIVITY]


async def test_report_review_names_its_work_before_calling_a_model(
    monkeypatch: MonkeyPatch,
) -> None:
    _no_model(monkeypatch)
    seen: list[str] = []
    node = nodes.make_report_review_node(
        today_date="2026-08-14",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        emit_result_stage=lambda _outcome: None,
        emit_activity=seen.append,
    )

    # This node absorbs a failing review call rather than failing the turn, so it returns.
    await node(_research_state())  # type: ignore[arg-type]

    assert seen == [nodes.REPORT_REVIEW_ACTIVITY]
