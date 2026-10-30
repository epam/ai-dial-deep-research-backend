"""Tests for the turn state a DIAL message carries and the preparation agent's history.

Covers `history.reconstruct_prep_agent_history` (request side), `PreparationDialState` and
`create_dial_state` (response side), and `load_last_prep_state`. Tests construct DIAL
`Request` instances via `Request.model_construct(...)` to sidestep the SDK's validation
requirements (headers, api_key_secret, original_request, etc.) — only `messages` are
exercised by the code under test.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import pytest
from aidial_sdk.chat_completion import CustomContent, Message, Request, Role
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)

from dial_deep_research.app.history import (
    FAILURE_STATE_KEY,
    SNAPSHOT_STATE_KEY,
    CrossTurnPrepState,
    Plan,
    PreparationDialState,
    create_dial_state,
    load_last_prep_state,
    reconstruct_prep_agent_history,
)
from dial_deep_research.app.preparation.prompts import (
    FAILED_TURN_NOTE,
    PlanReviewResponse,
    QueryReviewResponse,
)
from dial_deep_research.utils.content import is_image_block

_IMAGE_URL = "files/bucket/dial-deep-research/r9-0.png"
_IMAGE_PLACEHOLDER = "[image not stored: successful run, image/png, sha256=" + "0" * 64 + "]"


def _build_request(messages: list[Message]) -> Request:
    return Request.model_construct(messages=messages)


def _assistant(content: str, state: dict[str, Any] | None) -> Message:
    custom_content = CustomContent(state=state) if state is not None else None
    return Message(role=Role.ASSISTANT, content=content, custom_content=custom_content)


def _prep_agent_slice() -> list[BaseMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "search", "args": {"q": "foo"}, "type": "tool_call"}],
        ),
        ToolMessage(content="result-A", tool_call_id="c1"),
        AIMessage(content="final answer"),
    ]


def _start_research_slice() -> list[BaseMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"id": "s1", "name": "start_research", "args": {}, "type": "tool_call"}],
        ),
        ToolMessage(content="Research has started.", tool_call_id="s1"),
    ]


def _state(
    *,
    prep: CrossTurnPrepState | None = None,
    agent_messages: list[BaseMessage] | None = None,
    research: dict[str, Any] | None = None,
    turn_failed: bool = False,
) -> dict[str, Any]:
    preparation = PreparationDialState(
        prep_state=prep or CrossTurnPrepState(), agent_messages=agent_messages or []
    )
    return create_dial_state(preparation, research=research, turn_failed=turn_failed)


def _research_record(*, image_block: dict[str, Any]) -> dict[str, Any]:
    """A research record whose research-agent messages hold one image block and a reply."""
    research_messages = [
        AIMessage(
            content="",
            tool_calls=[{"id": "r9", "name": "get_page", "args": {}, "type": "tool_call"}],
        ),
        ToolMessage(content=[image_block], tool_call_id="r9"),
        AIMessage(content="research-agent finding about IMF:WEO", id="research-reply"),
    ]
    return {
        "plan_id": "0123abcd",
        "research_query": "q",
        "approved_plan": ["one"],
        "research_agent_messages": messages_to_dict(research_messages),
        "reports": ["# Report"],
    }


def _completed_research_record() -> dict[str, Any]:
    return _research_record(image_block={"type": "text", "text": _IMAGE_PLACEHOLDER})


def _failed_research_record() -> dict[str, Any]:
    return _research_record(image_block={"type": "image", "url": _IMAGE_URL})


def _assert_only_preparation_messages(history: list[BaseMessage]) -> None:
    for message in history:
        assert getattr(message, "tool_call_id", None) != "r9"
        assert message.id != "research-reply"
        assert "research-agent finding" not in str(message.content)
        assert _IMAGE_URL not in str(message.content)
        assert _IMAGE_PLACEHOLDER not in str(message.content)
        if isinstance(message.content, list):
            assert not any(is_image_block(block) for block in message.content)


def test_messages_to_dict_round_trip_preserves_tool_call_structure() -> None:
    restored = messages_from_dict(messages_to_dict(_prep_agent_slice()))

    assert [type(m).__name__ for m in restored] == ["AIMessage", "ToolMessage", "AIMessage"]
    assert restored[0].tool_calls == [  # type: ignore[attr-defined]
        {"id": "c1", "name": "search", "args": {"q": "foo"}, "type": "tool_call"}
    ]
    assert restored[1].tool_call_id == "c1"  # type: ignore[attr-defined]
    assert restored[1].content == "result-A"
    assert restored[2].content == "final answer"


# --- History reconstruction ----------------------------------------------------------------------


def test_history_reconstruction_with_state_replays_the_agent_messages() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="initial question"),
            _assistant("final answer", _state(agent_messages=_prep_agent_slice())),
            Message(role=Role.USER, content="follow-up"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

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


def test_reconstruction_takes_only_the_request() -> None:
    """With no dial client to call, reconstruction cannot download a file."""
    assert list(inspect.signature(reconstruct_prep_agent_history).parameters) == ["request"]
    assert not inspect.iscoroutinefunction(reconstruct_prep_agent_history)


def test_legacy_assistant_turn_falls_back_to_native_content() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="ping"),
            _assistant("legacy answer", None),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert len(history) == 2
    assert isinstance(history[0], HumanMessage)
    assert isinstance(history[1], AIMessage)
    assert history[1].content == "legacy answer"
    assert history[1].tool_calls == []


def test_legacy_assistant_turn_with_empty_state_falls_back() -> None:
    request = _build_request(messages=[_assistant("legacy answer", {})])

    history = reconstruct_prep_agent_history(request)

    assert len(history) == 1
    assert isinstance(history[0], AIMessage)
    assert history[0].content == "legacy answer"


def test_mixed_legacy_and_state_turns_reconstruct_in_order() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="q1"),
            _assistant("legacy a1", None),
            Message(role=Role.USER, content="q2"),
            _assistant("final answer", _state(agent_messages=_prep_agent_slice())),
        ]
    )

    history = reconstruct_prep_agent_history(request)

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


def test_system_role_messages_are_skipped() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.SYSTEM, content="system prompt — should be ignored"),
            Message(role=Role.USER, content="hi"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert len(history) == 1
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "hi"


# --- A state with a top-level `messages` key and no `agent_messages` -----------------------------


def _old_state() -> dict[str, Any]:
    """A state that keeps the turn's whole transcript under a top-level `messages` key."""
    transcript = [
        *_start_research_slice(),
        ToolMessage(content=[{"type": "image", "url": _IMAGE_URL}], tool_call_id="r9"),
        AIMessage(content="research-agent finding about IMF:WEO", id="research-reply"),
        AIMessage(content="# Report"),
    ]
    return {
        "messages": messages_to_dict(transcript),
        "preparation": CrossTurnPrepState(
            current_query="q", plan_id="0123abcd", research_started=True
        ).model_dump(mode="json"),
    }


