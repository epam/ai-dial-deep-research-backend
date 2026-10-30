"""The research review's findings as a DIAL stage.

The node decides what to report and the runner decides how it looks, so these tests cover both
ends: what the outcome carries — including a verdict that has to match where the graph routes —
and the stage the runner renders from it beside the still-open activity stage. A review the
iteration cap skipped has no findings to show, and is announced by the router instead, in time to
precede the report's own stages.
"""

from __future__ import annotations

import logging
import re
from itertools import count
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from pytest import LogCaptureFixture, MonkeyPatch

from dial_deep_research.app.history import CrossTurnPrepState, Plan
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.nodes import (
    RESEARCH_REVIEW_ACTIVITY,
    ResearchBudgetExhausted,
    ResearchReviewOutcome,
)
from dial_deep_research.app.research.prompts import REPORT_REQUEST, ResearchReview
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.research.state import build_initial_state
from dial_deep_research.app_properties import ReportSection
from tests.citation_fakes import no_lookups
from tests.dial_spies import ChoiceSpy
from tests.mcp_fakes import BOTH_SOURCE_KINDS

pytestmark = pytest.mark.asyncio

_ASSESSMENT = "The 2025 figure rests on a search summary rather than on the source page."
_STEPS = ["Open the source page.", "Confirm the 2025 figure there."]

# One section, so a draft satisfies the structure rule with a single heading. The report side is
# only here to let a whole graph run finish.
_SECTIONS = [ReportSection(name="Summary", description="The answer.", protected=True)]


class _FakeReviewModel:
    """The research-review call: `with_structured_output(...).with_retry(...).ainvoke(...)`."""

    def __init__(self, review: ResearchReview) -> None:
        self._review = review
        self.calls = 0

    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _FakeReviewModel:
        return self

    def with_retry(self, **kwargs: Any) -> _FakeReviewModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        self.calls += 1
        return {"parsed": self._review, "raw": AIMessage(content=""), "parsing_error": None}


def _reviewed_state() -> dict[str, Any]:
    """The state research-review reads after one completed research iteration."""
    prep = CrossTurnPrepState(
        current_query="q", plan=Plan(steps=["step one"]), plan_approved=True, research_started=True
    )
    state = dict(build_initial_state(prep))
    state["research_iteration"] = 1
    return state


def _review_node(
    monkeypatch: MonkeyPatch, review: ResearchReview, max_research_iterations: int = 10
) -> tuple[Any, list[ResearchReviewOutcome]]:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: _FakeReviewModel(review))
    outcomes: list[ResearchReviewOutcome] = []
    node = nodes.make_research_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="2026-08-14",
        max_research_iterations=max_research_iterations,
        data_sources="The topics map.",
        emit_result_stage=outcomes.append,
        emit_activity=lambda _title: None,
        glossary=None,
    )
    return node, outcomes


async def test_the_outcome_carries_the_iteration_the_assessment_and_the_steps(
    monkeypatch: MonkeyPatch,
) -> None:
    node, outcomes = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS)
    )

    await node(_reviewed_state())

    [outcome] = outcomes
    assert outcome.research_iteration == 1
    assert outcome.max_research_iterations == 10
    assert outcome.assessment == _ASSESSMENT
    assert outcome.next_steps == _STEPS
    assert outcome.duration_seconds >= 0


async def test_uncovered_work_reports_the_continue_verdict(monkeypatch: MonkeyPatch) -> None:
    """The verdict comes from the function the router calls, so it names the route actually taken."""
    node, outcomes = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS)
    )

    update = await node(_reviewed_state())

    [outcome] = outcomes
    assert outcome.will_continue is True
    assert nodes.route_after_research_review()({**_reviewed_state(), **update}) == "research-agent"


async def test_full_coverage_reports_the_report_verdict(monkeypatch: MonkeyPatch) -> None:
    node, outcomes = _review_node(
        monkeypatch, ResearchReview(assessment="Every plan item is covered.", next_steps=[])
    )

    update = await node(_reviewed_state())

    [outcome] = outcomes
    assert outcome.will_continue is False
    assert outcome.next_steps == []
    assert nodes.route_after_research_review()({**_reviewed_state(), **update}) == "report"


