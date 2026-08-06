"""The report ↔ report-review loop: the two nodes, and the prompt text they render.

What is protected here:

- The report node branches on whether a draft already exists, records each successful draft's
  1-based version in `report_version` (a failed write records nothing), and never lets a failed
  revision discard the draft it already had.
- A revision's request keeps the first draft's message prefix and appends the revision request
  last, so the provider's prompt cache can still serve the prefix.
- The report-review node absorbs its own failures, routes on the app-measured word count whatever
  the model said, emits one stage per review, and sees neither the findings nor a plan
  research-review authored.
- The configured section structure reaches both prompts verbatim.

Routing itself lives in `test_research_routing.py`; the stage's rendering in `test_dial_stages.py`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableLambda

from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.nodes import (
    ReportAction,
    ReportReviewOutcome,
    ReportVerdict,
)
from dial_deep_research.app.research.prompts import (
    REPORT_SYSTEM_PROMPT,
    ReportReview,
    render_protected_section_names,
    render_report_structure,
)
from dial_deep_research.app_properties import DEFAULT_REPORT_STRUCTURE, ReportSection
from dial_deep_research.utils.content import count_image_blocks, count_words

_TODAY = "2026-07-16"

_CUSTOM_SECTIONS = [
    ReportSection(name="Summary", description="Two paragraphs answering the question."),
    ReportSection(
        name="Evidence",
        description="A table with the columns `claim` and `source`.",
        protected=True,
    ),
    ReportSection(name="Outlook", description="What follows, where the findings support it."),
]


def _state(**overrides: Any) -> Any:
    """A post-research graph state: research done, no draft yet."""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="Research question:\nq\n\n1. step one")],
        "original_query": "what happened to inflation?",
        "plans": [["step one"]],
        "iteration": 1,
        "report": None,
        "report_revision_instruction": None,
        "report_version": 0,
        "revision_failed": False,
    }
    return {**state, **overrides}


# --- the report node ----------------------------------------------------------------------------


class _RecordingReportLLM:
    """Returns the canned drafts in turn, recording the messages each call received."""

    def __init__(self, *drafts: str) -> None:
        self._drafts = list(drafts)
        self.calls: list[list[BaseMessage]] = []

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.calls.append(list(messages))
        yield AIMessageChunk(content=self._drafts[len(self.calls) - 1])


class _FailingReportLLM:
    """Fails on a non-retryable error, the kind a longer revision request is likelier to hit."""

    def __init__(self) -> None:
        self.calls = 0

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.calls += 1
        raise ValueError("maximum context length exceeded")
        yield  # pragma: no cover - makes this an async generator


def _report_node(
    llm: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sections: list[ReportSection] | None = None,
    max_words: int = 2750,
) -> Any:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    return nodes.make_report_node(
        today_date=_TODAY,
        sections=sections if sections is not None else DEFAULT_REPORT_STRUCTURE,
        max_words=max_words,
    )


async def test_first_draft_asks_for_the_report_over_the_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("the report")
    node = _report_node(llm, monkeypatch)

    result = await node(_state())

    assert result == {"report": "the report", "report_version": 1}
    [messages] = llm.calls
    # System prompt, the research transcript, then the report request — and nothing else.
    assert len(messages) == 3
    assert isinstance(messages[0], SystemMessage)
    assert "1. step one" in messages[1].content
    assert "what happened to inflation?" in messages[2].content


async def test_first_draft_system_prompt_carries_the_configured_structure_and_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("the report")
    node = _report_node(llm, monkeypatch, sections=_CUSTOM_SECTIONS, max_words=1500)

    await node(_state())

    system = llm.calls[0][0].content
    assert isinstance(system, str)
    for section in _CUSTOM_SECTIONS:
        assert section.name in system
        # A section's rules are passed verbatim: the prompt neither rewrites nor summarizes them.
        assert section.description in system
    # The configured structure replaces the default, and the protected name is also stated
    # separately, in the precedence rule — hence at least twice in the prompt.
    assert "Key Findings" not in system
    assert "1500 words" in system
    assert system.count(render_protected_section_names(_CUSTOM_SECTIONS)) >= 2


async def test_first_draft_is_version_one(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _RecordingReportLLM("the report")
    node = _report_node(llm, monkeypatch)

    result = await node(_state())

    assert result["report_version"] == 1


async def test_a_revision_is_written_whenever_a_draft_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = "one two three four five six seven"
    llm = _RecordingReportLLM("the revised report")
    node = _report_node(llm, monkeypatch)

    result = await node(
        _state(
            report=previous,
            report_revision_instruction="- Restore the References section.",
            report_version=1,
        )
    )

    [messages] = llm.calls
    assert len(messages) == 4
    revision_request = messages[-1].content
    assert "- Restore the References section." in revision_request
    assert previous in revision_request
    assert f"{count_words(previous)} words" in revision_request
    assert "2750" in revision_request
    assert result == {"report": "the revised report", "report_version": 2}


async def test_a_revision_keeps_the_first_draft_message_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("draft one", "draft two")
    node = _report_node(llm, monkeypatch)

    await node(_state())
    await node(_state(report="draft one", report_revision_instruction="- Shorten it."))

    first_draft_messages, revision_messages = llm.calls
    # The revision request is appended, never inserted before the transcript, so the byte prefix
    # the provider's prompt cache holds is unchanged.
    assert revision_messages[:3] == first_draft_messages
    assert len(revision_messages) == 4


async def test_each_draft_records_the_next_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("the second revision")
    node = _report_node(llm, monkeypatch)

    result = await node(
        _state(
            report="the first revision", report_revision_instruction="- Again.", report_version=2
        )
    )

    assert result["report_version"] == 3


async def test_a_failed_revision_keeps_the_previous_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FailingReportLLM()
    node = _report_node(llm, monkeypatch)

    result = await node(_state(report="draft one", report_revision_instruction="- Shorten it."))

    # Nothing overwrites `report`, so the previous draft stays the one that is delivered.
    assert result == {"revision_failed": True}
    assert llm.calls == 1


async def test_a_failed_first_draft_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nothing to fall back to: the turn fails, as it did before the loop existed.
    llm = _FailingReportLLM()
    node = _report_node(llm, monkeypatch)

    with pytest.raises(ValueError):
        await node(_state())


# --- the report-review node ---------------------------------------------------------------------


class _FakeReviewLLM:
    """A structured-output LLM returning one canned result, or raising it.

    Records the messages of each call so the request's own contract can be checked.
    """

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result
        self.calls: list[list[BaseMessage]] = []

    def with_structured_output(
        self, schema: type[Any], *, include_raw: bool = False
    ) -> Runnable[Any, Any]:
        async def call(messages: list[BaseMessage]) -> dict[str, Any]:
            self.calls.append(list(messages))
            if isinstance(self._result, Exception):
                raise self._result
            return self._result

        return RunnableLambda(call)


def _parsed(review: ReportReview) -> dict[str, Any]:
    """The `include_raw=True` shape of a successfully parsed structured response."""
    return {"parsed": review, "parsing_error": None, "raw": AIMessage(content="")}


_UNPARSEABLE: dict[str, Any] = {
    "parsed": None,
    "parsing_error": ValueError("no verdict in the response"),
    "raw": AIMessage(content=""),
}


def _review_node(
    llm: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sections: list[ReportSection] | None = None,
    max_words: int = 2750,
) -> tuple[Any, list[ReportReviewOutcome]]:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    stages: list[ReportReviewOutcome] = []
    node = nodes.make_report_review_node(
        today_date=_TODAY,
        sections=sections if sections is not None else DEFAULT_REPORT_STRUCTURE,
        max_words=max_words,
        emit_stage=stages.append,
    )
    return node, stages


async def test_an_approved_draft_within_the_ceiling_is_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[])))
    node, stages = _review_node(llm, monkeypatch)

    result = await node(_state(report="a short draft", report_version=1))

    assert result == {"report_revision_instruction": None}
    [outcome] = stages
    assert outcome.verdict is ReportVerdict.APPROVED
    assert outcome.action is ReportAction.DELIVER
    assert outcome.findings == []
    assert outcome.draft_number == 1
    assert outcome.word_count == 3


async def test_findings_become_the_revision_instruction_and_reach_the_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = "The References section was dropped; restore it with the source tables."
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[finding])))
    node, stages = _review_node(llm, monkeypatch)

    result = await node(_state(report="a short draft"))

    assert result["report_revision_instruction"] is not None
    assert finding in result["report_revision_instruction"]
    [outcome] = stages
    assert outcome.verdict is ReportVerdict.REVISE
    assert outcome.action is ReportAction.REVISE
    assert outcome.findings == [finding]


async def test_an_approving_verdict_cannot_pass_an_over_ceiling_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[])))
    node, stages = _review_node(llm, monkeypatch, max_words=3)

    result = await node(_state(report="one two three four five"))

    assert result["report_revision_instruction"] is not None
    [outcome] = stages
    # The model's verdict is reported as it came; the app's action overrides it on the count.
    assert outcome.verdict is ReportVerdict.APPROVED
    assert outcome.action is ReportAction.REVISE_OVER_CEILING


async def test_a_failed_review_call_still_shortens_an_over_long_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(RuntimeError("provider is down"))
    node, stages = _review_node(llm, monkeypatch, max_words=3)

    result = await node(_state(report="one two three four five"))

    assert result["report_revision_instruction"] is not None
    [outcome] = stages
    assert outcome.verdict is ReportVerdict.FAILED
    assert outcome.action is ReportAction.REVISE_OVER_CEILING


async def test_a_failed_review_call_delivers_a_draft_within_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(RuntimeError("provider is down"))
    node, stages = _review_node(llm, monkeypatch)

    result = await node(_state(report="a short draft"))

    assert result == {"report_revision_instruction": None}
    # The failure is visible as a stage of its own, in place of findings.
    [outcome] = stages
    assert outcome.verdict is ReportVerdict.FAILED
    assert outcome.action is ReportAction.DELIVER
    assert outcome.findings == []


async def test_an_unparseable_verdict_is_absorbed_like_a_failed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_UNPARSEABLE)
    node, stages = _review_node(llm, monkeypatch)

    result = await node(_state(report="a short draft"))

    assert result == {"report_revision_instruction": None}
    [outcome] = stages
    assert outcome.verdict is ReportVerdict.FAILED


async def test_findings_reach_the_stage_but_never_a_log_record(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The asymmetry is the requirement: the stage shows the findings, the log counts them."""
    finding = "The draft ends with 'Confidence: High (3 sources)'; remove it."
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[finding])))
    node, stages = _review_node(llm, monkeypatch)
    caplog.set_level(logging.DEBUG, logger=nodes.__name__)

    await node(_state(report="a short draft"))

    assert stages[0].findings == [finding]
    records = [record.getMessage() for record in caplog.records]
    assert any("findings=1" in record for record in records)
    assert not any(finding in record for record in records)
    # Nor does the draft it judges.
    assert not any("a short draft" in record for record in records)


