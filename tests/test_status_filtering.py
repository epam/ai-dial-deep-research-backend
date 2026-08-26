"""Status announcements reach research-agent and no other model.

What the agent told the user it was doing is not evidence. It must not be weighed as a search
when research-review judges coverage, and it must not sit in the report writer's context. It
stays in the transcript the app persists, which is the record of what happened.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from dial_deep_research.app.research.nodes import _render_findings, _strip_status_calls
from dial_deep_research.app.research.tools import UPDATE_STATUS_TOOL_NAME

_STATUS_TEXT = "Looking for US GDP forecasts"


def _status_call(call_id: str = "c1") -> dict[str, Any]:
    return {"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": _STATUS_TEXT}, "id": call_id}


def _mixed_transcript() -> list[Any]:
    """The usual shape: a status riding along with the step's first real tool call."""
    return [
        HumanMessage(content="the plan"),
        AIMessage(
            content="",
            tool_calls=[_status_call("c1"), {"name": "rag_search", "args": {"q": "x"}, "id": "c2"}],
            id="a1",
        ),
        ToolMessage(content="ok", tool_call_id="c1", name=UPDATE_STATUS_TOOL_NAME, id="t1"),
        ToolMessage(content="the hits", tool_call_id="c2", name="rag_search", id="t2"),
    ]


def test_the_status_goes_and_the_research_call_stays() -> None:
    kept = _strip_status_calls(_mixed_transcript())

    [ai] = [m for m in kept if isinstance(m, AIMessage)]
    assert [tc["name"] for tc in ai.tool_calls] == ["rag_search"]
    tool_messages = [m for m in kept if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_messages] == ["c2"]


def test_every_remaining_call_keeps_its_result() -> None:
    """Providers reject an assistant tool call with no matching result."""
    kept = _strip_status_calls(_mixed_transcript())

    called_ids = {tc["id"] for m in kept if isinstance(m, AIMessage) for tc in m.tool_calls}
    answered_ids = {m.tool_call_id for m in kept if isinstance(m, ToolMessage)}
    assert called_ids == answered_ids


def test_a_status_only_message_is_dropped_whole() -> None:
    """Nothing is left of it once the call goes, and an assistant message with no tool calls
    would let the client fall back to the raw copy of them."""
    transcript = [
        AIMessage(content="", tool_calls=[_status_call("c1")], id="a1"),
        ToolMessage(content="ok", tool_call_id="c1", name=UPDATE_STATUS_TOOL_NAME, id="t1"),
    ]

    assert _strip_status_calls(transcript) == []


def test_the_raw_copy_of_the_tool_calls_is_cleaned_too() -> None:
    """langchain_openai falls back to `additional_kwargs["tool_calls"]` whenever the parsed list
    is empty, which would put the status call straight back on the wire."""
    message = AIMessage(
        content="",
        tool_calls=[_status_call("c1"), {"name": "rag_search", "args": {}, "id": "c2"}],
        additional_kwargs={
            "tool_calls": [
                {"id": "c1", "function": {"name": UPDATE_STATUS_TOOL_NAME, "arguments": "{}"}},
                {"id": "c2", "function": {"name": "rag_search", "arguments": "{}"}},
            ]
        },
        id="a1",
    )

    [kept] = _strip_status_calls([message])

    raw_ids = [tc["id"] for tc in kept.additional_kwargs["tool_calls"]]
    assert raw_ids == ["c2"]


def test_a_transcript_without_statuses_is_untouched() -> None:
    transcript = [
        HumanMessage(content="the plan"),
        AIMessage(content="", tool_calls=[{"name": "rag_search", "args": {}, "id": "c1"}], id="a1"),
        ToolMessage(content="hits", tool_call_id="c1", name="rag_search", id="t1"),
    ]

    assert _strip_status_calls(transcript) == transcript


def test_the_findings_log_shows_no_status() -> None:
    """Otherwise research-review weighs `SEARCHED: update_status(...)` as a retrieval."""
    blocks = _render_findings(_strip_status_calls(_mixed_transcript()))
    findings = "\n\n".join(block["text"] for block in blocks)

    assert UPDATE_STATUS_TOOL_NAME not in findings
    assert _STATUS_TEXT not in findings
    assert "SEARCHED: rag_search" in findings
    assert "the hits" in findings


def test_filtering_twice_changes_nothing_more() -> None:
    """The filter has to be deterministic, or successive calls stop sharing a byte prefix and
    the provider's prompt cache cannot serve them."""
    once = _strip_status_calls(_mixed_transcript())

    assert _strip_status_calls(once) == once