def test_an_old_state_parses() -> None:
    state = PreparationDialState.from_dict(_old_state()["preparation"])

    assert state.prep_state.current_query == "q"
    assert state.prep_state.research_started is True
    assert state.agent_messages == []


def test_an_old_state_reconstructs_as_one_message_of_the_native_content() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="go"),
            _assistant("# Report", _old_state()),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert [m.type for m in history] == ["human", "ai"]
    assert history[1].content == "# Report"
    assert history[1].tool_calls == []  # type: ignore[attr-defined]
    _assert_only_preparation_messages(history)


# --- `preparation.research_started` and the plan id ----------------------------------------------


def _started_prep() -> CrossTurnPrepState:
    return CrossTurnPrepState(current_query="q", plan_id="0123abcd", research_started=True)


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(_state(prep=_started_prep()), id="preparation-only"),
        pytest.param(
            _state(prep=_started_prep(), research=_failed_research_record(), turn_failed=True),
            id="beside-research-and-the-flag",
        ),
        pytest.param(
            {
                **_state(prep=_started_prep(), turn_failed=True),
                SNAPSHOT_STATE_KEY: "not a research record",
            },
            id="beside-an-invalid-research-value",
        ),
        pytest.param(
            {**_state(prep=_started_prep()), SNAPSHOT_STATE_KEY: {"plan_id": 7, "reports": "x"}},
            id="beside-an-invalid-research-dict",
        ),
    ],
)
def test_research_started_is_read_from_the_preparation_part(state: dict[str, Any]) -> None:
    assert state["preparation"]["research_started"] is True
    request = _build_request(messages=[_assistant("", state)])

    prep = load_last_prep_state(request)

    assert prep.research_started is True
    assert prep.plan_id == "0123abcd"


