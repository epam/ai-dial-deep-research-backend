"""The report ↔ report-review loop: the two nodes, and the prompt text they render.

What is protected here:

- The report node branches on whether a draft already exists, appends each successful draft to
  `reports` (a failed write appends nothing), and never lets a failed revision discard the draft
  it already had.
- A revision's request keeps the first draft's message prefix and appends the revision request
  last, so the provider's prompt cache can still serve the prefix.
- The report-review node absorbs its own failures, stores each round whole in `report_reviews`,
  revises on the app-measured word count whatever the model said, emits one stage per review, and
  sees neither the findings nor a plan research-review authored.
- The configured report structure reaches both prompts verbatim.

Routing itself lives in `test_research_routing.py`; the stage's rendering in `test_dial_stages.py`.
"""

from __future__ import annotations

import json
import logging
import re
from itertools import count
from typing import Any, cast

import pytest
from langchain_core.documents.base import Blob
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.citation_lookups import CitationLookups
from dial_deep_research.app.research.data_queries import DataQueryStore
from dial_deep_research.app.research.nodes import ReportReviewOutcome, revision_instruction
from dial_deep_research.app.research.prompts import (
    ReportReview,
    ResearchReview,
    render_protected_section_names,
    render_report_structure,
    render_report_system_prompt,
)
from dial_deep_research.app.research.report_length import LENGTH_EXEMPTIONS
from dial_deep_research.app.research.report_rules import (
    build_report_rules,
    render_writer_instructions,
)
from dial_deep_research.app.research.state import ReportReviewRound
from dial_deep_research.app_properties import (
    DEFAULT_REPORT_STRUCTURE,
    DocumentMetadataSource,
    ReportSection,
)
from dial_deep_research.utils.content import count_image_blocks, count_words
from tests.citation_fakes import no_lookups
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_TODAY = "2026-07-16"

# The section the app appends, named in the configuration rather than in the structure.
_REFERENCES_NAME = "References"

_CUSTOM_SECTIONS = [
    ReportSection(name="Summary", description="Two paragraphs answering the question."),
    ReportSection(
        name="Evidence",
        description="A table with the columns `claim` and `source`.",
        protected=True,
    ),
    ReportSection(name="Outlook", description="What follows, where the findings support it."),
]


_ONE_SECTION = [ReportSection(name="Summary", description="The answer.", protected=True)]


def _conforming_draft(body: str, sections: list[ReportSection] | None = None) -> str:
    """A draft whose headings satisfy the structure rule, so only the rule under test can fire."""
    return "\n\n".join(f"## {section.name}\n\n{body}" for section in (sections or _ONE_SECTION))


def _state(**overrides: Any) -> Any:
    """A post-research graph state: research done, no draft yet."""
    state: dict[str, Any] = {
        "research_agent_messages": [HumanMessage(content="Research question:\nq\n\n1. step one")],
        "research_query": "what happened to inflation?",
        "approved_plan": ["step one"],
        "research_iteration": 1,
        "research_reviews": [],
        "reports": [],
        "report_reviews": [],
        "report_revision_failed": False,
    }
    return {**state, **overrides}


def _round(*rule_violations: str, draft_number: int = 1) -> ReportReviewRound:
    """A review round whose only violations are the app's own rules' `rule_violations`."""
    return ReportReviewRound(
        draft_number=draft_number,
        rule_violations=list(rule_violations),
        blind_review=None,
        grounded_review=None,
    )


def _instruction_after(state: dict[str, Any], result: dict[str, Any]) -> str | None:
    """The revision instruction the state holds once the node's `result` is applied."""
    return revision_instruction({**state, **result})


# --- the report node ----------------------------------------------------------------------------


