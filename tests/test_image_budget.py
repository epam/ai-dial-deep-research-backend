"""Tests for `ImageBudgetMiddleware` (the image-budget spec).

The clamp walk and message rendering are unit-tested by calling `before_model`
directly; the same-id substitution mechanics are tested end-to-end through
`create_agent` with a scripted fake model.
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from dial_deep_research.app.middleware import ImageBudgetMiddleware
from dial_deep_research.settings import Settings


def _image_block() -> dict[str, Any]:
    return {"type": "image", "base64": "aGk=", "mime_type": "image/png"}


def _tool_message(msg_id: str, *, num_images: int, name: str = "some_tool") -> ToolMessage:
    content: list[dict[str, Any]] = [{"type": "text", "text": f"result {msg_id}"}]
    content.extend(_image_block() for _ in range(num_images))
    return ToolMessage(content=content, tool_call_id=f"call-{msg_id}", id=msg_id, name=name)


def _clamp(messages: list[BaseMessage], *, limit: int) -> dict[str, Any] | None:
    middleware = ImageBudgetMiddleware(limit=limit)
    return middleware.before_model({"messages": messages}, None)  # type: ignore[arg-type]


def test_noop_within_budget() -> None:
    messages: list[BaseMessage] = [_tool_message("a", num_images=3)]
    assert _clamp(messages, limit=3) is None


def test_parallel_batch_overflow_step_math() -> None:
    """The [a, b] example: base 49, +4 then +1, budget 50 — both dropped, exact math."""
    messages: list[BaseMessage] = [
        _tool_message("base", num_images=49),
        _tool_message("a", num_images=4),
        _tool_message("b", num_images=1),
    ]
    update = _clamp(messages, limit=50)
    assert update is not None
    by_id = {m.id: m for m in update["messages"]}
    assert set(by_id) == {"a", "b"}

    assert (
        "it contained 1 image(s), which brought the conversation from 53 to 54 images, "
        "exceeding the budget of 50." in by_id["b"].content
    )
    assert "slot(s) remain" not in by_id["b"].content

    assert (
        "it contained 4 image(s), which brought the conversation from 49 to 53 images, "
        "exceeding the budget of 50." in by_id["a"].content
    )
    assert "1 image slot(s) remain — fetch at most 1 more image(s)." in by_id["a"].content

    for substituted in by_id.values():
        assert substituted.status == "error"
        assert substituted.tool_call_id == f"call-{substituted.id}"
        assert substituted.name == "some_tool"


def test_budget_exactly_used() -> None:
    messages: list[BaseMessage] = [
        _tool_message("base", num_images=46),
        _tool_message("a", num_images=4),
        _tool_message("b", num_images=1),
    ]
    update = _clamp(messages, limit=50)
    assert update is not None
    assert [m.id for m in update["messages"]] == ["b"]
    text = update["messages"][0].content
    assert "from 50 to 51 images, exceeding the budget of 50." in text
    assert "The image budget is fully used — do not fetch more images." in text


def test_multi_image_message_over_drop_leaves_slots() -> None:
    """Dropping a whole multi-image message can land under the limit — slots reported."""
    messages: list[BaseMessage] = [
        _tool_message("base", num_images=49),
        _tool_message("big", num_images=5),
    ]
    update = _clamp(messages, limit=50)
    assert update is not None
    assert [m.id for m in update["messages"]] == ["big"]
    text = update["messages"][0].content
    assert "from 49 to 54 images, exceeding the budget of 50." in text
    assert "1 image slot(s) remain — fetch at most 1 more image(s)." in text


def test_text_only_and_older_messages_untouched() -> None:
    messages: list[BaseMessage] = [
        _tool_message("kept", num_images=2),
        ToolMessage(content="plain text", tool_call_id="call-t", id="t"),
        _tool_message("dropped", num_images=1),
    ]
    update = _clamp(messages, limit=2)
    assert update is not None
    assert [m.id for m in update["messages"]] == ["dropped"]


def test_tool_agnostic_counting() -> None:
    """Substitution keys on image content only, whatever the tool name."""
    messages: list[BaseMessage] = [
        _tool_message("x", num_images=1, name="future_image_tool"),
        _tool_message("y", num_images=1, name="another_tool"),
    ]
    update = _clamp(messages, limit=1)
    assert update is not None
    assert [m.id for m in update["messages"]] == ["y"]
    assert update["messages"][0].name == "another_tool"


def test_images_outside_tool_messages_are_not_substitutable() -> None:
    """Defensive: nothing to substitute — no update, no hang."""
    messages: list[BaseMessage] = [HumanMessage(content=[_image_block(), _image_block()])]
    assert _clamp(messages, limit=1) is None


def test_id_less_message_is_skipped_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """No id means `add_messages` would append the substitute and keep the images."""
    messages: list[BaseMessage] = [
        ToolMessage(content=[_image_block(), _image_block()], tool_call_id="call-x", name="t")
    ]
    with caplog.at_level(logging.WARNING):
        assert _clamp(messages, limit=1) is None
    assert "no message id" in caplog.text
    assert "still exceeded" in caplog.text


def test_walk_continues_past_an_id_less_message() -> None:
    """An unsubstitutable newest message does not stop the walk reaching an older one."""
    messages: list[BaseMessage] = [
        _tool_message("older", num_images=2),
        ToolMessage(content=[_image_block(), _image_block()], tool_call_id="call-x", name="t"),
    ]
    update = _clamp(messages, limit=2)
    assert update is not None
    assert [m.id for m in update["messages"]] == ["older"]


def test_max_context_images_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_CONTEXT_IMAGES", "7")
    assert Settings().max_context_images == 7


def test_max_context_images_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_CONTEXT_IMAGES", raising=False)
    assert Settings().max_context_images == 50


def test_max_context_images_rejects_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A budget of 0 would drop every image result; `ge=1` refuses it at startup."""
    monkeypatch.setenv("MAX_CONTEXT_IMAGES", "0")
    with pytest.raises(ValidationError):
        Settings()