def test_a_preparation_state_without_a_plan_id_still_reads() -> None:
    """A state an earlier release persisted carries no `plan_id`."""
    state = PreparationDialState.from_dict({"current_query": "q", "plan": {"steps": ["one"]}})
    assert state.prep_state.plan_id is None
    assert state.prep_state.plan == Plan(steps=["one"])


def test_the_plan_id_round_trips_through_the_persisted_state() -> None:
    prep = CrossTurnPrepState(current_query="q", plan=Plan(steps=["one"]), plan_id="0123abcd")
    restored = PreparationDialState.from_dict(PreparationDialState(prep_state=prep).to_dict())
    assert restored.prep_state.plan_id == "0123abcd"


# --- The persisted shape of `PreparationDialState` --------------------------------------------


def _query_review() -> QueryReviewResponse:
    return QueryReviewResponse(assessment="Region is missing.", questions=["Which region?"])


def _plan_review() -> PlanReviewResponse:
    return PlanReviewResponse(
        assessment="Approved.",
        recorded_plan_matches=True,
        user_approved_a_plan=True,
        failure_reason="",
    )


def _preparation_with_reviews() -> PreparationDialState:
    return PreparationDialState(
        prep_state=CrossTurnPrepState(
            current_query="q", plan=Plan(steps=["one"]), plan_id="0123abcd", plan_approved=True
        ),
        agent_messages=_prep_agent_slice(),
        query_reviews=[_query_review()],
        plan_reviews=[_plan_review()],
    )


def test_to_dict_puts_messages_and_reviews_beside_the_prep_state_fields() -> None:
    preparation = _preparation_with_reviews()

    data = preparation.to_dict()

    assert data == {
        **preparation.prep_state.model_dump(mode="json"),
        "agent_messages": messages_to_dict(preparation.agent_messages),
        "query_reviews": [_query_review().model_dump(mode="json")],
        "plan_reviews": [_plan_review().model_dump(mode="json")],
    }


def test_a_state_with_reviews_round_trips_its_preparation_and_agent_messages() -> None:
    preparation = _preparation_with_reviews()

    restored = PreparationDialState.from_dict(preparation.to_dict())

    assert restored.prep_state == preparation.prep_state
    assert messages_to_dict(restored.agent_messages) == messages_to_dict(preparation.agent_messages)


def test_create_dial_state_lays_out_the_three_top_level_keys() -> None:
    research = _completed_research_record()
    preparation = _preparation_with_reviews()

    state = create_dial_state(preparation, research=research, turn_failed=True)

    assert set(state) == {"preparation", SNAPSHOT_STATE_KEY, FAILURE_STATE_KEY}
    assert state["preparation"] == preparation.to_dict()
    assert state[SNAPSHOT_STATE_KEY] == research
    assert state[FAILURE_STATE_KEY] is True
    assert set(create_dial_state(_preparation_with_reviews())) == {"preparation"}


# --- The preparation history after research ------------------------------------------------------


