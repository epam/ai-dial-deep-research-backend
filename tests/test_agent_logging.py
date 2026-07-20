"""Tests for the agent logging middlewares (logging-policy spec).

The model-call skeleton event must be metadata-only; the payload record must be
DEBUG-level, truncated, and exist only behind the LOG_PAYLOADS switch. Requests are
lightweight stand-ins — the middlewares only read `messages`, `system_message`, and
`tools` from them.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from dial_deep_research.settings import settings
from dial_deep_research.utils.agent_logging import (
    ModelCallLoggingMiddleware,
    PromptLoggingMiddleware,
    agent_logging_middleware,
)

_LOGGER_NAME = "dial_deep_research.utils.agent_logging"


def _request(
    messages: list | None = None, system_text: str | None = None, tools: list | None = None
) -> Any:
    return SimpleNamespace(
        messages=messages or [HumanMessage(content="hi")],
        system_message=SystemMessage(content=system_text) if system_text else None,
        tools=tools or [],
    )


def _handler_returning(message: AIMessage):
    async def handler(request: Any) -> ModelResponse:
        return ModelResponse(result=[message])

    return handler


async def test_model_call_event_for_final_answer(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    message = AIMessage(
        content="a confidential result",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )

    await ModelCallLoggingMiddleware(agent_name="researcher").awrap_model_call(
        _request(), _handler_returning(message)
    )

    [record] = caplog.records
    text = record.getMessage()
    assert record.levelno == logging.INFO
    assert "agent=researcher" in text
    assert "finish=final_answer" in text
    assert f"content_length={len(message.content)}" in text
    assert "tokens=10/5/0" in text  # in/out/cached — cached 0 when the provider reports none
    assert "confidential" not in text  # metadata only — never the content itself


async def test_model_call_event_reports_cached_tokens(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    message = AIMessage(
        content="result",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 5,
            "total_tokens": 105,
            "input_token_details": {"cache_read": 80},
        },
    )

    await ModelCallLoggingMiddleware(agent_name="researcher").awrap_model_call(
        _request(), _handler_returning(message)
    )

    [record] = caplog.records
    assert "tokens=100/5/80" in record.getMessage()


async def test_model_call_event_for_tool_calls(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    message = AIMessage(
        content="",
        tool_calls=[
            {"id": "c1", "name": "search_docs", "args": {"q": "confidential"}, "type": "tool_call"}
        ],
    )

    await ModelCallLoggingMiddleware(agent_name="playground").awrap_model_call(
        _request(), _handler_returning(message)
    )

    [record] = caplog.records
    text = record.getMessage()
    assert "finish=tool_calls" in text
    assert "search_docs" in text  # tool names are structure
    assert "confidential" not in text  # tool-call argument values are content
    assert "tokens=n/a" in text


async def test_prompt_record_is_debug_and_truncated(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    long_text = "x" * 25
    request = _request(messages=[HumanMessage(content=long_text)], system_text="sys")

    response = await PromptLoggingMiddleware(max_chars=10).awrap_model_call(
        request, _handler_returning(AIMessage(content="ok"))
    )

    assert response.result[0].content == "ok"  # the handler chain is preserved
    [record] = caplog.records
    assert record.levelno == logging.DEBUG
    text = record.getMessage()
    assert "<truncated, total 25 chars>" in text
    assert long_text not in text


def test_payload_middleware_exists_only_behind_the_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "log_payloads", False)
    assert [type(m) for m in agent_logging_middleware("preparation")] == [
        ModelCallLoggingMiddleware
    ]

    monkeypatch.setattr(settings, "log_payloads", True)
    assert [type(m) for m in agent_logging_middleware("preparation")] == [
        ModelCallLoggingMiddleware,
        PromptLoggingMiddleware,
    ]


async def test_prompt_record_skipped_when_debug_filtered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The switch alone reveals nothing: payload records are DEBUG-level, and the
    # serialization is skipped entirely when DEBUG is filtered.
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    request = _request(messages=[HumanMessage(content="secret words")])

    response = await PromptLoggingMiddleware(max_chars=10).awrap_model_call(
        request, _handler_returning(AIMessage(content="ok"))
    )

    assert response.result[0].content == "ok"
    assert caplog.records == []