async def test_the_stage_reports_the_draft_being_reviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[])))
    node, stages = _review_node(llm, monkeypatch, max_words=1200)

    await node(_state(report="a short draft", report_version=2))

    [outcome] = stages
    # The stage reports the state's version index as-is: this is the second draft.
    assert outcome.draft_number == 2
    assert outcome.max_words == 1200


async def test_the_review_request_carries_neither_findings_nor_a_research_review_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = "one two three four five six seven eight nine"
    llm = _FakeReviewLLM(_parsed(ReportReview(findings=[])))
    node, _ = _review_node(llm, monkeypatch, sections=_CUSTOM_SECTIONS)

    await node(
        _state(
            report=draft,
            messages=[
                HumanMessage(content="Research question:\nq\n\n1. the approved plan step"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "rag_search", "args": {"q": "x"}, "id": "call_1"}],
                ),
                ToolMessage(
                    content=[{"type": "text", "text": "retrieved page text"}, {"type": "image"}],
                    tool_call_id="call_1",
                ),
            ],
            plans=[["the approved plan step"], ["a step research-review authored"]],
        )
    )

    [messages] = llm.calls
    # Exactly the system prompt and one request: no transcript message is forwarded.
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert not any(isinstance(message, ToolMessage) for message in messages)
    # The transcript's tool result carries an image block; none of it is forwarded.
    assert all(count_image_blocks(message.content) == 0 for message in messages)
    request = messages[1].content
    assert isinstance(request, str)
    assert "retrieved page text" not in request
    assert "rag_search" not in request
    # Only the approved preparation plan: a later plan is research-review's own and cannot
    # carry a user instruction.
    assert "the approved plan step" in request
    assert "a step research-review authored" not in request
    # Stable content first, the draft and its measured count last, for prefix stability.
    assert request.rstrip().endswith(draft)
    assert request.index(f"{count_words(draft)} words") < request.index(draft)
    assert request.index("Summary") < request.index(draft)