def test_a_completed_research_turn_gives_preparation_only_its_own_messages() -> None:
    state = _state(
        prep=_started_prep(),
        agent_messages=_start_research_slice(),
        research=_completed_research_record(),
    )
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="yes, go"),
            _assistant("# Report", state),
            Message(role=Role.USER, content="thanks"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert [m.type for m in history] == ["human", "ai", "tool", "human"]
    assert history[2].content == "Research has started."
    _assert_only_preparation_messages(history)


# --- A failed turn: the failure flag and the failed-turn note -----------------------------------


def _failed_research_state() -> dict[str, Any]:
    return _state(
        prep=_started_prep(),
        agent_messages=_start_research_slice(),
        research=_failed_research_record(),
        turn_failed=True,
    )


def test_a_failed_research_turn_is_followed_by_the_note_and_nothing_of_its_research() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="yes, go"),
            _assistant("", _failed_research_state()),
            Message(role=Role.USER, content="continue"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert [m.type for m in history] == ["human", "ai", "tool", "system", "human"]
    assert history[3].content == FAILED_TURN_NOTE
    assert history[4].content == "continue"
    _assert_only_preparation_messages(history)


def test_a_failed_turn_without_research_is_followed_by_the_note() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="approve"),
            _assistant("Let me check", _state(turn_failed=True)),
            Message(role=Role.USER, content="continue"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert [m.type for m in history] == ["human", "ai", "system", "human"]
    assert history[1].content == "Let me check"
    assert history[2].content == FAILED_TURN_NOTE


def test_a_turn_without_the_flag_gets_no_note() -> None:
    request = _build_request(
        messages=[_assistant("final answer", _state(agent_messages=_prep_agent_slice()))]
    )

    history = reconstruct_prep_agent_history(request)

    assert all(m.type != "system" for m in history)


def test_the_note_stays_after_the_failed_turn_as_turns_follow() -> None:
    request = _build_request(
        messages=[
            Message(role=Role.USER, content="go"),
            _assistant("", _failed_research_state()),
            Message(role=Role.USER, content="what happened?"),
            _assistant(
                "The request failed.",
                _state(agent_messages=[AIMessage(content="The request failed.")]),
            ),
            Message(role=Role.USER, content="continue"),
        ]
    )

    history = reconstruct_prep_agent_history(request)

    assert [m.type for m in history] == ["human", "ai", "tool", "system", "human", "ai", "human"]
    assert history[3].content == FAILED_TURN_NOTE


# --- Log records for state parsing (logging-policy: rebalance + content rule) --------------------


def test_legacy_fallbacks_log_below_warning(caplog: pytest.LogCaptureFixture) -> None:
    # Routine fallbacks (no custom content / no dict state) must not alarm at WARNING.
    caplog.set_level(logging.DEBUG, logger="dial_deep_research.app.history")
    request = _build_request(
        messages=[
            _assistant("legacy answer", None),
            Message(role=Role.ASSISTANT, content="another", custom_content=CustomContent()),
        ]
    )

    reconstruct_prep_agent_history(request)

    assert caplog.records  # the fallbacks are still recorded, at DEBUG
    assert all(record.levelno < logging.WARNING for record in caplog.records)


def test_invalid_state_logs_structure_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.history")
    secret = "top-secret user words"
    # `current_query` must be a string — the dict fails CrossTurnPrepState validation with the
    # secret as the offending input value.
    request = _build_request(
        messages=[_assistant("visible answer", {"preparation": {"current_query": {"q": secret}}})]
    )

    history = reconstruct_prep_agent_history(request)

    # The turn degrades to the visible text, and the WARNING carries structure, not content.
    assert history[-1].content == "visible answer"
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "error(s)" in record.getMessage()
    assert secret not in record.getMessage()


def test_agent_messages_that_cannot_be_decoded_fall_back_to_the_native_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A message type a later release writes must not make the conversation unreadable."""
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.history")
    state = {
        "preparation": {
            **_started_prep().model_dump(mode="json"),
            "agent_messages": [{"type": "a-later-type", "data": {"content": "hidden"}}],
        }
    }
    request = _build_request(messages=[_assistant("visible answer", state)])

    history = reconstruct_prep_agent_history(request)

    assert [m.content for m in history] == ["visible answer"]
    assert load_last_prep_state(request) == CrossTurnPrepState()
    # One WARNING per read of the state, each naming only the exception class.
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.WARNING]
    assert not any("hidden" in r.getMessage() for r in caplog.records)
