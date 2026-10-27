"""The preparation tools: their LLM calls' log records and the state they write.

`update_query` and `approve_plan` each make one system+human call to check clarity or
approval, and log a message count alongside duration and token usage (logging-policy spec).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.runnables import Runnable, RunnableLambda

from dial_deep_research.app.history import Clarification, Plan, PrepState
from dial_deep_research.app.preparation import tools as tools_module
from dial_deep_research.app.preparation.prompts import (
    FAILED_TURN_NOTE,
    PlanReviewResponse,
    QueryReviewResponse,
)
from dial_deep_research.app.preparation.tools import PrepTools

pytestmark = pytest.mark.asyncio

_LOGGER_NAME = tools_module.__name__


class _FakeStructuredLLM:
    """Stands in for `get_chat_model(...).with_structured_output(...)`."""

    def __init__(self, parsed: Any) -> None:
        self._parsed = parsed

    def with_structured_output(
        self, schema: type[Any], *, include_raw: bool = False
    ) -> Runnable[Any, Any]:
        async def call(messages: list[Any]) -> dict[str, Any]:
            from langchain_core.messages import AIMessage

            return {"parsed": self._parsed, "parsing_error": None, "raw": AIMessage(content="")}

        return RunnableLambda(call)


def _runtime(messages: list[Any] | None = None) -> Any:
    return SimpleNamespace(state={"messages": messages or []})


async def test_query_clarity_checked_logs_the_message_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    parsed = QueryReviewResponse(assessment="Settled.", questions=[])
    monkeypatch.setattr(
        tools_module, "get_chat_model", lambda model_config: _FakeStructuredLLM(parsed)
    )
    prep_tools = PrepTools(PrepState(), today_date="2026-08-21", data_sources="publications")
    update_query = prep_tools.build()[0]
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)

    await update_query.coroutine(query="What happened to inflation?", runtime=_runtime())

    [record] = caplog.records
    text = record.getMessage()
    assert "Query clarity checked" in text
    assert "messages=2" in text  # one system message, one rendered human message


async def test_plan_approval_checked_logs_the_message_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    parsed = PlanReviewResponse(
        assessment="Approved.",
        recorded_plan_matches=True,
        user_approved_a_plan=True,
        failure_reason="",
    )
    monkeypatch.setattr(
        tools_module, "get_chat_model", lambda model_config: _FakeStructuredLLM(parsed)
    )
    state = PrepState(
        current_query="q", clarification=Clarification(questions=[]), plan=Plan(steps=["step one"])
    )
    prep_tools = PrepTools(state, today_date="2026-08-21", data_sources="publications")
    approve_plan = prep_tools.build()[2]
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)

    await approve_plan.coroutine(runtime=_runtime())

    [record] = caplog.records
    text = record.getMessage()
    assert "Plan approval checked" in text
    assert "messages=2" in text  # one system message, one rendered human message


# --- The plan id ---------------------------------------------------------------------------------


def _clear_query_state() -> PrepState:
    return PrepState(current_query="q", clarification=Clarification(questions=[]))


async def test_recording_the_same_steps_again_renews_the_plan_id() -> None:
    state = _clear_query_state()
    update_plan = PrepTools(state, today_date="2026-08-21", data_sources="").build()[1]

    await update_plan.coroutine(steps=["one", "two"])
    first_id = state.plan_id
    await update_plan.coroutine(steps=["one", "two"])

    assert first_id is not None
    assert state.plan_id is not None
    assert state.plan_id != first_id


async def test_changing_the_query_clears_the_plan_id(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = QueryReviewResponse(assessment="Settled.", questions=[])
    monkeypatch.setattr(
        tools_module, "get_chat_model", lambda model_config: _FakeStructuredLLM(parsed)
    )
    state = _clear_query_state()
    state.plan, state.plan_id = Plan(steps=["one"]), "0123abcd"
    update_query = PrepTools(state, today_date="2026-08-21", data_sources="").build()[0]

    await update_query.coroutine(query="another question", runtime=_runtime())

    assert state.plan is None
    assert state.plan_id is None


async def test_starting_research_gives_a_plan_without_an_id_one() -> None:
    """A plan an earlier release recorded has no id."""
    state = _clear_query_state()
    state.plan, state.plan_approved = Plan(steps=["one"]), True
    start_research = PrepTools(state, today_date="2026-08-21", data_sources="").build()[3]

    await start_research.coroutine()

    assert state.research_started is True
    assert state.plan_id


async def test_starting_research_keeps_an_existing_plan_id() -> None:
    state = _clear_query_state()
    state.plan, state.plan_id, state.plan_approved = Plan(steps=["one"]), "0123abcd", True
    start_research = PrepTools(state, today_date="2026-08-21", data_sources="").build()[3]

    await start_research.coroutine()

    assert state.plan_id == "0123abcd"


# --- The failed-turn note in the checks' conversation --------------------------------------------


class _RecordingStructuredLLM(_FakeStructuredLLM):
    """A structured-output fake that keeps the messages of every call."""

    def __init__(self, parsed: Any) -> None:
        super().__init__(parsed)
        self.calls: list[list[Any]] = []

    def with_structured_output(
        self, schema: type[Any], *, include_raw: bool = False
    ) -> Runnable[Any, Any]:
        async def call(messages: list[Any]) -> dict[str, Any]:
            from langchain_core.messages import AIMessage

            self.calls.append(messages)
            return {"parsed": self._parsed, "parsing_error": None, "raw": AIMessage(content="")}

        return RunnableLambda(call)


def _conversation_after_a_failed_turn() -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    return [
        HumanMessage(content="Yes, I approve the plan."),
        AIMessage(content="Starting the research."),
        SystemMessage(content=FAILED_TURN_NOTE),
        SystemMessage(content="some other system message"),
        HumanMessage(content="continue"),
    ]


async def test_the_failed_turn_note_is_rendered_at_its_position() -> None:
    rendered = tools_module._format_conversation(_conversation_after_a_failed_turn())

    assert rendered.split("\n\n") == [
        "User: Yes, I approve the plan.",
        "Assistant: Starting the research.",
        f"System note: {FAILED_TURN_NOTE}",
        "User: continue",
    ]


async def test_the_approval_check_sees_the_note_and_the_continue_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = PlanReviewResponse(
        assessment="Approved before the failure.",
        recorded_plan_matches=True,
        user_approved_a_plan=True,
        failure_reason="",
    )
    llm = _RecordingStructuredLLM(parsed)
    monkeypatch.setattr(tools_module, "get_chat_model", lambda model_config: llm)
    state = _clear_query_state()
    state.plan = Plan(steps=["one"])
    approve_plan = PrepTools(state, today_date="2026-08-21", data_sources="").build()[2]

    await approve_plan.coroutine(runtime=_runtime(_conversation_after_a_failed_turn()))

    [[(_, system), (_, human)]] = llm.calls
    assert "continue or retry the research approves the recorded plan" in system
    assert "The note by itself approves" in system
    assert "Assistant: Starting the research.\n\nSystem note: " in human
    assert human.endswith("User: continue")


async def test_the_clarity_check_sees_the_note(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _RecordingStructuredLLM(QueryReviewResponse(assessment="Settled.", questions=[]))
    monkeypatch.setattr(tools_module, "get_chat_model", lambda model_config: llm)
    update_query = PrepTools(PrepState(), today_date="2026-08-21", data_sources="").build()[0]

    await update_query.coroutine(query="q", runtime=_runtime(_conversation_after_a_failed_turn()))

    [[_, (_, human)]] = llm.calls
    assert f"System note: {FAILED_TURN_NOTE}\n\nUser: continue" in human