# --- prompt rendering ---------------------------------------------------------------------------


def test_render_report_structure_keeps_names_and_descriptions_verbatim_in_order() -> None:
    rendered = render_report_structure(_CUSTOM_SECTIONS)

    for section in _CUSTOM_SECTIONS:
        assert section.name in rendered
        assert section.description in rendered
    assert rendered.index("Summary") < rendered.index("Evidence") < rendered.index("Outlook")
    # A configured structure replaces the default rather than extending it.
    assert "Key Findings" not in rendered


def test_render_report_structure_marks_the_protected_sections() -> None:
    rendered = render_report_structure(_CUSTOM_SECTIONS)

    assert "Evidence — PROTECTED" in rendered
    assert "Summary — PROTECTED" not in rendered


def test_render_protected_section_names_lists_only_the_protected_ones() -> None:
    assert render_protected_section_names(_CUSTOM_SECTIONS) == "Evidence"
    assert render_protected_section_names(DEFAULT_REPORT_STRUCTURE) == "References"
    two_protected = [
        _CUSTOM_SECTIONS[0],
        _CUSTOM_SECTIONS[1],
        ReportSection(name="Outlook", description="What follows.", protected=True),
    ]
    assert render_protected_section_names(two_protected) == "Evidence, Outlook"


def test_report_system_prompt_states_the_ceiling_and_the_protected_names() -> None:
    prompt = REPORT_SYSTEM_PROMPT.format(
        today_date=_TODAY,
        report_structure=render_report_structure(DEFAULT_REPORT_STRUCTURE),
        max_words=2750,
        protected_sections=render_protected_section_names(DEFAULT_REPORT_STRUCTURE),
    )

    assert "2750 words" in prompt
    # Once as the section heading, once in the precedence rule that names what a user
    # instruction may not drop.
    assert prompt.count("References") >= 2
    # Report-wide rules are the prompt's own, not a section's.
    assert "[doc <id>, page <ix>]" in prompt