def _apply(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """`state` after a node's `update`, with the transcript merged as the graph's reducer does."""
    merged = {**state, **update}
    if "research_agent_messages" in update:
        merged["research_agent_messages"] = add_messages(
            state["research_agent_messages"], update["research_agent_messages"]
        )
    return merged


class _RecordingReportModel:
    """The report call: `with_retry(...).ainvoke(...)`, recording the messages it received."""

    def __init__(self) -> None:
        self.calls: list[list[BaseMessage]] = []

    def with_retry(self, **kwargs: Any) -> _RecordingReportModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        return AIMessage(content="## Summary\n\nThe answer.")


async def test_each_iteration_plan_is_counted_and_reaches_the_writer_numbered(
    monkeypatch: MonkeyPatch,
) -> None:
    """The approved plan is plan 1 and the first review's next steps are plan 2: the router counts
    both, and the writer is told both, in that order."""
    route = nodes.route_after_research_review()
    state = _reviewed_state()

    first_review, _ = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS)
    )
    state = _apply(state, await first_review(state))
    assert len(nodes.iteration_plans(state)) == 2
    assert route(state) == "research-agent"

    # Research-agent ran the second iteration; the second review finds nothing left to do.
    state["research_iteration"] = 2
    second_review, _ = _review_node(
        monkeypatch, ResearchReview(assessment="Every plan item is covered.", next_steps=[])
    )
    state = _apply(state, await second_review(state))
    assert len(nodes.iteration_plans(state)) == 2
    assert route(state) == "report"

    model = _RecordingReportModel()
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
    report = nodes.make_report_node(
        today_date="2026-08-14",
        sections=_SECTIONS,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources="The topics map.",
        glossary=None,
        emit_revision_failed_stage=lambda _failure: None,
        emit_activity=lambda _title: None,
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
    )
    await report(state)

    [messages] = model.calls
    request = messages[-1]
    assert isinstance(request, HumanMessage)
    assert request.content == REPORT_REQUEST.format(
        query="q",
        plans=(
            "Plan 1:\n1. step one\n\n"
            "Plan 2:\n1. Open the source page.\n2. Confirm the 2025 figure there."
        ),
    )


async def test_the_logged_duration_is_the_call_only_not_the_whole_node(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """The stage may report the whole node's time; the log reports a narrower measurement.

    A real clock (an infinite, monotonically increasing fake) is used rather than a fixed
    sequence: `time.monotonic` is the same global function LangChain's own retry and callback
    machinery calls too, so a short canned sequence undercounts and raises `StopIteration`.
    """
    node, outcomes = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=[])
    )
    tick = count()
    monkeypatch.setattr(nodes.time, "monotonic", lambda: next(tick) * 1.0)
    caplog.set_level(logging.INFO, logger=nodes.__name__)

    await node(_reviewed_state())

    [outcome] = outcomes
    [record] = caplog.records
    logged_duration = float(re.search(r"duration=(\d+\.\d+)s", record.getMessage())[1])
    # The call starts strictly after the node does and the node's own duration is computed
    # strictly after the call returns, so the logged (call-only) duration is always the smaller
    # of the two, however many extra ticks LangChain's internals consume in between.
    assert logged_duration < outcome.duration_seconds


async def test_the_findings_never_reach_a_log_record(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """LLM response text belongs in the stage; the logs carry the step count."""
    node, _ = _review_node(monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS))

    with caplog.at_level(logging.DEBUG):
        await node(_reviewed_state())

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert _ASSESSMENT not in logged
    assert all(step not in logged for step in _STEPS)
    assert "next_plan_steps=2" in logged
    assert "messages=2" in logged


async def test_a_failed_review_call_emits_nothing_and_ends_the_turn(
    monkeypatch: MonkeyPatch,
) -> None:
    """This node re-raises instead of absorbing, so the failure travels to the DIAL error path
    and the runner closes the activity stage as failed. There is no outcome to report."""

    def _boom(_model_config: Any) -> Any:
        raise RuntimeError("the review call failed")

    monkeypatch.setattr(nodes, "get_chat_model", _boom)
    outcomes: list[ResearchReviewOutcome] = []
    node = nodes.make_research_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="2026-08-14",
        max_research_iterations=10,
        data_sources="The topics map.",
        emit_result_stage=outcomes.append,
        emit_activity=lambda _title: None,
        glossary=None,
    )

    with pytest.raises(RuntimeError):
        await node(_reviewed_state())

    assert outcomes == []


