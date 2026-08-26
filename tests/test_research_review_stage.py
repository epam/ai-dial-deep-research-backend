"""The research review's findings as a DIAL stage.

The node decides what to report and the runner decides how it looks, so these tests cover both
ends: what the outcome carries — including a verdict that has to match where the graph routes —
and the stage the runner renders from it beside the still-open activity stage. A review the
iteration cap skipped has no findings to show, and is announced by the router instead, in time to
precede the report's own stages.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pytest import LogCaptureFixture, MonkeyPatch

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.nodes import (
    RESEARCH_REVIEW_ACTIVITY,
    ResearchBudgetExhausted,
    ResearchReviewOutcome,
)
from dial_deep_research.app.research.prompts import RESEARCH_REVIEW_SYSTEM_PROMPT, ResearchReview
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.research.state import build_initial_state
from dial_deep_research.app_properties import ReportSection
from tests.dial_spies import ChoiceSpy

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
        self.last_messages: list[BaseMessage] | None = None

    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _FakeReviewModel:
        return self

    def with_retry(self, **kwargs: Any) -> _FakeReviewModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        self.calls += 1
        self.last_messages = messages
        return {"parsed": self._review, "raw": AIMessage(content=""), "parsing_error": None}


def _reviewed_state() -> dict[str, Any]:
    """The state research-review reads after one completed research iteration."""
    prep = PrepState(
        current_query="q", plan=Plan(steps=["step one"]), plan_approved=True, research_started=True
    )
    state = dict(build_initial_state(prep))
    state["research_iteration"] = 1
    return state


def _review_node(
    monkeypatch: MonkeyPatch, review: ResearchReview, max_research_iterations: int = 10
) -> tuple[Any, list[ResearchReviewOutcome], _FakeReviewModel]:
    fake = _FakeReviewModel(review)
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: fake)
    outcomes: list[ResearchReviewOutcome] = []
    node = nodes.make_research_review_node(
        today_date="2026-08-14",
        max_research_iterations=max_research_iterations,
        emit_result_stage=outcomes.append,
        emit_activity=lambda _title: None,
    )
    return node, outcomes, fake


async def test_the_outcome_carries_the_iteration_the_assessment_and_the_steps(
    monkeypatch: MonkeyPatch,
) -> None:
    node, outcomes, _fake = _review_node(
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
    node, outcomes, _fake = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS)
    )

    update = await node(_reviewed_state())

    [outcome] = outcomes
    assert outcome.will_continue is True
    assert nodes.route_after_research_review()({**_reviewed_state(), **update}) == "research-agent"


async def test_full_coverage_reports_the_report_verdict(monkeypatch: MonkeyPatch) -> None:
    node, outcomes, _fake = _review_node(
        monkeypatch, ResearchReview(assessment="Every plan item is covered.", next_steps=[])
    )

    update = await node(_reviewed_state())

    [outcome] = outcomes
    assert outcome.will_continue is False
    assert outcome.next_steps == []
    assert nodes.route_after_research_review()({**_reviewed_state(), **update}) == "report"


async def test_the_findings_never_reach_a_log_record(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """LLM response text belongs in the stage; the logs carry the step count."""
    node, _, _fake = _review_node(
        monkeypatch, ResearchReview(assessment=_ASSESSMENT, next_steps=_STEPS)
    )

    with caplog.at_level(logging.DEBUG):
        await node(_reviewed_state())

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert _ASSESSMENT not in logged
    assert all(step not in logged for step in _STEPS)
    assert "next_plan_steps=2" in logged


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
        today_date="2026-08-14",
        max_research_iterations=10,
        emit_result_stage=outcomes.append,
        emit_activity=lambda _title: None,
    )

    with pytest.raises(RuntimeError):
        await node(_reviewed_state())

    assert outcomes == []


_IMAGE_BLOCK = {"type": "image", "base64": "aGk="}


def _transcript_with_an_image() -> list[BaseMessage]:
    """One completed tool call whose result carries both text and an image."""
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_page", "args": {"page": 3}, "id": "c1"}],
            id="a1",
        ),
        ToolMessage(
            content=[{"type": "text", "text": "page 3 text"}, _IMAGE_BLOCK],
            tool_call_id="c1",
            name="get_page",
            id="t1",
        ),
    ]


async def test_an_image_finding_reaches_the_review_call(monkeypatch: MonkeyPatch) -> None:
    """research-review must see the image itself, not a marker noting one was returned."""
    node, _outcomes, fake = _review_node(
        monkeypatch, ResearchReview(assessment="ok", next_steps=[])
    )
    state = _reviewed_state()
    state["messages"] = _transcript_with_an_image()

    await node(state)

    assert fake.last_messages is not None
    [_system, human] = fake.last_messages
    assert _IMAGE_BLOCK in human.content


async def test_research_review_prompt_distinguishes_data_from_pure_format_requests() -> None:
    """A format request can still name research work (issue #45's other half): "compare X and Y
    in a table" implies data for both, but the report itself is never something research-review
    can check — there is nothing written yet to check it against."""
    normalized = " ".join(RESEARCH_REVIEW_SYSTEM_PROMPT.split())
    assert "coverage gap" in normalized
    assert "no report is written until research" in normalized


async def test_successive_review_calls_share_a_byte_prefix(monkeypatch: MonkeyPatch) -> None:
    """A later iteration's call must extend, not rewrite, an earlier one's message content — the
    property the provider's prompt cache relies on (see the prompt-caching spec)."""
    node, _outcomes, fake = _review_node(
        monkeypatch, ResearchReview(assessment="ok", next_steps=[])
    )
    state = _reviewed_state()
    state["messages"] = _transcript_with_an_image()

    await node(state)
    assert fake.last_messages is not None
    [_system, first_human] = fake.last_messages
    first_content = list(first_human.content)

    state["messages"] = [
        *_transcript_with_an_image(),
        AIMessage(
            content="",
            tool_calls=[{"name": "rag_search", "args": {"q": "y"}, "id": "c2"}],
            id="a2",
        ),
        ToolMessage(content="more hits", tool_call_id="c2", name="rag_search", id="t2"),
    ]
    await node(state)
    assert fake.last_messages is not None
    [_system, second_human] = fake.last_messages
    second_content = list(second_human.content)

    # The tail block (closing the findings and rendering the plans) sits last in both messages;
    # everything before it — the head and the growing findings — must be an unchanged prefix.
    assert second_content[: len(first_content) - 1] == first_content[:-1]


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

    The stubbed research-agent lands on the cap in one pass, so the run reaches the router in the
    state a real one would after its last permitted iteration. A version budget of one turns the
    report review off, so the run needs no review model.
    """

    async def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        return {"research_iteration": max_research_iterations}

    class _ReportModel:
        def with_retry(self, **kwargs: Any) -> _ReportModel:
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            return AIMessage(content="## Summary\n\nThe answer.")

    monkeypatch.setattr(graph_module, "build_research_agent", lambda *a, **kw: research_agent)
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

    prep = PrepState(
        current_query="q", plan=Plan(steps=["step one"]), plan_approved=True, research_started=True
    )
    final = await compiled.ainvoke(build_initial_state(prep))
    return final, exhausted + findings, order


async def test_the_cap_announces_the_review_it_skipped(monkeypatch: MonkeyPatch) -> None:
    final, reported, order = await _run_graph_with_the_cap_reached(
        monkeypatch, max_research_iterations=10
    )

    assert final["report"]
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

    assert final["report"]
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
