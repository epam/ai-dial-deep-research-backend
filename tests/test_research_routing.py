"""Every loop/termination decision of the research graph, decided in Python over the state.

Four edges and the helpers that decide them:

- `route_after_research_agent` (research-agent → research-review | report) gates the review on
  the iteration budget: the last permitted iteration hands straight to the report without a
  review call.
- `route_after_research_review` (research-review → research-agent | report) loops back only when
  research-review recorded a plan for a not-yet-run iteration (`len(plans) > iteration`).
- `decide_report_action` is the report loop's decision table: the measured word count and the
  review's findings in, the action and the revision instruction out. The router maps its action
  to an edge and the report-review node logs the same action, so neither can disagree with it.
- `route_after_report` (report → report-review | END) gates the review on the version budget:
  the last permitted version is delivered without a review call. And
  `route_after_report_review` (report-review → report | END).
"""

from __future__ import annotations

from typing import Any

from dial_deep_research.app.research.nodes import (
    ReportAction,
    decide_report_action,
    route_after_report,
    route_after_report_review,
    route_after_research_agent,
    route_after_research_review,
)
from dial_deep_research.app.research.state import ResearchState


def _state(plans: list[list[str]], research_iteration: int) -> ResearchState:
    return ResearchState(
        messages=[],
        original_query="q",
        plans=plans,
        research_iteration=research_iteration,
        report=None,
    )


def test_iteration_with_budget_left_is_reviewed() -> None:
    # Iteration 1 just finished (research-agent counted itself) and the budget allows a second.
    route = route_after_research_agent(max_research_iterations=10)
    assert route(_state(plans=[["a"]], research_iteration=1)) == "research-review"


def test_last_permitted_iteration_hands_straight_to_report() -> None:
    # Iteration 2 just finished with a budget of 2: a "continue" verdict could not be acted on.
    route = route_after_research_agent(max_research_iterations=2)
    assert route(_state(plans=[["a"], ["b"]], research_iteration=2)) == "report"


def test_budget_of_one_iteration_skips_the_review_entirely() -> None:
    route = route_after_research_agent(max_research_iterations=1)
    assert route(_state(plans=[["a"]], research_iteration=1)) == "report"


def test_empty_review_routes_to_report() -> None:
    # research-review returned no new plan after iteration 1: len(plans) == iteration.
    route = route_after_research_review()
    assert route(_state(plans=[["a"]], research_iteration=1)) == "report"


def test_new_plan_routes_to_research_agent() -> None:
    # research-review added a plan for iteration 2: len(plans) > iteration. The iteration cap
    # needs no check here — the review only ran because another iteration was permitted.
    route = route_after_research_review()
    assert route(_state(plans=[["a"], ["b"]], research_iteration=1)) == "research-agent"


# --- decide_report_action -----------------------------------------------------------------------


def _decide(**overrides: Any) -> tuple[ReportAction, str | None]:
    """The decision for a draft within the ceiling, with the given fields overridden."""
    inputs: dict[str, Any] = {
        "word_count": 900,
        "max_words": 2750,
        "findings": [],
    }
    return decide_report_action(**{**inputs, **overrides})


def test_clean_draft_under_the_ceiling_is_delivered() -> None:
    assert _decide() == (ReportAction.DELIVER, None)


def test_findings_drive_a_revision_carrying_them() -> None:
    action, instruction = _decide(
        findings=["The references section is missing.", "Drop 'Confidence: High'."]
    )
    assert action is ReportAction.REVISE
    assert instruction is not None
    assert "The references section is missing." in instruction
    assert "Drop 'Confidence: High'." in instruction


def test_over_the_ceiling_with_no_findings_revises_on_the_length_alone() -> None:
    action, instruction = _decide(word_count=3910)
    assert action is ReportAction.REVISE_OVER_CEILING
    assert instruction is not None
    # The instruction is app-rendered, so it states both numbers even with nothing from the model.
    assert "3910" in instruction
    assert "2750" in instruction


def test_over_the_ceiling_with_findings_merges_both_into_one_instruction() -> None:
    action, instruction = _decide(word_count=3910, findings=["The citations were renumbered."])
    assert action is ReportAction.REVISE
    assert instruction is not None
    assert "The citations were renumbered." in instruction
    assert "3910" in instruction
    assert "2750" in instruction


def test_draft_exactly_at_the_ceiling_is_within_it() -> None:
    assert _decide(word_count=2750) == (ReportAction.DELIVER, None)


# --- the report loop's two edges ----------------------------------------------------------------


def _report_state(**overrides: Any) -> ResearchState:
    state: dict[str, Any] = {
        "messages": [],
        "original_query": "q",
        "plans": [["a"]],
        "research_iteration": 1,
        "report": "the draft",
        "report_revision_instruction": None,
        "report_version": 1,
        "report_revision_failed": False,
    }
    return ResearchState(**{**state, **overrides})  # type: ignore[typeddict-item]


def test_report_routes_to_review_when_the_budget_allows() -> None:
    assert route_after_report(max_versions=3)(_report_state()) == "report-review"


def test_the_next_to_last_version_is_still_reviewed() -> None:
    # Version 2 with a budget of 3: one more version may be written, so a verdict is actionable.
    assert route_after_report(max_versions=3)(_report_state(report_version=2)) == "report-review"


def test_the_last_permitted_version_delivers_without_a_review_call() -> None:
    # Version 3 with a budget of 3: no version may follow, so a verdict could not be acted on.
    assert route_after_report(max_versions=3)(_report_state(report_version=3)) == "end"


def test_failed_revision_ends_the_loop_even_with_budget_left() -> None:
    # Re-reviewing the unchanged draft would route straight back into a call that fails again,
    # and a failed revision increments no counter, so nothing would bound the cycle.
    route = route_after_report(max_versions=3)
    assert route(_report_state(report_revision_failed=True)) == "end"


def test_budget_of_one_skips_the_review_entirely() -> None:
    assert route_after_report(max_versions=1)(_report_state()) == "end"


def test_recorded_instruction_routes_back_to_report() -> None:
    route = route_after_report_review()
    assert route(_report_state(report_revision_instruction="Shorten it.")) == "report"


def test_no_instruction_ends_the_turn() -> None:
    # `decide_report_action` already folded in the count and the budget, so an absent
    # instruction is the whole signal to deliver.
    assert route_after_report_review()(_report_state()) == "end"
