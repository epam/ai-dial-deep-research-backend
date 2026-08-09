"""Every loop/termination decision of the research graph, decided in Python over the state.

Four edges and the helpers that decide them:

- `route_after_research_agent` (research-agent → research-review | report) gates the review on
  the iteration budget: the last permitted iteration hands straight to the report without a
  review call.
- `route_after_research_review` (research-review → research-agent | report) loops back only when
  research-review recorded a plan for a not-yet-run iteration (`len(plans) > iteration`).
- `ReportReviewOutcome.revision_instruction` decides the report loop: a non-empty violations
  list becomes the numbered revision instruction, an empty one delivers. The router maps its
  presence to an edge and the report-review node logs the same value, so neither can disagree
  with it.
- `route_after_report` (report → report-review | END) gates the review on the version budget:
  the last permitted version is delivered without a review call. And
  `route_after_report_review` (report-review → report | END).
"""

from __future__ import annotations

from typing import Any

from dial_deep_research.app.research.nodes import (
    ReportReviewOutcome,
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


# --- ReportReviewOutcome.revision_instruction ----------------------------------------------------


def _outcome(**overrides: Any) -> ReportReviewOutcome:
    """An outcome for a clean draft within the ceiling, with the given fields overridden."""
    fields: dict[str, Any] = {
        "draft_number": 1,
        "word_count": 900,
        "max_words": 2750,
        "violations": [],
        "error": None,
        "duration_seconds": 1.0,
    }
    return ReportReviewOutcome(**{**fields, **overrides})


def test_no_violations_deliver_the_draft() -> None:
    assert _outcome().revision_instruction is None


def test_violations_become_a_numbered_instruction() -> None:
    instruction = _outcome(
        violations=["The references section is missing.", "Drop 'Confidence: High'."]
    ).revision_instruction
    assert instruction == ("1. The references section is missing.\n2. Drop 'Confidence: High'.")


def test_a_failed_review_with_no_violations_delivers() -> None:
    # The error alone forces nothing: an instruction exists iff the list is non-empty.
    assert _outcome(error="RuntimeError").revision_instruction is None


def test_a_failed_review_still_revises_on_a_violation_in_the_list() -> None:
    # The node merges the app-measured length violation into the list even when the call
    # failed, so the instruction needs no fallback of its own.
    instruction = _outcome(
        error="RuntimeError", violations=["The draft is 3910 words, over the 2750-word ceiling."]
    ).revision_instruction
    assert instruction is not None
    assert "3910" in instruction


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
    # `revision_instruction` already folded in the count and the budget, so an absent
    # instruction is the whole signal to deliver.
    assert route_after_report_review()(_report_state()) == "end"
