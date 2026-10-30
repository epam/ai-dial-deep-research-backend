"""The research state's lists through a real compiled research graph (research-resume spec).

Research-review, the writer and report-review are the real nodes over fake models; research-agent
is a stub that adds one tool call per iteration. The lists are followed through one run, a failed
run's snapshot, its resume, a resumed run that fails again, and a completed run's record.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from dial_deep_research.app.history import CrossTurnPrepState, Plan
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.prompts import (
    GROUNDED_REVIEW_SYSTEM_MESSAGE,
    REPORT_REQUEST,
    ReportReview,
    ResearchReview,
)
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.research.snapshot import (
    NotResumableReason,
    ResearchSnapshot,
    ResumableSnapshot,
    ResumePoint,
    build_completed_record,
    build_snapshot,
    read_snapshot,
)
from dial_deep_research.app.research.state import (
    ReportReviewRound,
    build_initial_state,
    build_resumed_state,
)
from dial_deep_research.app_properties import ReportSection
from tests.citation_fakes import no_lookups
from tests.dial_spies import ChoiceSpy
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_PLAN_ID = "0123abcd0123abcd0123abcd0123abcd"
_QUERY = "How did inflation change in 2024?"
_APPROVED_PLAN = ["Find the annual inflation rate for IMF:WEO."]
_NEXT_STEPS = ["Find the monthly inflation rate."]
_SECTIONS = [ReportSection(name="Summary", description="The answer.", protected=True)]

_REVIEW_ONE = ResearchReview(assessment="The monthly rate is missing.", next_steps=_NEXT_STEPS)
_REVIEW_TWO = ResearchReview(assessment="Every plan item is covered.", next_steps=[])
_DRAFTS = [f"## Summary\n\nDraft {number}." for number in (1, 2, 3)]
_BLIND = ReportReview(report_violations=["Cut the padding."])
_GROUNDED = "1. Cite the annual rate."


class _FailureError(Exception):
    """A failure that propagates out of the graph, as a quota error does."""


class _Models:
    """Every model call of the research graph's nodes but research-agent's, scripted in order."""

    def __init__(
        self,
        *,
        research_reviews: list[ResearchReview | Exception] | None = None,
        drafts: list[str | Exception] | None = None,
        blind_reviews: list[ReportReview] | None = None,
        grounded_answers: list[str] | None = None,
    ) -> None:
        self._research_reviews = list(research_reviews or [])
        self._drafts = list(drafts or [])
        self._blind_reviews = list(blind_reviews or [])
        self._grounded_answers = list(grounded_answers or [])
        self.writer_calls: list[list[BaseMessage]] = []
        self.research_review_calls: list[list[BaseMessage]] = []

    def with_retry(self, **_kwargs: Any) -> _Models:
        return self

    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _Structured:
        return _Structured(self, schema)

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        if messages[0].content == GROUNDED_REVIEW_SYSTEM_MESSAGE:
            return AIMessage(content=self._grounded_answers.pop(0))
        self.writer_calls.append(list(messages))
        draft = self._drafts.pop(0)
        if isinstance(draft, Exception):
            raise draft
        return AIMessage(content=draft)

    def structured(self, schema: Any, messages: list[BaseMessage]) -> Any:
        if schema is ResearchReview:
            self.research_review_calls.append(list(messages))
            review = self._research_reviews.pop(0)
            if isinstance(review, Exception):
                raise review
            return review
        return self._blind_reviews.pop(0)


class _Structured:
    def __init__(self, models: _Models, schema: Any) -> None:
        self._models = models
        self._schema = schema

    def with_retry(self, **_kwargs: Any) -> _Structured:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        parsed = self._models.structured(self._schema, messages)
        return {"parsed": parsed, "raw": AIMessage(content=""), "parsing_error": None}


class _ResearchAgent:
    """research-agent: one tool call and its result per iteration, ids numbered by iteration."""

    async def ainvoke(self, agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
        messages = agent_input["messages"]
        iteration = sum(isinstance(m, HumanMessage) for m in messages)
        call = {"id": f"c{iteration}", "name": "rag_search", "args": {"query": "inflation"}}
        return {
            "messages": [
                *messages,
                AIMessage(content="", tool_calls=[call], id=f"a{iteration}"),
                ToolMessage(content=f"result {iteration}", tool_call_id=f"c{iteration}"),
            ]
        }


def _compile(
    monkeypatch: pytest.MonkeyPatch,
    models: _Models,
    *,
    entry: ResumePoint = ResumePoint.RESEARCH,
    prefetch_fails_on: int = 0,
) -> Any:
    monkeypatch.setattr(graph_module, "build_research_agent", lambda *a, **kw: _ResearchAgent())
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: models)
    lookups = no_lookups()
    if prefetch_fails_on:
        prefetch = lookups.prefetch
        calls = 0

        async def failing_prefetch(draft: str) -> None:
            nonlocal calls
            calls += 1
            if calls == prefetch_fails_on:
                raise _FailureError("report review failed outside its two calls")
            await prefetch(draft)

        lookups.prefetch = failing_prefetch  # type: ignore[method-assign]
    return build_research_graph(
        tools=[],
        today_date="2026-10-30",
        max_research_iterations=10,
        client_name="ACME",
        report_structure=_SECTIONS,
        max_report_words=2750,
        max_report_versions=3,
        references_section_name="References",
        citation_lookups=lookups,
        data_sources="The topics map.",
        data_sources_instructions="",
        glossary=None,
        glossary_fetch_listed_terms=False,
        client_rules=(),
        source_kinds=BOTH_SOURCE_KINDS,
        emit_research_review_result_stage=lambda _outcome: None,
        emit_research_budget_exhausted=lambda _outcome: None,
        emit_report_review_result_stage=lambda _outcome: None,
        emit_report_revision_failed=lambda _outcome: None,
        emit_report_budget_exhausted=lambda _outcome: None,
        emit_activity=lambda _title: None,
        entry=entry,
    )


def _initial_state() -> dict[str, Any]:
    prep = CrossTurnPrepState(
        current_query=_QUERY, plan=Plan(steps=_APPROVED_PLAN), plan_id=_PLAN_ID
    )
    return dict(build_initial_state(prep))


async def _stream(graph: Any, state: dict[str, Any], *, entry: ResumePoint) -> ResearchRunner:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    await runner._stream_graph(graph, state, config={"recursion_limit": 100}, entry=entry)
    return runner


async def _stream_until_it_fails(
    graph: Any, state: dict[str, Any], *, entry: ResumePoint
) -> ResearchRunner:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    with pytest.raises(_FailureError):
        await runner._stream_graph(graph, state, config={"recursion_limit": 100}, entry=entry)
    return runner


async def _snapshot_of(runner: ResearchRunner) -> ResumableSnapshot:
    """The failed run's snapshot, saved and read back as a later turn reads it."""
    progress = runner.captured_progress()
    assert progress is not None
    snapshot = await build_snapshot(
        progress, plan_id=_PLAN_ID, repeating_failure=False, dial=None  # type: ignore[arg-type]
    )
    resumed = read_snapshot(snapshot.model_dump(mode="json"), current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)
    return resumed


