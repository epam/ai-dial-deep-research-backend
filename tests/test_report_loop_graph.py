"""The report loop as the compiled graph actually runs it.

The unit tests pin each router's decision in isolation; this file protects the wiring around
them — the node ids in `add_conditional_edges` maps, and the fact that the loop terminates. A
typo in one of those strings, or a router returning a key the map does not carry, passes every
unit test and breaks at runtime.

Research is stubbed out (one iteration, no next steps) so each test drives the report side only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.prompts import ReportReview
from dial_deep_research.app.research.state import build_initial_state
from dial_deep_research.app_properties import DEFAULT_REPORT_STRUCTURE

pytestmark = pytest.mark.asyncio


class _FakeChatModel:
    """Serves the report node (`astream`) and the report-review node (structured `ainvoke`)."""

    def __init__(self, drafts: list[str | Exception], reviews: list[ReportReview]) -> None:
        self._drafts = list(drafts)
        self._reviews = list(reviews)
        self.report_calls = 0
        self.review_calls = 0
        self.report_messages: list[list[BaseMessage]] = []

    # --- report node ---
    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.report_calls += 1
        self.report_messages.append(list(messages))
        draft = self._drafts.pop(0) if self._drafts else "a draft"
        if isinstance(draft, Exception):
            raise draft
        yield AIMessageChunk(content=draft)

    # --- report-review node: with_structured_output(...).with_retry(...).ainvoke(...) ---
    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _FakeChatModel:
        return self

    def with_retry(self, **kwargs: Any) -> _FakeChatModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        self.review_calls += 1
        review = self._reviews.pop(0) if self._reviews else ReportReview(findings=[])
        return {"parsed": review, "raw": AIMessage(content=""), "parsing_error": None}


def _stub_research(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace research with one no-op iteration that hands straight to the report node."""

    async def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def research_review(state: dict[str, Any]) -> dict[str, Any]:
        return {"iteration": state["iteration"] + 1}

    monkeypatch.setattr(graph_module, "build_research_agent", lambda *a, **kw: research_agent)
    monkeypatch.setattr(graph_module, "make_research_review_node", lambda *a, **kw: research_review)


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    drafts: list[str | Exception],
    reviews: list[ReportReview],
    max_report_revisions: int = 2,
    max_report_words: int = 2750,
) -> tuple[Any, _FakeChatModel, list[Any]]:
    _stub_research(monkeypatch)
    llm = _FakeChatModel(drafts, reviews)
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    stages: list[Any] = []
    compiled = build_research_graph(
        tools=[],
        today_date="2026-07-31",
        max_iterations=10,
        client_name="ACME",
        report_structure=DEFAULT_REPORT_STRUCTURE,
        max_report_words=max_report_words,
        max_report_revisions=max_report_revisions,
        emit_report_review_stage=stages.append,
    )
    return compiled, llm, stages


def _initial_state() -> dict[str, Any]:
    prep = PrepState(current_query="q", plan=Plan(steps=["step one"]))
    return dict(build_initial_state(prep))


async def _run(compiled: Any) -> dict[str, Any]:
    return await compiled.ainvoke(_initial_state(), config={"recursion_limit": 50})


async def test_approved_first_draft_ends_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch, drafts=["short draft"], reviews=[ReportReview(findings=[])]
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (1, 1)
    assert final["report"] == "short draft"
    assert final["revisions_used"] == 0
    assert len(stages) == 1
    assert stages[0].action == nodes.ReportAction.DELIVER


async def test_findings_drive_a_revision_then_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=["first draft", "second draft"],
        reviews=[
            ReportReview(findings=["Conclusion section missing"]),
            ReportReview(findings=[]),
        ],
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 2)
    assert final["report"] == "second draft"
    assert final["revisions_used"] == 1
    assert [stage.action for stage in stages] == [
        nodes.ReportAction.REVISE,
        nodes.ReportAction.DELIVER,
    ]
    # The revision extends the first draft's prompt rather than replacing any of it.
    first, revision = llm.report_messages
    assert [m.content for m in revision[: len(first)]] == [m.content for m in first]
    assert "Conclusion section missing" in str(revision[-1].content)


async def test_budget_caps_report_calls_at_revisions_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A review that never approves still stops: budget 2 means 3 drafts, then delivery."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=["draft one", "draft two", "draft three"],
        reviews=[ReportReview(findings=["still wrong"])] * 3,
        max_report_revisions=2,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (3, 3)
    assert final["report"] == "draft three"
    assert final["revisions_used"] == 2
    assert stages[-1].action == nodes.ReportAction.BUDGET_EXHAUSTED


async def test_zero_budget_skips_the_review_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=["the only draft"],
        reviews=[],
        max_report_revisions=0,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (1, 0)
    assert final["report"] == "the only draft"
    assert stages == []


async def test_over_ceiling_draft_is_revised_despite_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured count overrides an approving verdict — and the loop still terminates."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=["one two three four five", "two words"],
        reviews=[ReportReview(findings=[])] * 2,
        max_report_words=3,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 2)
    assert final["report"] == "two words"
    assert stages[0].action == nodes.ReportAction.REVISE_OVER_CEILING
    assert stages[0].verdict == nodes.ReportVerdict.APPROVED
    assert stages[1].action == nodes.ReportAction.DELIVER


async def test_failed_revision_delivers_the_previous_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revision whose own call fails leaves the loop instead of re-reviewing the same draft."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=["the first draft", RuntimeError("context length exceeded")],
        reviews=[ReportReview(findings=["too long"])],
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 1)
    assert final["report"] == "the first draft"
    assert final["revision_failed"] is True


async def test_failed_first_draft_fails_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing to fall back on, so the failure propagates to the DIAL error protocol."""
    compiled, _, _ = _build(monkeypatch, drafts=[RuntimeError("upstream is down")], reviews=[])
    with pytest.raises(RuntimeError, match="upstream is down"):
        await _run(compiled)
