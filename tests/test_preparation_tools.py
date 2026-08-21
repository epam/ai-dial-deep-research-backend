"""Logging for the preparation tools' independent LLM calls (logging-policy spec).

`update_query` and `approve_plan` each make one system+human call to check clarity or
approval; both now log a message count alongside duration and token usage.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.runnables import Runnable, RunnableLambda

from dial_deep_research.app.history import Clarification, Plan, PrepState
from dial_deep_research.app.preparation import tools as tools_module
from dial_deep_research.app.preparation.prompts import PlanReviewResponse, QueryReviewResponse
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
    prep_tools = PrepTools(PrepState(), today_date="2026-08-21", data_sources_descriptions="sigma")
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
    prep_tools = PrepTools(state, today_date="2026-08-21", data_sources_descriptions="sigma")
    approve_plan = prep_tools.build()[2]
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)

    await approve_plan.coroutine(runtime=_runtime())

    [record] = caplog.records
    text = record.getMessage()
    assert "Plan approval checked" in text
    assert "messages=2" in text  # one system message, one rendered human message