async def test_the_runner_renders_the_outcome_beside_the_open_activity_stage() -> None:
    choice = ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]
    runner._set_activity(RESEARCH_REVIEW_ACTIVITY)

    runner._emit_research_review_result_stage(
        ResearchReviewOutcome(
            research_iteration=1,
            max_research_iterations=10,
            assessment=_ASSESSMENT,
            next_steps=_STEPS,
            will_continue=True,
            duration_seconds=8.2,
        )
    )

    activity, result = choice.stages
    assert activity.opened and not activity.closed
    assert result.title == "[RESEARCH REVIEW RESULT] iteration 1 - continue 🔄 (8.20s)"
    assert _ASSESSMENT in result.body
    assert "1. Open the source page." in result.body
    assert result.closed


async def _run_graph_with_the_cap_reached(
    monkeypatch: MonkeyPatch, *, max_research_iterations: int
) -> tuple[dict[str, Any], list[Any], list[str]]:
    """Drive a whole run whose research ends on the cap, collecting what each emitter reported.

    The run starts one iteration short of the cap, so the stubbed research-agent's one pass reaches
    the router in the state a real run would after its last permitted iteration. A version budget
    of one turns the report review off, so the run needs no review model.
    """

    class _ResearchAgent:
        async def ainvoke(self, agent_input: dict[str, Any], config: Any = None) -> dict[str, Any]:
            return {"messages": agent_input["messages"]}

    class _ReportModel:
        def with_retry(self, **kwargs: Any) -> _ReportModel:
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            return AIMessage(content="## Summary\n\nThe answer.")

    monkeypatch.setattr(graph_module, "build_research_agent", lambda *a, **kw: _ResearchAgent())
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: _ReportModel())
    findings: list[Any] = []
    exhausted: list[Any] = []
    order: list[str] = []
    compiled = build_research_graph(
        tools=[],
        today_date="2026-08-14",
        max_research_iterations=max_research_iterations,
        client_name="ACME",
        report_structure=_SECTIONS,
        max_report_words=2750,
        max_report_versions=1,
        references_section_name="References",
        citation_lookups=no_lookups(),
        data_sources="The topics map.",
        data_sources_instructions="",
        glossary=None,
        glossary_fetch_listed_terms=False,
        client_rules=(),
        source_kinds=BOTH_SOURCE_KINDS,
        emit_research_review_result_stage=lambda outcome: (
            findings.append(outcome),
            order.append("findings"),
        ),
        emit_research_budget_exhausted=lambda outcome: (
            exhausted.append(outcome),
            order.append("budget-exhausted"),
        ),
        emit_report_review_result_stage=lambda _outcome: order.append("report-review"),
        emit_report_revision_failed=lambda _outcome: order.append("revision-failed"),
        emit_report_budget_exhausted=lambda _outcome: order.append("report-budget-exhausted"),
        emit_activity=lambda title: order.append(f"activity:{title}"),
    )

    prep = CrossTurnPrepState(
        current_query="q", plan=Plan(steps=["step one"]), plan_approved=True, research_started=True
    )
    initial = build_initial_state(prep)
    initial["research_iteration"] = max_research_iterations - 1
    final = await compiled.ainvoke(initial)
    return final, exhausted + findings, order


async def test_the_cap_announces_the_review_it_skipped(monkeypatch: MonkeyPatch) -> None:
    final, reported, order = await _run_graph_with_the_cap_reached(
        monkeypatch, max_research_iterations=10
    )

    assert final["reports"]
    [outcome] = reported
    assert (outcome.research_iteration, outcome.max_research_iterations) == (10, 10)
    # Announced while research is still the current work, so it precedes the report's own stages.
    assert order.index("budget-exhausted") < order.index("activity:Writing the report")


async def test_a_cap_of_one_announces_nothing(monkeypatch: MonkeyPatch) -> None:
    """With one permitted iteration a review could never be acted on, so review is off by
    configuration and there is nothing to report — the rule a version budget of one follows."""
    final, reported, order = await _run_graph_with_the_cap_reached(
        monkeypatch, max_research_iterations=1
    )

    assert final["reports"]
    assert reported == []
    assert "budget-exhausted" not in order


async def test_the_runner_renders_the_exhausted_budget_without_a_duration() -> None:
    choice = ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]

    runner._emit_research_budget_exhausted_stage(
        ResearchBudgetExhausted(research_iteration=10, max_research_iterations=10)
    )

    [stage] = choice.stages
    assert stage.title == (
        "[RESEARCH REVIEW RESULT] review budget is exhausted - proceeding to report ⚠️"
    )
    assert "**Iteration** 10 of at most 10" in stage.body
    assert "without a coverage review" in stage.body
    assert stage.closed