@tool
def fetch_images() -> list[dict[str, Any]]:
    """Return two images."""
    return [_image_block(), _image_block()]


class _FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def _scripted_responses() -> Iterator[AIMessage]:
    yield AIMessage(content="", tool_calls=[{"name": "fetch_images", "args": {}, "id": "call1"}])
    yield AIMessage(content="done")


def _budget_agent() -> Any:
    return create_agent(
        model=_FakeToolCallingModel(messages=_scripted_responses()),
        tools=[fetch_images],
        middleware=[ImageBudgetMiddleware(limit=1)],
    )


async def test_sync_only_hook_still_runs_on_async_invoke() -> None:
    """Production is async; `before_model` is sync-only and relies on langgraph's fallback.

    `create_agent` wraps the hook in a `RunnableCallable` with no async variant, which runs
    the sync fn in an executor. Nothing in this repo would catch that contract changing.
    """
    result = await _budget_agent().ainvoke({"messages": [HumanMessage(content="hi")]})

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].status == "error"
    assert "Tool result dropped: it contained 2 image(s)" in tool_messages[0].content


def test_substitution_replaces_in_state_end_to_end() -> None:
    result = _budget_agent().invoke({"messages": [HumanMessage(content="hi")]})

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1  # replaced, not appended
    substituted = tool_messages[0]
    assert substituted.status == "error"
    assert substituted.tool_call_id == "call1"
    assert "Tool result dropped: it contained 2 image(s)" in substituted.content
    assert "from 0 to 2 images, exceeding the budget of 1." in substituted.content
    assert "1 image slot(s) remain" in substituted.content
    assert all(
        not (isinstance(b, dict) and b.get("type") == "image")
        for m in result["messages"]
        if isinstance(m.content, list)
        for b in m.content
    )