class _RecordingReportLLM:
    """Returns the canned drafts in turn, recording the messages each call received."""

    def __init__(self, *drafts: str) -> None:
        self._drafts = list(drafts)
        self.calls: list[list[BaseMessage]] = []

    async def __call__(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        return AIMessage(content=self._drafts[len(self.calls) - 1])


class _FailingReportLLM:
    """Fails on a non-retryable error, the kind a longer revision request is likelier to hit."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls += 1
        raise ValueError("maximum context length exceeded")


def _report_node(
    llm: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sections: list[ReportSection] | None = None,
    max_words: int = 2750,
    failures: list[nodes.ReportRevisionFailure] | None = None,
) -> Any:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: RunnableLambda(llm))
    return nodes.make_report_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date=_TODAY,
        sections=sections if sections is not None else DEFAULT_REPORT_STRUCTURE,
        max_words=max_words,
        references_name=_REFERENCES_NAME,
        lookups=no_lookups(),
        data_sources="The topics map.",
        glossary=None,
        emit_revision_failed_stage=(failures.append if failures is not None else lambda _o: None),
        emit_activity=lambda _title: None,
    )


async def test_first_draft_asks_for_the_report_over_the_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("the report")
    node = _report_node(llm, monkeypatch)

    result = await node(_state())

    assert result == {"reports": ["the report"]}
    [messages] = llm.calls
    # System prompt, the research transcript, then the report request — and nothing else.
    assert len(messages) == 3
    assert isinstance(messages[0], SystemMessage)
    assert "1. step one" in messages[1].content
    assert "what happened to inflation?" in messages[2].content


async def test_report_generated_logs_the_message_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm = _RecordingReportLLM("the report")
    node = _report_node(llm, monkeypatch)
    caplog.set_level(logging.INFO, logger=nodes.__name__)

    await node(_state())

    [messages] = llm.calls
    records = [record.getMessage() for record in caplog.records]
    assert any(f"messages={len(messages)}" in record for record in records)


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

    assert len(result["reports"]) == 1


async def test_a_revision_is_written_whenever_a_draft_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = "one two three four five six seven"
    llm = _RecordingReportLLM("the revised report")
    node = _report_node(llm, monkeypatch)

    result = await node(
        _state(reports=[previous], report_reviews=[_round("Restore the References section.")])
    )

    [messages] = llm.calls
    assert len(messages) == 4
    revision_request = messages[-1].content
    assert "1. Restore the References section." in revision_request
    assert previous in revision_request
    assert f"{count_words(previous)} words" in revision_request
    assert "2750" in revision_request
    assert result == {"reports": [previous, "the revised report"]}


async def test_a_revision_keeps_the_first_draft_message_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("draft one", "draft two")
    node = _report_node(llm, monkeypatch)

    await node(_state())
    await node(_state(reports=["draft one"], report_reviews=[_round("Shorten it.")]))

    first_draft_messages, revision_messages = llm.calls
    # The revision request is appended, never inserted before the transcript, so the byte prefix
    # the provider's prompt cache holds is unchanged.
    assert revision_messages[:3] == first_draft_messages
    assert len(revision_messages) == 4


async def test_each_draft_is_appended_after_the_previous_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingReportLLM("the second revision")
    node = _report_node(llm, monkeypatch)

    result = await node(
        _state(
            reports=["the first draft", "the first revision"],
            report_reviews=[_round("Again.", draft_number=1), _round("Again.", draft_number=2)],
        )
    )

    assert result == {"reports": ["the first draft", "the first revision", "the second revision"]}


async def test_a_failed_revision_keeps_the_previous_draft(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm = _FailingReportLLM()
    failures: list[nodes.ReportRevisionFailure] = []
    node = _report_node(llm, monkeypatch, failures=failures)
    caplog.set_level(logging.WARNING, logger=nodes.__name__)

    result = await node(_state(reports=["draft one"], report_reviews=[_round("Shorten it.")]))

    # Nothing is appended to `reports`, so the previous draft stays the one that is delivered.
    assert result == {"report_revision_failed": True}
    assert llm.calls == 1
    # Without this the run would end on a review stage asking for a revision that never arrives.
    [failure] = failures
    assert (failure.failed_draft_number, failure.delivered_draft_number) == (2, 1)
    assert failure.error == "ValueError"
    # The failed call still gets a duration and a message count, even though it produced no draft.
    [record] = caplog.records
    text = record.getMessage()
    assert "duration=" in text
    assert "messages=4" in text  # system, transcript, report request, revision request
    assert "tokens=n/a" in text  # no response to read usage from, marked unavailable like elsewhere


async def test_a_failed_first_draft_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nothing to fall back to: the turn fails and the DIAL error path carries it.
    llm = _FailingReportLLM()
    failures: list[nodes.ReportRevisionFailure] = []
    node = _report_node(llm, monkeypatch, failures=failures)

    with pytest.raises(ValueError):
        await node(_state())

    # No hand-off happened, so there is none to announce.
    assert failures == []


# --- the report-review node ---------------------------------------------------------------------


class _FakeReviewLLM:
    """A structured-output LLM returning one canned result, or raising it.

    Records the messages of each call so the request's own contract can be checked. The
    grounded review, a plain call on the same model, answers `grounded_answer` and is not
    recorded.
    """

    def __init__(
        self, result: dict[str, Any] | Exception, *, grounded_answer: str = "No violations."
    ) -> None:
        self._result = result
        self._grounded_answer = grounded_answer
        self.calls: list[list[BaseMessage]] = []
        self.grounded_review_calls = 0

    def with_retry(self, **kwargs: Any) -> _FakeReviewLLM:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.grounded_review_calls += 1
        return AIMessage(content=self._grounded_answer)

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
    lookups: CitationLookups | None = None,
) -> tuple[Any, list[ReportReviewOutcome]]:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    stages: list[ReportReviewOutcome] = []
    node = nodes.make_report_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date=_TODAY,
        sections=sections if sections is not None else DEFAULT_REPORT_STRUCTURE,
        max_words=max_words,
        references_name=_REFERENCES_NAME,
        lookups=lookups or no_lookups(),
        data_sources="The topics map.",
        glossary=None,
        glossary_fetch_listed_terms=False,
        emit_result_stage=stages.append,
        emit_activity=lambda _title: None,
    )
    return node, stages


async def test_an_approved_draft_within_the_ceiling_is_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    state = _state(reports=[_conforming_draft("a short draft")])
    result = await node(state)

    assert _instruction_after(state, result) is None
    # The round is stored whole: each review's response, beside the app's own rules' findings.
    [review_round] = result["report_reviews"]
    assert review_round == ReportReviewRound(
        draft_number=1,
        rule_violations=[],
        blind_review=ReportReview(report_violations=[]),
        grounded_review="No violations.",
    )
    [outcome] = stages
    assert outcome.violations == []
    assert outcome.blind_review_error is None
    assert outcome.draft_number == 1
    # The heading's two words count with the body's three.
    assert outcome.word_count == 5


async def test_the_review_looks_up_cited_documents_before_checking_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identifier rules read what the review's own lookup learned about this draft."""

    class _Resource:
        async def get_resources(self, _server_name: str, *, uris: list[str]) -> list[Blob]:
            return [Blob.from_data(data=json.dumps({"207": {}}), mime_type="application/json")]

    lookups = CitationLookups(
        dataset_tool=None,
        client=cast(MultiServerMCPClient, _Resource()),
        document_source=DocumentMetadataSource(
            server_name="documents",
            resource_template="documents://metadata/{document_ids}",
            title_key="publication_title",
        ),
        data_queries=DataQueryStore(),
    )
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION, lookups=lookups)

    await node(_state(reports=[_conforming_draft("A [doc 207, page 1]. B [doc 999, page 2].")]))

    [outcome] = stages
    [violation] = outcome.violations
    assert "document 999" in violation


