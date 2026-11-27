"""`SHOW_DEBUG_STAGES` decides whether the debug stages are emitted; the activity stage stays."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from dial_deep_research.app.playground.runner import PlaygroundRunner
from dial_deep_research.app.preparation.runner import PrepAgentRunner
from dial_deep_research.app.research.nodes import (
    ReportBudgetExhausted,
    ReportReviewOutcome,
    ReportRevisionFailure,
    ResearchBudgetExhausted,
    ResearchReviewOutcome,
)
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.settings import Settings, settings
from dial_deep_research.utils.dial_stages import emit_debug_stage
from tests.dial_spies import ChoiceSpy


@pytest.fixture
def debug_stages_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "show_debug_stages", False)


def _tool_call(call_id: str) -> dict[str, Any]:
    return {"name": "rag_search", "args": {"q": "gdp"}, "id": call_id}


def test_debug_stages_are_hidden_by_default() -> None:
    assert Settings.model_fields["show_debug_stages"].default is False


@pytest.mark.usefixtures("debug_stages_shown")
def test_a_debug_stage_is_emitted_when_shown() -> None:
    choice = ChoiceSpy()

    emit_debug_stage(choice=choice, title="[DEBUG] title", body="body")  # type: ignore[arg-type]

    [stage] = choice.stages
    assert (stage.title, stage.body) == ("[DEBUG] title", "body")
    assert stage.closed


@pytest.mark.usefixtures("debug_stages_hidden")
def test_a_debug_stage_is_skipped_when_hidden() -> None:
    choice = ChoiceSpy()

    emit_debug_stage(choice=choice, title="[DEBUG] title", body="body")  # type: ignore[arg-type]

    assert choice.stages == []


@pytest.mark.usefixtures("debug_stages_hidden")
def test_research_keeps_only_the_activity_stage_when_hidden() -> None:
    choice = ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "update_status", "args": {"status": "Looking for forecasts"}, "id": "c1"},
            _tool_call("c2"),
        ],
        id="a1",
    )

    runner._handle_updates({"model": {"messages": [ai]}})
    runner._handle_updates(
        {"tools": {"messages": [ToolMessage(content="hits", tool_call_id="c2")]}}
    )
    runner._emit_research_review_result_stage(
        ResearchReviewOutcome(
            research_iteration=1,
            max_research_iterations=10,
            assessment="Covered.",
            next_steps=[],
            will_continue=False,
            duration_seconds=1.0,
        )
    )
    runner._emit_research_budget_exhausted_stage(
        ResearchBudgetExhausted(research_iteration=10, max_research_iterations=10)
    )
    runner._emit_report_review_result_stage(
        ReportReviewOutcome(
            draft_number=1,
            word_count=900,
            max_words=2750,
            violations=["Fix the table."],
            blind_review_error=None,
            duration_seconds=1.0,
        )
    )
    runner._emit_report_budget_exhausted_stage(
        ReportBudgetExhausted(draft_number=3, word_count=900, max_words=2750, max_versions=3)
    )
    runner._emit_report_revision_failed_stage(
        ReportRevisionFailure(failed_draft_number=2, delivered_draft_number=1, error="TimeoutError")
    )

    assert choice.stage_titles == ["Looking for forecasts"]


@pytest.mark.usefixtures("debug_stages_hidden")
@pytest.mark.parametrize("runner_type", [PrepAgentRunner, PlaygroundRunner])
def test_a_tool_call_emits_no_stage_when_hidden(runner_type: type) -> None:
    choice = ChoiceSpy()
    runner = runner_type(choice)

    runner._handle_ai_message(AIMessage(content="", tool_calls=[_tool_call("c1")], id="a1"))
    runner._handle_tool_message(ToolMessage(content="hits", tool_call_id="c1"))

    assert choice.stages == []
