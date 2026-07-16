"""Tests for DIAL <-> LangChain message history round-tripping.

Covers `history.reconstruct_history` (request side) and the
`messages_to_dict`/`messages_from_dict` round-trip we rely on for the response
side. Tests construct DIAL `Request` instances via `Request.construct(...)` to
sidestep the SDK's validation requirements (headers, api_key_secret,
original_request, etc.) — only `messages` are exercised by the code under test.
"""

from __future__ import annotations

import logging

import pytest
from aidial_sdk.chat_completion import CustomContent, Message, Request, Role
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)

from dial_deep_research.app.history import reconstruct_history


def _build_request(messages: list[Message]) -> Request:
    return Request.model_construct(messages=messages)


class _NoOpDial:
    """Stand-in for `AsyncDial` for tests that don't exercise image rehydration.

    `reconstruct_history` only touches `dial` to pass it through to
    `rehydrate_image_blocks`, which is a no-op for assistant slices that
    contain no URL-form image blocks (which is the case in these tests).
    """


def _encoded_assistant_slice() -> list[dict]:
    return messages_to_dict(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "c1", "name": "search", "args": {"q": "foo"}, "type": "tool_call"}
                ],
            ),
            ToolMessage(content="result-A", tool_call_id="c1"),
            AIMessage(content="final answer"),
        ]
    )


def test_messages_to_dict_round_trip_preserves_tool_call_structure() -> None:
    seq = [
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "search", "args": {"q": "foo"}, "type": "tool_call"}],
        ),
        ToolMessage(content="result-A", tool_call_id="c1"),
        AIMessage(content="final answer"),
    ]

    restored = messages_from_dict(messages_to_dict(seq))

    assert [type(m).__name__ for m in restored] == ["AIMessage", "ToolMessage", "AIMessage"]
    assert restored[0].tool_calls == [  # type: ignore[attr-defined]
        {"id": "c1", "name": "search", "args": {"q": "foo"}, "type": "tool_call"}
    ]
    assert restored[1].tool_call_id == "c1"  # type: ignore[attr-defined]
    assert restored[1].content == "result-A"
    assert restored[2].content == "final answer"


async def test_history_reconstruction_with_state_replays_full_slice() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="initial question"),
            Message(
                role=Role.ASSISTANT,
                content="final answer",
                custom_content=CustomContent(state={"messages": _encoded_assistant_slice()}),
            ),
            Message(role=Role.USER, content="follow-up"),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert [type(m).__name__ for m in history] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert history[0].content == "initial question"
    assert history[1].tool_calls[0]["name"] == "search"  # type: ignore[attr-defined]
    assert history[2].tool_call_id == "c1"  # type: ignore[attr-defined]
    assert history[3].content == "final answer"
    assert history[4].content == "follow-up"


async def test_legacy_assistant_turn_falls_back_to_native_content() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="ping"),
            Message(role=Role.ASSISTANT, content="legacy answer"),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert len(history) == 2
    assert isinstance(history[0], HumanMessage)
    assert isinstance(history[1], AIMessage)
    assert history[1].content == "legacy answer"
    assert history[1].tool_calls == []


async def test_legacy_assistant_turn_with_empty_state_falls_back() -> None:
    request = _build_request(
        messages=[
            Message(
                role=Role.ASSISTANT,
                content="legacy answer",
                custom_content=CustomContent(state={}),
            ),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert len(history) == 1
    assert isinstance(history[0], AIMessage)
    assert history[0].content == "legacy answer"


async def test_mixed_legacy_and_state_turns_reconstruct_in_order() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="q1"),
            Message(role=Role.ASSISTANT, content="legacy a1"),
            Message(role=Role.USER, content="q2"),
            Message(
                role=Role.ASSISTANT,
                content="final answer",
                custom_content=CustomContent(state={"messages": _encoded_assistant_slice()}),
            ),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert [type(m).__name__ for m in history] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    assert history[0].content == "q1"
    assert history[1].content == "legacy a1"
    assert history[1].tool_calls == []  # type: ignore[attr-defined]
    assert history[2].content == "q2"
    assert history[3].tool_calls[0]["name"] == "search"  # type: ignore[attr-defined]


async def test_system_role_messages_are_skipped() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.SYSTEM, content="system prompt — should be ignored"),
            Message(role=Role.USER, content="hi"),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert len(history) == 1
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "hi"


# --- Log records for state parsing (logging-policy: rebalance + content rule) --------------------


async def test_legacy_fallbacks_log_below_warning(caplog: pytest.LogCaptureFixture) -> None:
    # Routine fallbacks (no custom content / no dict state) must not alarm at WARNING.
    caplog.set_level(logging.DEBUG, logger="dial_deep_research.app.history")
    request = _build_request(
        messages=[
            Message(role=Role.ASSISTANT, content="legacy answer"),
            Message(role=Role.ASSISTANT, content="another", custom_content=CustomContent()),
        ]
    )

    await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    assert caplog.records  # the fallbacks are still recorded, at DEBUG
    assert all(record.levelno < logging.WARNING for record in caplog.records)


async def test_invalid_state_logs_structure_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.history")
    secret = "top-secret user words"
    request = _build_request(
        messages=[
            Message(
                role=Role.ASSISTANT,
                content="visible answer",
                custom_content=CustomContent(
                    # `current_query` must be a string — the dict fails PrepState validation
                    # with the secret as the offending input value.
                    state={"messages": [], "preparation": {"current_query": {"q": secret}}},
                ),
            ),
        ]
    )

    history = await reconstruct_history(request, _NoOpDial())  # type: ignore[arg-type]

    # The turn degrades to the visible text, and the WARNING carries structure, not content.
    assert history[-1].content == "visible answer"
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "error(s)" in record.getMessage()
    assert secret not in record.getMessage()
