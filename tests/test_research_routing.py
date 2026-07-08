"""Routing logic for the research loop (the reviewer → researcher | report edge).

`route_after_review` is the sole loop/termination decision. It loops back to the
researcher only when the reviewer recorded a plan for a not-yet-run iteration
(`len(plans) > iteration`) and the iteration cap is not yet reached.
"""

from __future__ import annotations

from dial_deep_research.app.research.nodes import route_after_review
from dial_deep_research.app.research.state import ResearchState


def _state(plans: list[list[str]], iteration: int) -> ResearchState:
    return ResearchState(
        messages=[],
        original_query="q",
        plans=plans,
        iteration=iteration,
        report=None,
    )


def test_empty_review_routes_to_report() -> None:
    # Reviewer returned no new plan after iteration 1: len(plans) == iteration.
    route = route_after_review(max_iterations=10)
    assert route(_state(plans=[["a"]], iteration=1)) == "report"


def test_new_plan_under_cap_routes_to_researcher() -> None:
    # Reviewer added a plan for iteration 2: len(plans) > iteration, under cap.
    route = route_after_review(max_iterations=10)
    assert route(_state(plans=[["a"], ["b"]], iteration=1)) == "researcher"


def test_cap_forces_report_even_with_new_plan() -> None:
    route = route_after_review(max_iterations=2)
    # iteration reached the cap; even though a plan was recorded, force the report.
    assert route(_state(plans=[["a"], ["b"], ["c"]], iteration=2)) == "report"