async def test_violations_become_the_revision_instruction_and_reach_the_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    violation = "The References section was dropped; restore it with the source tables."
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[violation])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    state = _state(reports=[_conforming_draft("a short draft")])
    result = await node(state)

    assert _instruction_after(state, result) == f"1. {violation}"
    [outcome] = stages
    assert outcome.violations == [violation]
    assert outcome.blind_review_error is None


async def test_an_approving_review_cannot_pass_an_over_ceiling_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION, max_words=3)

    state = _state(reports=[_conforming_draft("one two three four five")])
    result = await node(state)

    assert _instruction_after(state, result) is not None
    [outcome] = stages
    # The count is the app's: the length violation joins the list even though the model
    # reported none, so the stage shows why the revision happens.
    [length_violation] = outcome.violations
    assert "7 words" in length_violation
    assert "3-word ceiling" in length_violation
    assert outcome.blind_review_error is None


async def test_citations_do_not_push_a_draft_over_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Six counted words, the heading's two included, against a ceiling of six: the citation is
    # outside the measure, so this draft is delivered as it stands.
    draft = "## Summary\n\nThe rate rose sharply [doc 150, page 3]."
    sections = [ReportSection(name="Summary", description="The answer.", protected=True)]
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=sections, max_words=6)

    state = _state(reports=[draft])
    result = await node(state)

    assert _instruction_after(state, result) is None
    [outcome] = stages
    assert outcome.word_count == 6
    assert outcome.violations == []