def _report_request(call: list[BaseMessage]) -> str:
    """The writer's request, which carries the query and the iteration plans."""
    [request] = [
        m.content
        for m in call
        if isinstance(m, HumanMessage) and str(m.content).startswith(REPORT_REQUEST[:20])
    ]
    return str(request)


def _ids(messages: list[BaseMessage]) -> list[str | None]:
    return [m.id for m in messages]


async def test_the_lists_are_written_and_read_in_one_run(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _Models(
        research_reviews=[_REVIEW_ONE, _REVIEW_TWO],
        drafts=list(_DRAFTS),
        blind_reviews=[_BLIND, _BLIND],
        grounded_answers=[_GROUNDED, _GROUNDED],
    )
    graph = _compile(monkeypatch, models)

    runner = await _stream(graph, _initial_state(), entry=ResumePoint.RESEARCH)

    final = runner._root_state
    assert final is not None
    assert final["research_iteration"] == 2
    assert final["research_reviews"] == [_REVIEW_ONE, _REVIEW_TWO]
    assert final["reports"] == _DRAFTS
    assert [r.draft_number for r in final["report_reviews"]] == [1, 2]
    assert final["report_reviews"][0].blind_review == _BLIND
    assert final["report_reviews"][0].grounded_review == _GROUNDED
    # Routing counted two plans, and both the second review and the writer list them.
    plans = f"Plan 1:\n1. {_APPROVED_PLAN[0]}\n\nPlan 2:\n1. {_NEXT_STEPS[0]}"
    assert plans in str(models.research_review_calls[1][-1].content)
    assert _report_request(models.writer_calls[0]) == REPORT_REQUEST.format(
        query=_QUERY, plans=plans
    )
    # The revision instruction comes from the latest round only.
    revision = str(models.writer_calls[1][-1].content)
    assert "Cut the padding." in revision and "Cite the annual rate." in revision


async def test_a_completed_runs_record_holds_every_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _Models(
        research_reviews=[_REVIEW_ONE, _REVIEW_TWO],
        drafts=list(_DRAFTS),
        blind_reviews=[_BLIND, _BLIND],
        grounded_answers=[_GROUNDED, _GROUNDED],
    )
    runner = await _stream(
        _compile(monkeypatch, models), _initial_state(), entry=ResumePoint.RESEARCH
    )

    record = build_completed_record(runner.completed_progress(), plan_id=_PLAN_ID)

    read_back = ResearchSnapshot.model_validate(record.model_dump(mode="json"))
    assert (read_back.resumable, read_back.not_resumable_reason, read_back.resume_at) == (
        False,
        NotResumableReason.COMPLETED,
        None,
    )
    assert read_back.research_reviews == [_REVIEW_ONE, _REVIEW_TWO]
    assert read_back.reports == _DRAFTS
    assert [r.draft_number for r in read_back.report_reviews] == [1, 2]
    # Research-agent's two calls, and no message of the report.
    ai_messages = [m["data"] for m in read_back.research_agent_messages if m["type"] == "ai"]
    assert [m["id"] for m in ai_messages] == ["a1", "a2"]
    assert all(m["tool_calls"] and not m["content"] for m in ai_messages)


async def test_a_failed_runs_snapshot_holds_the_lists_and_the_resumed_nodes_use_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fresh run fails in report-review's second round, outside its two model calls.
    fresh_models = _Models(
        research_reviews=[_REVIEW_ONE, _REVIEW_TWO],
        drafts=list(_DRAFTS[:2]),
        blind_reviews=[_BLIND, _BLIND],
        grounded_answers=[_GROUNDED, _GROUNDED],
    )
    failed = await _stream_until_it_fails(
        _compile(monkeypatch, fresh_models, prefetch_fails_on=2),
        _initial_state(),
        entry=ResumePoint.RESEARCH,
    )

    resumed = await _snapshot_of(failed)

    snapshot = resumed.snapshot
    assert snapshot.resume_at is ResumePoint.REPORT_REVIEW
    assert snapshot.research_reviews == [_REVIEW_ONE, _REVIEW_TWO]
    assert all(isinstance(review, ResearchReview) for review in snapshot.research_reviews)
    assert snapshot.reports == _DRAFTS[:2]
    [round_one] = snapshot.report_reviews
    assert isinstance(round_one, ReportReviewRound)
    assert round_one == failed._root_state["report_reviews"][0]  # type: ignore[index]

    # The resumed run reviews draft 2, then writes draft 3 from that round's instruction.
    resumed_models = _Models(
        drafts=[_DRAFTS[2]], blind_reviews=[_BLIND], grounded_answers=["No violations."]
    )
    runner = await _stream(
        _compile(monkeypatch, resumed_models, entry=resumed.resume_at),
        dict(build_resumed_state(resumed)),
        entry=resumed.resume_at,
    )

    final = runner._root_state
    assert final is not None
    assert final["reports"] == _DRAFTS
    assert [r.draft_number for r in final["report_reviews"]] == [1, 2]
    assert final["report_reviews"][0] == round_one
    [writer_call] = resumed_models.writer_calls
    # The resumed writer lists the same plans as the fresh run's writer did.
    assert _report_request(writer_call) == _report_request(fresh_models.writer_calls[0])
    revision = str(writer_call[-1].content)
    assert "Cut the padding." in revision and "Cite the annual rate." not in revision


async def test_a_resumed_run_that_fails_again_keeps_the_order_with_nothing_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fresh run fails in research-review after iteration 2.
    failed = await _stream_until_it_fails(
        _compile(
            monkeypatch, _Models(research_reviews=[_REVIEW_ONE, _FailureError("upstream 502")])
        ),
        _initial_state(),
        entry=ResumePoint.RESEARCH,
    )
    first = await _snapshot_of(failed)
    assert first.snapshot.resume_at is ResumePoint.RESEARCH_REVIEW
    assert first.snapshot.research_reviews == [_REVIEW_ONE]

    # The resumed run records its review, then the first draft fails.
    failed_again = await _stream_until_it_fails(
        _compile(
            monkeypatch,
            _Models(research_reviews=[_REVIEW_TWO], drafts=[_FailureError("quota")]),
            entry=first.resume_at,
        ),
        dict(build_resumed_state(first)),
        entry=first.resume_at,
    )
    second = await _snapshot_of(failed_again)

    assert second.snapshot.resume_at is ResumePoint.REPORT
    assert second.snapshot.research_reviews == [_REVIEW_ONE, _REVIEW_TWO]
    assert second.snapshot.research_iteration == 2
    assert second.snapshot.reports == []
    assert _ids(second.messages) == _ids(first.messages)
    assert len(set(_ids(second.messages))) == len(second.messages)
