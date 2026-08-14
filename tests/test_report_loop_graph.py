"""The report loop as the compiled graph actually runs it.

The unit tests pin each router's decision in isolation; this file protects the wiring around
them — the node ids in `add_conditional_edges` maps, and the fact that the loop terminates. A
typo in one of those strings, or a router returning a key the map does not carry, passes every
unit test and breaks at runtime.

Research is stubbed out (one iteration, no next steps) so each test drives the report side only.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from dial_deep_research.app.history import Plan, PrepState
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.prompts import ReportReview
from dial_deep_research.app.research.state import build_initial_state
from dial_deep_research.app_properties import ReportSection

pytestmark = pytest.mark.asyncio

# One section, so a draft satisfies the structure rule with a single heading: this file protects
# the graph wiring, and the rules have their own tests.
_SECTIONS = [ReportSection(name="Summary", description="The answer.", protected=True)]


def _draft(body: str) -> str:
    return f"## Summary\n\n{body}"


class _FakeChatModel:
    """Serves the report node (plain `ainvoke`) and the report-review node (structured one).

    Both nodes wrap the model in `with_stream_drop_retry`, hence `with_retry` on each object;
    `with_structured_output` hands back a separate object so the two `ainvoke` calls stay apart.
    """

    def __init__(self, drafts: list[str | Exception], reviews: list[ReportReview]) -> None:
        self._drafts = list(drafts)
        self._reviews = list(reviews)
        self.report_calls = 0
        self.review_calls = 0
        self.report_messages: list[list[BaseMessage]] = []

    # --- report node: with_retry(...).ainvoke(...) ---
    def with_retry(self, **kwargs: Any) -> _FakeChatModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.report_calls += 1
        self.report_messages.append(list(messages))
        draft = self._drafts.pop(0) if self._drafts else "a draft"
        if isinstance(draft, Exception):
            raise draft
        return AIMessage(content=draft)

    # --- report-review node: with_structured_output(...).with_retry(...).ainvoke(...) ---
    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _FakeReviewModel:
        return _FakeReviewModel(self)

    def next_review(self) -> ReportReview:
        self.review_calls += 1
        return self._reviews.pop(0) if self._reviews else ReportReview(report_violations=[])


class _FakeReviewModel:
    def __init__(self, model: _FakeChatModel) -> None:
        self._model = model

    def with_retry(self, **kwargs: Any) -> _FakeReviewModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        review = self._model.next_review()
        return {"parsed": review, "raw": AIMessage(content=""), "parsing_error": None}


def _stub_research(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace research with one no-op iteration that hands straight to the report node."""

    async def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        # The real research-agent counts its own iterations (IterationCounterMiddleware).
        return {"research_iteration": state["research_iteration"] + 1}

    async def research_review(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(graph_module, "build_research_agent", lambda *a, **kw: research_agent)
    monkeypatch.setattr(graph_module, "make_research_review_node", lambda *a, **kw: research_review)


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    drafts: list[str | Exception],
    reviews: list[ReportReview],
    max_report_versions: int = 3,
    max_report_words: int = 2750,
) -> tuple[Any, _FakeChatModel, list[Any]]:
    _stub_research(monkeypatch)
    llm = _FakeChatModel(drafts, reviews)
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    stages: list[Any] = []
    compiled = build_research_graph(
        tools=[],
        today_date="2026-07-31",
        max_research_iterations=10,
        client_name="ACME",
        report_structure=_SECTIONS,
        max_report_words=max_report_words,
        max_report_versions=max_report_versions,
        emit_research_review_result_stage=lambda _outcome: None,
        emit_report_review_result_stage=stages.append,
        emit_activity=lambda _title: None,
    )
    return compiled, llm, stages


def _initial_state() -> dict[str, Any]:
    prep = PrepState(current_query="q", plan=Plan(steps=["step one"]))
    return dict(build_initial_state(prep))


async def _run(compiled: Any) -> dict[str, Any]:
    return await compiled.ainvoke(_initial_state(), config={"recursion_limit": 50})


async def test_approved_first_draft_ends_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch, drafts=[_draft("short draft")], reviews=[ReportReview(report_violations=[])]
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (1, 1)
    assert final["report"] == _draft("short draft")
    assert final["report_version"] == 1
    assert len(stages) == 1
    assert stages[0].revision_instruction is None


async def test_violations_drive_a_revision_then_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=[_draft("first draft"), _draft("second draft")],
        reviews=[
            ReportReview(report_violations=["Conclusion section missing"]),
            ReportReview(report_violations=[]),
        ],
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 2)
    assert final["report"] == _draft("second draft")
    assert final["report_version"] == 2
    assert [stage.revision_instruction is not None for stage in stages] == [True, False]
    # The revision extends the first draft's prompt rather than replacing any of it.
    first, revision = llm.report_messages
    assert [m.content for m in revision[: len(first)]] == [m.content for m in first]
    assert "Conclusion section missing" in str(revision[-1].content)


async def test_budget_caps_report_calls_at_the_version_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A review that never approves still stops: a budget of 3 versions means 3 drafts, and the
    third is delivered without a review call — its verdict could not be acted on."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=[_draft("draft one"), _draft("draft two"), _draft("draft three")],
        reviews=[ReportReview(report_violations=["still wrong"])] * 3,
        max_report_versions=3,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (3, 2)
    assert final["report"] == _draft("draft three")
    assert final["report_version"] == 3
    assert all(stage.revision_instruction is not None for stage in stages)


async def test_budget_of_one_skips_the_review_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=[_draft("the only draft")],
        reviews=[],
        max_report_versions=1,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (1, 0)
    assert final["report"] == _draft("the only draft")
    assert stages == []


async def test_over_ceiling_draft_is_revised_despite_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured count overrides an approving verdict — and the loop still terminates."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=[_draft("one two three four five"), _draft("two words")],
        reviews=[ReportReview(report_violations=[])] * 2,
        # The heading's two words count too: the first draft measures 7, the second 4.
        max_report_words=4,
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 2)
    assert final["report"] == _draft("two words")
    # The approving review's empty list gained the app-measured length violation.
    assert len(stages[0].violations) == 1
    assert stages[0].revision_instruction is not None
    assert stages[1].revision_instruction is None


async def test_failed_revision_delivers_the_previous_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revision whose own call fails leaves the loop instead of re-reviewing the same draft."""
    compiled, llm, stages = _build(
        monkeypatch,
        drafts=[_draft("the first draft"), RuntimeError("context length exceeded")],
        reviews=[ReportReview(report_violations=["too long"])],
    )
    final = await _run(compiled)

    assert (llm.report_calls, llm.review_calls) == (2, 1)
    assert final["report"] == _draft("the first draft")
    # The failed write recorded no version, so the state still names the delivered draft.
    assert final["report_version"] == 1
    assert final["report_revision_failed"] is True


async def test_failed_first_draft_fails_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing to fall back on, so the failure propagates to the DIAL error protocol."""
    compiled, _, _ = _build(monkeypatch, drafts=[RuntimeError("upstream is down")], reviews=[])
    with pytest.raises(RuntimeError, match="upstream is down"):
        await _run(compiled)