async def test_a_references_section_the_writer_wrote_is_a_violation_and_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app appends that section, so a draft carrying one earns a violation, not free words."""
    draft = (
        "## Summary\n\nThe rate rose sharply [doc 150, page 3].\n\n"
        "## References\n\n| doc id | title |\n| 150 | The annual report on rates |\n"
    )
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION, max_words=6)

    state = _state(reports=[draft])
    result = await node(state)

    [outcome] = stages
    # The section's own words are counted, so the draft is over a ceiling it would otherwise meet.
    assert outcome.word_count > 6
    assert _instruction_after(state, result) is not None
    # It is reported as the extra `##` heading it is, the configured structure naming no such
    # section.
    assert any("References" in violation for violation in outcome.violations)


async def test_a_rule_violation_survives_an_approving_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The structure rule is the app's own: an approving model cannot pass a draft that renamed a
    # section, and the stage shows the rule's own wording.
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    state = _state(reports=["## Overview\n\nThe answer."])
    result = await node(state)

    assert _instruction_after(state, result) is not None
    [outcome] = stages
    # One violation, naming the section the structure requires and the one the draft wrote.
    [violation] = outcome.violations
    assert "'Summary'" in violation
    assert "'Overview'" in violation
    assert outcome.blind_review_error is None


async def test_a_failed_review_call_still_shortens_an_over_long_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(RuntimeError("provider is down"))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION, max_words=3)

    state = _state(reports=[_conforming_draft("one two three four five")])
    result = await node(state)

    assert _instruction_after(state, result) is not None
    [outcome] = stages
    # The failure and the length violation are separate facts, and both stay visible.
    assert outcome.blind_review_error == "RuntimeError"
    [length_violation] = outcome.violations
    assert "7 words" in length_violation


async def test_a_failed_review_call_delivers_a_draft_within_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(RuntimeError("provider is down"))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    state = _state(reports=[_conforming_draft("a short draft")])
    result = await node(state)

    assert _instruction_after(state, result) is None
    # The failed call is stored as an absent response, never as an approval.
    [review_round] = result["report_reviews"]
    assert review_round.blind_review is None
    # The failure is visible as a stage of its own, with nothing to revise against.
    [outcome] = stages
    assert outcome.blind_review_error == "RuntimeError"
    assert outcome.violations == []


async def test_a_failed_blind_review_leaves_the_rules_and_the_grounded_items_to_revise_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grounded_item = "The 2025 figure appears on no page the research retrieved."
    llm = _FakeReviewLLM(RuntimeError("provider is down"), grounded_answer=f"1. {grounded_item}")
    node, _ = _review_node(llm, monkeypatch, sections=_ONE_SECTION, max_words=3)

    state = _state(reports=[_conforming_draft("one two three four five")])
    result = await node(state)

    [review_round] = result["report_reviews"]
    assert review_round.blind_review is None
    [length_violation] = review_round.rule_violations
    assert _instruction_after(state, result) == f"1. {length_violation}\n2. {grounded_item}"


async def test_an_empty_grounded_answer_is_stored_as_absent_and_the_round_stays_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty answer checked nothing: it is stored as no response, so the router and the writer
    read the round without parsing it again."""
    violation = "Drop 'Confidence: High' from the summary."
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[violation])), grounded_answer="")
    review_node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    draft = _conforming_draft("a short draft")
    state = _state(reports=[draft])
    state = {**state, **await review_node(state)}

    [review_round] = state["report_reviews"]
    assert review_round.grounded_review is None
    [outcome] = stages
    assert outcome.grounded_review_error == "EmptyReviewAnswerError"
    assert nodes.route_after_report_review()(state) == "report"

    writer = _RecordingReportLLM("the revised report")
    report_node = _report_node(writer, monkeypatch, sections=_ONE_SECTION)
    result = await report_node(state)

    assert result == {"reports": [draft, "the revised report"]}
    revision_request = writer.calls[0][-1].content
    assert f"1. {violation}" in revision_request


