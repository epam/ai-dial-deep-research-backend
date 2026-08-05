"""How preparation text reaches the DIAL choice.

Two invariants: tokens of one assistant message concatenate untouched, and a new message starts
a new paragraph. The boundary is the segment — the chunk id plus the graph step, which every
chunk of one message shares and a later message differs in.

`appended_content` is the same flag, read by the research runner to decide whether the report
needs separating from preparation text at all.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from dial_deep_research.app.preparation.runner import PrepAgentRunner


class _StageSpy:
    def append_content(self, text: str) -> None:
        pass


class _ChoiceSpy:
    def __init__(self) -> None:
        self.content = ""

    def append_content(self, text: str) -> None:
        self.content += text

    @contextmanager
    def create_stage(self, title: str) -> Any:
        yield _StageSpy()


def _tool_round(runner: PrepAgentRunner, *call_ids: str) -> None:
    """One tool round as the runner really sees it: the calling AIMessage, then each result.

    The runner registers pending calls from the `AIMessage` and raises on a result with no
    match, so a test cannot shortcut to the `ToolMessage`.
    """
    runner._handle_ai_message(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "update_query", "args": {}, "id": call_id} for call_id in call_ids
            ],
        )
    )
    for call_id in call_ids:
        runner._handle_tool_message(ToolMessage(content="ok", tool_call_id=call_id))


def _runner() -> tuple[PrepAgentRunner, _ChoiceSpy]:
    choice = _ChoiceSpy()
    return PrepAgentRunner(choice), choice  # type: ignore[arg-type]


def _stream(
    runner: PrepAgentRunner, *, msg_id: str, langgraph_step: int, tokens: list[str]
) -> None:
    """Feed one assistant message's tokens: same id and step, as the model node emits them."""
    for token in tokens:
        runner._handle_message_chunk(
            AIMessageChunk(content=token, id=msg_id),
            {"langgraph_node": "model", "langgraph_step": langgraph_step},
        )


def test_tokens_of_one_message_concatenate_untouched() -> None:
    runner, choice = _runner()
    _stream(
        runner,
        msg_id="msg-1",
        langgraph_step=1,
        tokens=["What time ", "period should ", "this cover?"],
    )

    assert choice.content == "What time period should this cover?"


def test_the_first_segment_takes_no_leading_separator() -> None:
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["Let me check that."])

    assert not choice.content.startswith("\n")


def test_a_second_message_starts_a_new_paragraph() -> None:
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["Let me check that."])
    _stream(runner, msg_id="msg-2", langgraph_step=3, tokens=["The query is clear."])

    assert choice.content == "Let me check that.\n\nThe query is clear."


def test_a_new_segment_is_detected_without_a_tool_round_between() -> None:
    """Two segments in one graph step, with no tool round between them, still separate."""
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["First."])
    _stream(runner, msg_id="msg-2", langgraph_step=1, tokens=["Second."])

    assert choice.content == "First.\n\nSecond."


def test_the_unit_is_the_message_not_the_graph_step() -> None:
    """One id across two steps is one message, so it takes no separator.

    Structurally unreachable — an LLM run cannot span two super-steps — but it pins that the id
    alone decides, which is why the graph step is not part of the key.
    """
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["one "])
    _stream(runner, msg_id="msg-1", langgraph_step=2, tokens=["message"])

    assert choice.content == "one message"


def test_two_sequential_tool_calls_each_with_text_give_three_paragraphs() -> None:
    """Three model calls, so three segments and two blank lines — one per boundary."""
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["Checking the query."])
    _tool_round(runner, "call-1")
    _stream(runner, msg_id="msg-2", langgraph_step=3, tokens=["Now recording the plan."])
    _tool_round(runner, "call-2")
    _stream(runner, msg_id="msg-3", langgraph_step=5, tokens=["Does this plan look right?"])

    assert choice.content == (
        "Checking the query.\n\nNow recording the plan.\n\nDoes this plan look right?"
    )


def test_two_parallel_tool_calls_with_text_give_one_paragraph_break() -> None:
    """Parallel calls share one assistant message, so there is only one text segment before them.

    Two tool results arriving back-to-back must not produce two blank lines — the separator
    belongs to the boundary between text segments, and there is only one.
    """
    runner, choice = _runner()
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["Checking both sources."])
    _tool_round(runner, "call-1", "call-2")
    _stream(runner, msg_id="msg-2", langgraph_step=3, tokens=["Both came back."])

    assert choice.content == "Checking both sources.\n\nBoth came back."


def test_a_retried_model_call_separates_the_aborted_fragment() -> None:
    """A stream-drop retry re-streams as a new message inside the same graph step.

    The aborted fragment cannot be retracted (DIAL content is append-only), so the retry is a new
    segment and takes a blank line, keeping the fragment visibly apart from the full answer.
    """
    runner, choice = _runner()
    _stream(runner, msg_id="attempt-1", langgraph_step=1, tokens=["What time per"])
    _stream(
        runner, msg_id="attempt-2", langgraph_step=1, tokens=["What time period should this cover?"]
    )

    assert choice.content == "What time per\n\nWhat time period should this cover?"


def test_only_the_model_node_reaches_the_content() -> None:
    """The clarity/approval checks stream under "tools"; their raw JSON must not leak."""
    runner, choice = _runner()
    runner._handle_message_chunk(
        AIMessageChunk(content='{"questions": []}', id="check-1"),
        {"langgraph_node": "tools", "langgraph_step": 2},
    )

    assert choice.content == ""
    assert runner.appended_content is False


def test_non_chunk_and_empty_text_are_ignored() -> None:
    runner, choice = _runner()
    runner._handle_message_chunk(
        HumanMessage(content="not a chunk"), {"langgraph_node": "model", "langgraph_step": 1}
    )
    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=[""])

    assert choice.content == ""
    assert runner.appended_content is False


def test_appended_content_reports_whether_any_text_was_streamed() -> None:
    runner, _ = _runner()
    assert runner.appended_content is False

    _stream(runner, msg_id="msg-1", langgraph_step=1, tokens=["anything"])
    assert runner.appended_content is True