async def test_an_unparseable_verdict_is_absorbed_like_a_failed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_UNPARSEABLE)
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    state = _state(reports=[_conforming_draft("a short draft")])
    result = await node(state)

    assert _instruction_after(state, result) is None
    assert result["report_reviews"][0].blind_review is None
    [outcome] = stages
    assert outcome.blind_review_error == "ValueError"
    assert outcome.violations == []


async def test_a_verdict_with_no_structured_output_is_a_failed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer without a tool call parses to nothing without a parsing error; it checked
    nothing, so it is reported as a failed call, never as an approval."""
    llm = _FakeReviewLLM({"parsed": None, "parsing_error": None, "raw": AIMessage(content="")})
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)

    result = await node(_state(reports=[_conforming_draft("a short draft")]))

    assert result["report_reviews"][0].blind_review is None
    [outcome] = stages
    assert outcome.blind_review_error == "ValueError"


@pytest.mark.parametrize("answer", ["", "   "])
def test_a_blank_stored_grounded_review_contributes_nothing(answer: str) -> None:
    review_round = ReportReviewRound(
        draft_number=1, rule_violations=["Shorten it."], blind_review=None, grounded_review=answer
    )

    assert nodes.review_violations(review_round) == ["Shorten it."]


async def test_the_logged_duration_is_the_call_only_not_the_whole_node(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The stage may report the whole node's time; the log reports a narrower measurement.

    A real clock (an infinite, monotonically increasing fake) is used rather than a fixed
    sequence: `time.monotonic` is the same global function LangChain's own retry and callback
    machinery calls too, so a short canned sequence undercounts and raises `StopIteration`.
    """
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)
    tick = count()
    monkeypatch.setattr(nodes.time, "monotonic", lambda: next(tick) * 1.0)
    caplog.set_level(logging.INFO, logger=nodes.__name__)

    await node(_state(reports=[_conforming_draft("a short draft")]))

    [stage] = stages
    records = [record.getMessage() for record in caplog.records]
    [logged] = [r for r in records if r.startswith("Report blind-reviewed")]
    logged_duration = float(re.search(r"duration=(\d+\.\d+)s", logged)[1])
    # The call starts strictly after the node does and the node's own duration is computed
    # strictly after the call returns, so the logged (call-only) duration is always the smaller
    # of the two, however many extra ticks LangChain's internals consume in between.
    assert logged_duration < stage.duration_seconds


async def test_violations_reach_the_stage_but_never_a_log_record(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The asymmetry is the requirement: the stage shows the violations, the log counts them."""
    violation = "The draft ends with 'Confidence: High (3 sources)'; remove it."
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[violation])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION)
    caplog.set_level(logging.DEBUG, logger=nodes.__name__)

    await node(_state(reports=[_conforming_draft("a short draft")]))

    assert stages[0].violations == [violation]
    records = [record.getMessage() for record in caplog.records]
    assert any("violations=1" in record for record in records)
    assert any("messages=2" in record for record in records)
    assert not any(violation in record for record in records)
    # Nor does the draft it judges.
    assert not any("a short draft" in record for record in records)


async def test_the_stage_reports_the_draft_being_reviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, stages = _review_node(llm, monkeypatch, sections=_ONE_SECTION, max_words=1200)

    await node(_state(reports=["the first draft", _conforming_draft("a short draft")]))

    [outcome] = stages
    # The draft number is the count of drafts written: this is the second one.
    assert outcome.draft_number == 2
    assert outcome.max_words == 1200


async def test_the_review_request_carries_neither_findings_nor_a_research_review_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = "one two three four five six seven eight nine"
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, _ = _review_node(llm, monkeypatch, sections=_CUSTOM_SECTIONS)

    await node(
        _state(
            reports=[draft],
            research_agent_messages=[
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
            approved_plan=["the approved plan step"],
            research_reviews=[
                ResearchReview(
                    assessment="One step is open.",
                    next_steps=["a step research-review authored"],
                )
            ],
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
    # Stable content first, the draft last, for prefix stability.
    assert request.rstrip().endswith(f"<draft>\n{draft}\n</draft>")
    assert request.index("Summary") < request.index(draft)
    # Length is judged in Python, not by the review model: neither number reaches the request.
    assert f"{count_words(draft)}" not in request
    assert "2750" not in request


async def test_the_review_system_prompt_makes_a_written_references_section_a_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One check carries both halves: report a list of sources, and never demand one.

    The app's structure check sees only `##` headings, so a list written under a sub-heading, in
    bold, or with no heading at all reaches the reader unless the review reports it. Demanding one
    needs no rule of its own — the reviewer's job is the checks alone, and this check makes such a
    section a violation, so asking for one would be asking for a violation.
    """
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, _ = _review_node(llm, monkeypatch, sections=_CUSTOM_SECTIONS)

    await node(_state(reports=["one two three"]))

    [system, request] = llm.calls[0]
    assert isinstance(system.content, str)
    assert "6. **No list of sources.**" in system.content
    # What is forbidden is an enumeration, in any of the forms one can take. Naming the heading
    # cases here is what keeps the check from being read as the app's heading check.
    assert "no section, table or" in system.content
    assert "under a bold line standing in for one, or under nothing at all" in system.content
    # Why the rule holds, and that an instruction in the question or the plan does not lift it.
    assert "The application" in system.content
    assert "whatever the question or the plan asked for" in system.content
    # The two things that are not that list, and that a section may be required to carry.
    assert "the inline citations, and prose describing the evidence" in system.content

    # Stated once: the per-turn request carries no copy and needs no section name to render.
    assert isinstance(request.content, str)
    assert "check 6" not in request.content
    assert _REFERENCES_NAME not in request.content


async def test_the_review_system_prompt_can_decide_the_dataset_citation_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The citation check is worded against a citation's shape, which is all this call can see.

    The blind review receives neither the transcript nor any tool result, so "is this the
    identifier the dataset tool reported?" is a question it cannot answer, and a model asked it
    resolves it by guessing — a readable name inside a URN reads as a display name. It is given
    an example and told to judge the shape instead.
    """
    llm = _FakeReviewLLM(_parsed(ReportReview(report_violations=[])))
    node, _ = _review_node(llm, monkeypatch, sections=_CUSTOM_SECTIONS)

    await node(_state(reports=["one two three"]))

    [system, request] = llm.calls[0]
    assert isinstance(system.content, str)
    # The shape a URN takes, so a readable name inside one is not read as a display name, and
    # the same example the writer is given, so the two cannot drift on what a URN looks like.
    assert "<agency>:<dataset_name>(version)" in system.content
    assert "IMF:WEO(1.0.0)" in system.content
    assert "You cannot" in system.content and "see what the tool reported" in system.content
    # The failure the check does target, named as the counter-example.
    assert "Example of incorrect citation: `[dataset World Economic Outlook]`." in system.content

    # The findings stay out of the call, which is why the check has to be decidable without them.
    assert isinstance(request.content, str)
    assert "one two three" in request.content


# --- prompt rendering ---------------------------------------------------------------------------


def test_render_report_structure_keeps_names_and_descriptions_verbatim_in_order() -> None:
    rendered = render_report_structure(_CUSTOM_SECTIONS)

    for section in _CUSTOM_SECTIONS:
        assert section.name in rendered
        assert section.description in rendered
    assert rendered.index("Summary") < rendered.index("Evidence") < rendered.index("Outlook")
    # A configured structure replaces the default rather than extending it.
    assert "Key Findings" not in rendered


def test_render_report_structure_carries_no_marker_on_a_section_name() -> None:
    # The prompt tells the writer to use these names as the report's headings, so a name is
    # rendered alone; protection is stated by the prompt's own precedence rule instead.
    rendered = render_report_structure(_CUSTOM_SECTIONS)

    assert "PROTECTED" not in rendered
    assert "## Evidence\n" in rendered


def test_render_report_structure_renders_every_configured_section() -> None:
    """Nothing is subtracted: the References section is no part of a configured structure."""
    sections = [*_CUSTOM_SECTIONS, ReportSection(name="Annex", description="The tables.")]

    rendered = render_report_structure(sections)

    for section in sections:
        assert f"## {section.name}" in rendered
        assert section.description in rendered


def test_render_protected_section_names_lists_only_the_protected_ones() -> None:
    assert render_protected_section_names(_CUSTOM_SECTIONS) == "Evidence"
    # References is protected and still left out: the app writes it, so no user instruction the
    # precedence rule governs could drop it in the first place.
    assert render_protected_section_names(DEFAULT_REPORT_STRUCTURE) == "Overview"
    two_protected = [
        _CUSTOM_SECTIONS[0],
        _CUSTOM_SECTIONS[1],
        ReportSection(name="Outlook", description="What follows.", protected=True),
    ]
    assert render_protected_section_names(two_protected) == "Evidence, Outlook"


def test_the_length_exemption_is_the_citations_whatever_the_structure() -> None:
    """The app writes the references section after the loop, so no draft carries one to exempt."""
    assert LENGTH_EXEMPTIONS == "the inline citations"


def test_report_system_prompt_states_the_ceiling_and_the_protected_names() -> None:
    prompt = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date=_TODAY,
        rules=render_writer_instructions(
            build_report_rules(
                sections=DEFAULT_REPORT_STRUCTURE,
                max_words=2750,
                references_name=_REFERENCES_NAME,
                lookups=no_lookups(),
            )
        ),
        protected_sections=render_protected_section_names(DEFAULT_REPORT_STRUCTURE),
        data_sources="The topics map.",
        glossary=False,
    )

    assert "2750 words" in prompt
    # Named once, in the rule telling the writer not to write it: the app builds that section,
    # so it is neither a heading to copy nor a name in the precedence rule.
    assert "## References" not in prompt
    assert 'Do not write a "References" section' in prompt
    # Report-wide rules are the prompt's own, not a section's.
    assert "[doc <id>, page <ix>]" in prompt
