"""Saving a failed research run's progress and resuming it on a later turn (research-resume spec).

Covers the snapshot format and its reader, the history search, the resumed graph state, capturing
progress from a real compiled research graph, and the turn that persists or resumes a snapshot.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

import httpx
import openai
import pytest
from aidial_client import DialException, ResourceNotFoundError
from aidial_sdk.chat_completion import CustomContent, Message, Request, Role
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict
from langchain_core.tools import tool
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent
from pydantic import Field

import dial_deep_research.app.completion as completion_module
from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.error_resolution import (
    SnapshotUnreadableError,
    SnapshotVersionUnsupportedError,
)
from dial_deep_research.app.history import (
    FAILURE_STATE_KEY,
    SNAPSHOT_STATE_KEY,
    Clarification,
    CrossTurnPrepState,
    Plan,
    PreparationDialState,
    create_dial_state,
    reconstruct_prep_agent_history,
)
from dial_deep_research.app.mcp_tools import LoadedMcpTools
from dial_deep_research.app.preparation.prompts import (
    FAILED_TURN_NOTE,
    PlanReviewResponse,
    QueryReviewResponse,
)
from dial_deep_research.app.preparation.tools import PrepReviews
from dial_deep_research.app.research import graph as graph_module
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research import runner as runner_module
from dial_deep_research.app.research.data_queries import (
    DataQueryCapture,
    DataQueryRecord,
    DataQueryStore,
)
from dial_deep_research.app.research.graph import build_research_graph
from dial_deep_research.app.research.prompts import ReportReview, ResearchReview
from dial_deep_research.app.research.runner import ResearchRunner
from dial_deep_research.app.research.snapshot import (
    SNAPSHOT_VERSION,
    CapturedProgress,
    DiscardedSnapshot,
    DiscardReason,
    NotResumableReason,
    ResearchSnapshot,
    ResumableSnapshot,
    ResumePoint,
    build_completed_record,
    build_snapshot,
    decode_data_queries,
    encode_data_queries,
    find_latest_snapshot,
    read_snapshot,
)
from dial_deep_research.app.research.state import (
    ReportReviewRound,
    ResearchState,
    build_initial_state,
    build_resumed_state,
)
from dial_deep_research.app.research.tools import (
    build_finish_iteration_tool,
    build_update_status_tool,
)
from dial_deep_research.app_properties import ApplicationProperties, ReportSection
from dial_deep_research.utils import image_attachments
from dial_deep_research.utils.image_attachments import download_snapshot_images
from tests.citation_fakes import no_lookups
from tests.dial_spies import ChoiceSpy
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_PLAN_ID = "0123abcd0123abcd0123abcd0123abcd"


def _tool_call(call_id: str, name: str = "rag_search") -> dict[str, Any]:
    return {"id": call_id, "name": name, "args": {"query": "inflation"}, "type": "tool_call"}


def _transcript() -> list[Any]:
    """The seed instruction and two completed model calls with their tool results."""
    return [
        HumanMessage(content="Research the question.", id="h1"),
        AIMessage(content="", tool_calls=[_tool_call("c1")], id="a1"),
        ToolMessage(content="result one", tool_call_id="c1", id="t1"),
        AIMessage(content="", tool_calls=[_tool_call("c2")], id="a2"),
        ToolMessage(content="result two", tool_call_id="c2", id="t2"),
    ]


def _records() -> dict[str, DataQueryRecord]:
    return {
        "dq_0123abcd45": DataQueryRecord.model_validate(
            {
                "_meta": {
                    "queryId": "dq_0123abcd45",
                    "dataExplorerUrl": "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)",
                },
                "structured_content": {
                    "queryId": "dq_0123abcd45",
                    "datasetUrn": "IMF:WEO(1.0.0)",
                    "seriesCount": 2,
                    # A server element holding a list of objects that carry an `index` key.
                    "dimensions": [{"index": 1, "id": "FREQ"}, {"index": 0, "id": "REF_AREA"}],
                },
            }
        )
    }


def _review(*next_steps: str) -> ResearchReview:
    return ResearchReview(assessment="Coverage of the plan so far.", next_steps=list(next_steps))


def _review_round(draft_number: int, *rule_violations: str) -> ReportReviewRound:
    return ReportReviewRound(
        draft_number=draft_number,
        rule_violations=list(rule_violations),
        blind_review=ReportReview(report_violations=["Cut the padding."]),
        grounded_review="1. Cite the annual rate.",
    )


def _snapshot_dict(**overrides: Any) -> dict[str, Any]:
    snapshot = ResearchSnapshot(
        plan_id=_PLAN_ID,
        resumable=True,
        version=SNAPSHOT_VERSION,
        resume_at=ResumePoint.RESEARCH,
        research_query="How did inflation change in 2024?",
        approved_plan=["Find the annual inflation rate."],
        research_agent_messages=messages_to_dict(_transcript()),
        research_iteration=0,
        research_reviews=[],
        reports=[],
        report_reviews=[],
        report_revision_failed=False,
        data_queries=encode_data_queries(_records()),
    )
    return {**snapshot.model_dump(mode="json"), **overrides}


# --- The snapshot format ------------------------------------------------------------------------


def test_a_snapshot_round_trips_through_the_reader() -> None:
    raw = _snapshot_dict()

    resumed = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.snapshot.model_dump(mode="json") == raw
    assert [m.id for m in resumed.messages] == ["h1", "a1", "t1", "a2", "t2"]
    assert resumed.data_queries == _records()


def test_a_field_this_code_does_not_know_is_ignored() -> None:
    resumed = read_snapshot(
        _snapshot_dict(added_by_a_later_release=[1, 2]), current_plan_id=_PLAN_ID
    )
    assert isinstance(resumed, ResumableSnapshot)


def test_the_record_has_a_field_for_every_research_state_channel() -> None:
    """A channel added without a record field would be missing from every resumed run."""
    assert set(ResearchState.__annotations__) <= set(ResearchSnapshot.model_fields)


def test_a_record_reads_its_reviews_back_as_their_models() -> None:
    raw = _snapshot_dict(
        resume_at=ResumePoint.REPORT.value,
        research_reviews=[_review("Find the monthly rate.").model_dump(mode="json")],
        reports=["Draft one."],
        report_reviews=[_review_round(1, "The summary is too long.").model_dump(mode="json")],
    )

    resumed = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.snapshot.research_reviews == [_review("Find the monthly rate.")]
    assert resumed.snapshot.report_reviews == [_review_round(1, "The summary is too long.")]


def test_data_query_records_survive_a_clients_chunk_merge() -> None:
    """A client may rebuild a streamed answer with the SDK merge, which re-slots `index` lists."""
    state_chunk = {
        SNAPSHOT_STATE_KEY: {"data_queries": encode_data_queries(_records())},
        "plain_records": {
            k: v.model_dump(mode="json", by_alias=True) for k, v in _records().items()
        },
    }

    merged = cleanup_indices(merge({}, state_chunk))

    assert decode_data_queries(merged[SNAPSHOT_STATE_KEY]["data_queries"]) == _records()
    # The same records kept as plain JSON lose their elements' `index` key.
    plain_dimensions = merged["plain_records"]["dq_0123abcd45"]["structured_content"]["dimensions"]
    assert all("index" not in dimension for dimension in plain_dimensions)


# --- The reader: header first, then the rest ----------------------------------------------------


def test_a_snapshot_of_another_plan_is_discarded_unread() -> None:
    raw = _snapshot_dict(plan_id="another-plan", version=99, research_agent_messages="broken")

    discarded = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert discarded == DiscardedSnapshot(
        plan_id="another-plan", reason=DiscardReason.PLAN_CHANGED, resume_at=ResumePoint.RESEARCH
    )


def test_a_snapshot_marked_not_resumable_is_discarded_whatever_its_version() -> None:
    raw = _snapshot_dict(resumable=False, not_resumable_reason="repeating_failure", version=99)

    discarded = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(discarded, DiscardedSnapshot)
    assert discarded.reason is DiscardReason.NOT_RESUMABLE
    assert discarded.not_resumable_reason is NotResumableReason.REPEATING_FAILURE
    assert ("not_resumable_reason", "repeating_failure") in discarded.facts(
        current_plan_id=_PLAN_ID
    )


def test_a_discard_names_the_resume_point_only_when_it_reads_as_one() -> None:
    raw = _snapshot_dict(plan_id="another-plan", resume_at="somewhere-new")

    discarded = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(discarded, DiscardedSnapshot)
    assert discarded.resume_at is None


def test_a_record_of_another_plan_names_no_not_resumable_reason() -> None:
    raw = _snapshot_dict(
        plan_id="another-plan", resumable=False, not_resumable_reason="repeating_failure"
    )

    discarded = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(discarded, DiscardedSnapshot)
    assert discarded.reason is DiscardReason.PLAN_CHANGED
    assert discarded.not_resumable_reason is None


def test_a_discard_names_the_not_resumable_reason_only_when_it_reads_as_one() -> None:
    raw = _snapshot_dict(resumable=False, not_resumable_reason="a-reason-from-a-later-release")

    discarded = read_snapshot(raw, current_plan_id=_PLAN_ID)

    assert isinstance(discarded, DiscardedSnapshot)
    assert discarded.not_resumable_reason is None
    assert "not_resumable_reason" not in dict(discarded.facts(current_plan_id=_PLAN_ID))


@pytest.mark.parametrize("raw", ["not a snapshot", {"plan_id": 7}, {"resumable": True}])
def test_a_snapshot_whose_plan_id_cannot_be_read_is_unreadable(raw: Any) -> None:
    with pytest.raises(SnapshotUnreadableError):
        read_snapshot(raw, current_plan_id=_PLAN_ID)


def test_a_resumable_mark_that_is_not_a_boolean_is_unreadable() -> None:
    with pytest.raises(SnapshotUnreadableError):
        read_snapshot(_snapshot_dict(resumable="yes"), current_plan_id=_PLAN_ID)


def test_a_matching_snapshot_of_another_version_is_refused() -> None:
    with pytest.raises(SnapshotVersionUnsupportedError):
        read_snapshot(_snapshot_dict(version=SNAPSHOT_VERSION + 1), current_plan_id=_PLAN_ID)


@pytest.mark.parametrize(
    "overrides",
    [
        {"research_iteration": "two"},
        {"research_agent_messages": [{"type": "no-such-type", "data": {}}]},
        {"data_queries": "{not json"},
        {"research_reviews": [{"next_steps": ["no assessment"]}]},
        {"resume_at": None},
    ],
)
def test_a_matching_snapshot_that_fails_to_read_is_unreadable_with_its_cause(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(SnapshotUnreadableError) as raised:
        read_snapshot(_snapshot_dict(**overrides), current_plan_id=_PLAN_ID)
    assert raised.value.__cause__ is not None


# --- The history search -------------------------------------------------------------------------


def _assistant(state: dict[str, Any] | None, content: str = "") -> Message:
    custom_content = CustomContent(state=state) if state is not None else None
    return Message(role=Role.ASSISTANT, content=content, custom_content=custom_content)


def _user(content: str) -> Message:
    return Message(role=Role.USER, content=content)


def test_a_snapshot_two_answers_back_is_found() -> None:
    snapshot = _snapshot_dict()
    messages = [
        _user("go"),
        _assistant({"preparation": {}, SNAPSHOT_STATE_KEY: snapshot, FAILURE_STATE_KEY: True}),
        _user("what happened?"),
        _assistant({"preparation": {}}, content="It failed."),
        _user("continue"),
        _assistant({"preparation": {}, FAILURE_STATE_KEY: True}),
        _user("continue"),
    ]
    assert find_latest_snapshot(messages) == snapshot


def test_a_newer_snapshot_hides_an_older_one() -> None:
    older, newer = _snapshot_dict(), _snapshot_dict(resumable=False)
    messages = [
        _assistant({SNAPSHOT_STATE_KEY: older}),
        _user("continue"),
        _assistant({SNAPSHOT_STATE_KEY: newer}),
        _user("continue"),
    ]
    assert find_latest_snapshot(messages) == newer


def test_a_history_without_a_snapshot_has_none() -> None:
    messages = [_user("hi"), _assistant(None, content="legacy"), _assistant({"preparation": {}})]
    assert find_latest_snapshot(messages) is None


# --- The resumed graph state --------------------------------------------------------------------


def test_the_resumed_state_fills_every_channel_from_the_snapshot() -> None:
    raw = _snapshot_dict(
        resume_at=ResumePoint.REPORT_REVIEW.value,
        research_iteration=2,
        research_reviews=[_review("Find the monthly rate.").model_dump(mode="json")],
        reports=["Draft one.", "Draft two."],
        report_reviews=[_review_round(1, "Shorten the summary.").model_dump(mode="json")],
        report_revision_failed=False,
    )
    resumed = read_snapshot(raw, current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)

    state = build_resumed_state(resumed)

    assert set(state) == set(ResearchState.__annotations__)
    assert state["research_query"] == "How did inflation change in 2024?"
    assert state["approved_plan"] == ["Find the annual inflation rate."]
    assert state["research_iteration"] == 2
    assert state["research_reviews"] == [_review("Find the monthly rate.")]
    assert state["reports"] == ["Draft one.", "Draft two."]
    assert state["report_reviews"] == [_review_round(1, "Shorten the summary.")]
    assert [m.id for m in state["research_agent_messages"]] == ["h1", "a1", "t1", "a2", "t2"]


def test_the_stage_facts_of_a_research_resume_point() -> None:
    resumed = read_snapshot(_snapshot_dict(), current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.restored_model_calls_in_iteration == 2
    assert resumed.report_review_round is None


def test_the_stage_facts_of_a_report_review_resume_point() -> None:
    raw = _snapshot_dict(
        resume_at=ResumePoint.REPORT_REVIEW.value, reports=["One.", "Two.", "Three."]
    )
    resumed = read_snapshot(raw, current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.report_review_round == 3
    assert resumed.restored_model_calls_in_iteration is None


# --- Capturing progress: the stream parts the runner keeps ----------------------------------------


def _part(kind: str, ns: tuple[str, ...], data: dict[str, Any]) -> dict[str, Any]:
    return {"type": kind, "ns": ns, "data": data}


def _task_start(name: str) -> dict[str, Any]:
    return _part("tasks", (), {"id": "t", "name": name, "input": {}, "triggers": []})


def _root_values(messages: list[Any]) -> dict[str, Any]:
    return _part("values", (), {**_channels(), "research_agent_messages": messages})


def _channels() -> dict[str, Any]:
    return {
        "research_query": "q",
        "approved_plan": ["one"],
        "research_iteration": 0,
        "research_reviews": [],
        "reports": [],
        "report_reviews": [],
        "report_revision_failed": False,
    }


def test_research_agents_own_messages_are_kept_from_its_namespace_only() -> None:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    seed = [HumanMessage(content="Research the question.", id="h1")]
    agent_messages = _transcript()

    for part in [
        _root_values(seed),
        _task_start("research-agent"),
        _part("values", ("research-agent:1",), {"messages": agent_messages}),
        _part("values", ("research-review:2",), {"messages": seed}),
        _part("values", ("research-agent:1", "tools:3"), {"messages": seed}),
    ]:
        runner._handle_part(part)  # type: ignore[arg-type]

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.RESEARCH
    assert [m.id for m in progress.messages] == ["h1", "a1", "t1", "a2", "t2"]


def test_a_new_iteration_clears_the_previous_iterations_messages() -> None:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    root_transcript = [*_transcript(), HumanMessage(content="Instruction two.", id="h2")]

    for part in [
        _task_start("research-agent"),
        _part("values", ("research-agent:1",), {"messages": _transcript()}),
        _task_start("research-review"),
        _root_values(root_transcript),
        _task_start("research-agent"),
    ]:
        runner._handle_part(part)  # type: ignore[arg-type]

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.messages[-1].id == "h2"


def test_a_finished_task_does_not_change_the_running_node() -> None:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    finished = {"id": "t", "name": "research-agent", "error": None, "result": [], "interrupts": []}

    for part in [_root_values([]), _task_start("report"), _part("tasks", (), finished)]:
        runner._handle_part(part)  # type: ignore[arg-type]

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.REPORT


def test_no_progress_is_captured_before_the_graph_streams_state() -> None:
    assert ResearchRunner(ChoiceSpy()).captured_progress() is None  # type: ignore[arg-type]


# --- Capturing progress from a real compiled research graph ---------------------------------------


class _Abort(BaseException):
    """Ends a run during a tools round: tool `Exception`s become error results instead."""


@tool
def rag_search(query: str) -> str:
    """Search the documents."""
    return f"results for {query}"


@tool
def abort_search(query: str) -> str:
    """A search whose run is cut off."""
    raise _Abort()


class _ScriptedToolModel(GenericFakeChatModel):
    """research-agent's model: answers each call with the next scripted message, or raises."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def _script(*steps: AIMessage | Exception) -> Iterator[AIMessage]:
    for step in steps:
        if isinstance(step, Exception):
            raise step
        yield step


def _calls(*calls: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=list(calls))


def _compile_research_graph(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Any:
    arguments: dict[str, Any] = {
        "tools": [
            rag_search,
            abort_search,
            build_finish_iteration_tool(),
            build_update_status_tool(),
        ],
        "today_date": "2026-10-23",
        "max_research_iterations": 10,
        "client_name": "ACME",
        "report_structure": [
            ReportSection(name="Summary", description="The answer.", protected=True)
        ],
        "max_report_words": 2750,
        "max_report_versions": 3,
        "references_section_name": "References",
        "citation_lookups": no_lookups(),
        "data_sources": "The topics map.",
        "data_sources_instructions": "",
        "glossary": None,
        "glossary_fetch_listed_terms": False,
        "client_rules": (),
        "source_kinds": BOTH_SOURCE_KINDS,
        "emit_research_review_result_stage": lambda _outcome: None,
        "emit_research_budget_exhausted": lambda _outcome: None,
        "emit_report_review_result_stage": lambda _outcome: None,
        "emit_report_revision_failed": lambda _outcome: None,
        "emit_report_budget_exhausted": lambda _outcome: None,
        "emit_activity": lambda _title: None,
    }
    return build_research_graph(**{**arguments, **overrides})


def _use_agent_script(monkeypatch: pytest.MonkeyPatch, *steps: AIMessage | Exception) -> None:
    model = _ScriptedToolModel(messages=_script(*steps))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)


def _stub_node(monkeypatch: pytest.MonkeyPatch, factory: str, node: Any) -> None:
    monkeypatch.setattr(graph_module, factory, lambda *a, **kw: node)


def _prep_state() -> CrossTurnPrepState:
    return CrossTurnPrepState(
        current_query="How did inflation change in 2024?",
        plan=Plan(steps=["Find the annual inflation rate."]),
        plan_id=_PLAN_ID,
        plan_approved=True,
        research_started=True,
    )


async def _run_until_it_fails(
    graph: Any, *, raises: type[BaseException] = RuntimeError
) -> ResearchRunner:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    with pytest.raises(raises):
        await runner._stream_graph(
            graph,
            build_initial_state(_prep_state()),
            config={"recursion_limit": 100},
            entry=ResumePoint.RESEARCH,
        )
    return runner


async def test_a_failure_at_a_model_call_keeps_the_completed_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_agent_script(
        monkeypatch,
        _calls(_tool_call("c1")),
        _calls(_tool_call("c2")),
        RuntimeError("quota exhausted"),
    )

    runner = await _run_until_it_fails(_compile_research_graph(monkeypatch))

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.RESEARCH
    assert [m.type for m in progress.messages] == ["human", "ai", "tool", "ai", "tool"]
    assert progress.messages[-1].tool_call_id == "c2"  # type: ignore[attr-defined]
    assert progress.channels["research_iteration"] == 0


async def test_a_failure_during_a_tools_round_leaves_out_the_call_that_requested_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_agent_script(
        monkeypatch,
        _calls(_tool_call("c1")),
        _calls(_tool_call("c2", name="abort_search")),
    )

    runner = await _run_until_it_fails(_compile_research_graph(monkeypatch), raises=_Abort)

    progress = runner.captured_progress()
    assert progress is not None
    assert [m.type for m in progress.messages] == ["human", "ai", "tool"]
    assert progress.messages[-1].tool_call_id == "c1"  # type: ignore[attr-defined]


async def test_research_review_failing_after_iteration_two(monkeypatch: pytest.MonkeyPatch) -> None:
    async def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        return {"research_iteration": state["research_iteration"] + 1}

    reviews = 0

    async def research_review(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal reviews
        reviews += 1
        if reviews == 2:
            raise RuntimeError("upstream 502")
        return {
            "research_reviews": [*state["research_reviews"], _review("Next step.")],
            "research_agent_messages": [HumanMessage(content="Instruction two.")],
        }

    _stub_node(monkeypatch, "make_research_agent_node", research_agent)
    _stub_node(monkeypatch, "make_research_review_node", research_review)

    runner = await _run_until_it_fails(_compile_research_graph(monkeypatch))

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.RESEARCH_REVIEW
    assert progress.channels["research_iteration"] == 2


async def test_the_report_node_failing_on_the_first_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    async def research_agent(state: dict[str, Any]) -> dict[str, Any]:
        return {"research_iteration": state["research_iteration"] + 1}

    async def research_review(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def report(state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("quota exhausted")

    _stub_node(monkeypatch, "make_research_agent_node", research_agent)
    _stub_node(monkeypatch, "make_research_review_node", research_review)
    _stub_node(monkeypatch, "make_report_node", report)

    runner = await _run_until_it_fails(_compile_research_graph(monkeypatch))

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.REPORT
    assert progress.channels["reports"] == []


async def test_a_new_iteration_failing_at_once_uses_the_graphs_own_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_agent_script(
        monkeypatch,
        _calls(_tool_call("c1")),
        _calls(_tool_call("f1", name="finish_iteration")),
        RuntimeError("quota exhausted"),
    )

    async def research_review(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "research_reviews": [*state["research_reviews"], _review("Next step.")],
            "research_agent_messages": [HumanMessage(content="Instruction two.", id="h2")],
        }

    _stub_node(monkeypatch, "make_research_review_node", research_review)

    runner = await _run_until_it_fails(_compile_research_graph(monkeypatch))

    progress = runner.captured_progress()
    assert progress is not None
    assert progress.resume_at is ResumePoint.RESEARCH
    assert progress.messages[-1].id == "h2"
    assert progress.channels["research_iteration"] == 1


# --- From captured progress to the snapshot to persist ----------------------------------------------

_PNG_B64 = "iVBORw0KGgo="


class _UploadingDial:
    """Just enough of `AsyncDial` for an upload: a bucket and a files API answering with a URL."""

    def __init__(self, *, bucket_fails: bool = False) -> None:
        self.bucket = self._Bucket(bucket_fails)
        self.files = self._Files()

    class _Bucket:
        def __init__(self, fails: bool) -> None:
            self._fails = fails

        async def get_raw(self) -> Any:
            if self._fails:
                raise RuntimeError("bucket lookup failed")
            return type("BucketResp", (), {"appdata": "ub/appdata", "bucket": "ub"})()

    class _Files:
        async def upload(self, *, url: str, file: Any) -> Any:
            return type("Uploaded", (), {"url": url})()


def _progress_with_an_image() -> CapturedProgress:
    tool_message = ToolMessage(
        content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
        tool_call_id="c1",
        id="t1",
    )
    return CapturedProgress(
        resume_at=ResumePoint.RESEARCH,
        messages=[
            HumanMessage(content="Research the question.", id="h1"),
            AIMessage(content="", tool_calls=[_tool_call("c1")], id="a1"),
            tool_message,
        ],
        channels={**_channels(), "research_agent_messages": []},
        data_queries=_records(),
    )


def test_the_captured_progress_carries_the_turns_data_query_records() -> None:
    runner = ResearchRunner(ChoiceSpy())  # type: ignore[arg-type]
    runner._data_queries = DataQueryStore(records=_records())
    runner._handle_part(_root_values([]))  # type: ignore[arg-type]

    progress = runner.captured_progress()

    assert progress is not None
    assert progress.data_queries == _records()


_PNG_SHA256 = hashlib.sha256(base64.b64decode(_PNG_B64)).hexdigest()


async def test_a_built_snapshot_holds_image_urls_and_reads_back() -> None:
    snapshot = await build_snapshot(
        _progress_with_an_image(),
        plan_id=_PLAN_ID,
        repeating_failure=False,
        dial=_UploadingDial(),  # type: ignore[arg-type]
    )

    assert snapshot.resumable is True
    assert snapshot.not_resumable_reason is None
    [block] = snapshot.research_agent_messages[-1]["data"]["content"]
    assert "base64" not in block
    assert block["url"] == "files/ub/appdata/dial-deep-research/c1-0.png"
    resumed = read_snapshot(snapshot.model_dump(mode="json"), current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.data_queries == _records()
    assert [m.id for m in resumed.messages] == ["h1", "a1", "t1"]


async def test_a_snapshot_whose_bucket_cannot_be_resolved_is_not_resumable() -> None:
    snapshot = await build_snapshot(
        _progress_with_an_image(),
        plan_id=_PLAN_ID,
        repeating_failure=False,
        dial=_UploadingDial(bucket_fails=True),  # type: ignore[arg-type]
    )

    assert snapshot.resumable is False
    assert snapshot.not_resumable_reason is NotResumableReason.IMAGE_UPLOAD_FAILED
    [block] = snapshot.research_agent_messages[-1]["data"]["content"]
    assert block == {
        "type": "text",
        "text": f"[image not stored: upload failed, image/png, sha256={_PNG_SHA256}]",
    }


async def test_a_repeating_failure_that_also_loses_an_image_names_the_repeating_failure() -> None:
    snapshot = await build_snapshot(
        _progress_with_an_image(),
        plan_id=_PLAN_ID,
        repeating_failure=True,
        dial=_UploadingDial(bucket_fails=True),  # type: ignore[arg-type]
    )

    assert snapshot.resumable is False
    assert snapshot.not_resumable_reason is NotResumableReason.REPEATING_FAILURE


def test_a_completed_record_holds_placeholders_and_names_no_resume_point() -> None:
    progress = _progress_with_an_image().model_copy(update={"resume_at": None})

    record = build_completed_record(progress, plan_id=_PLAN_ID)

    assert (record.resumable, record.not_resumable_reason, record.resume_at) == (
        False,
        NotResumableReason.COMPLETED,
        None,
    )
    [block] = record.research_agent_messages[-1]["data"]["content"]
    assert block == {
        "type": "text",
        "text": f"[image not stored: successful run, image/png, sha256={_PNG_SHA256}]",
    }


async def test_every_research_state_channel_survives_the_save_and_the_resume() -> None:
    """A channel the record builder forgets to copy would resume with the record field's default.

    Every value differs from an empty or zero default, so a forgotten copy fails the comparison.
    """
    state = ResearchState(
        research_query="How did inflation change in 2024?",
        approved_plan=["Find the annual inflation rate."],
        research_agent_messages=_transcript(),
        research_iteration=2,
        research_reviews=[_review("Find the monthly rate.")],
        reports=["Draft one.", "Draft two."],
        report_reviews=[_review_round(1, "Shorten the summary.")],
        report_revision_failed=True,
    )
    assert all(state.values()), "every channel needs a value that no default could equal"
    progress = CapturedProgress(
        resume_at=ResumePoint.REPORT_REVIEW,
        messages=list(state["research_agent_messages"]),
        channels=dict(state),
        data_queries=_records(),
    )

    snapshot = await build_snapshot(
        progress,
        plan_id=_PLAN_ID,
        repeating_failure=False,
        dial=_UploadingDial(),  # type: ignore[arg-type]
    )
    stored = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    resumed = read_snapshot(stored, current_plan_id=_PLAN_ID)

    assert isinstance(resumed, ResumableSnapshot)
    assert build_resumed_state(resumed) == state


_PNG_BYTES = b"\x89PNG\r\n\x1a\n"
_DRAFT = "## Summary\n\nInflation rose."


class _RecordingToolModel(_ScriptedToolModel):
    """research-agent's model, keeping the messages of every call it answers."""

    received: list[list[Any]] = Field(default_factory=list)

    def _generate(self, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
        self.received.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


class _DownloadingDial(_UploadingDial):
    """Adds the files download a resumed run makes for the snapshot's images."""

    def __init__(self) -> None:
        super().__init__()
        self.files = self._DownloadingFiles()

    class _DownloadingFiles(_UploadingDial._Files):
        async def download(self, url: str) -> Any:
            class _Downloaded:
                async def aget_content(self) -> bytes:
                    return _PNG_BYTES

            return _Downloaded()


def _resume_properties(**overrides: Any) -> ApplicationProperties:
    return ApplicationProperties.model_validate(
        {
            "prompts": {"client_name": "ACME", "agent_name": "ACME Deep Research"},
            "mcp_servers": [
                {
                    "server_name": "rag",
                    "server_type": "generic_rag",
                    "description": "## report\n\nA report.",
                    "deployment_id": "generic-rag-mcp",
                    "file_sharing_tool": "get_citation_url",
                    "document_metadata_resource": "documents://metadata/{document_ids}",
                    "document_title_key": "publication_title",
                    "references_table": {
                        "title": "Documents",
                        "columns": [{"heading": "Title", "key": "publication_title"}],
                    },
                }
            ],
            "max_report_versions": 1,
            **overrides,
        }
    )


def _load_tools(
    monkeypatch: pytest.MonkeyPatch, *, agent_tools: list[Any], store: DataQueryStore
) -> None:
    async def load(**_kwargs: Any) -> LoadedMcpTools:
        return LoadedMcpTools(
            agent_tools=agent_tools,
            file_sharing_tool=None,
            list_datasets_tool=None,
            client=None,
            data_queries=store,
        )

    monkeypatch.setattr(runner_module, "load_mcp_tools", load)


def _counting_rag_tool(calls: list[str]) -> Any:
    @tool("rag_search")
    def counting_rag_search(query: str) -> str:
        """Search the documents."""
        calls.append(query)
        return f"results for {query}"

    return counting_rag_search


def _resumed(**overrides: Any) -> ResumableSnapshot:
    resumed = read_snapshot(_snapshot_dict(**overrides), current_plan_id=_PLAN_ID)
    if not isinstance(resumed, ResumableSnapshot):
        raise AssertionError(f"the snapshot was not resumable: {resumed}")
    return resumed


def _record_order(order: list[str], name: str, update: dict[str, Any] | None = None) -> Any:
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        order.append(name)
        return update(state) if callable(update) else (update or {})

    return node


def _report_writer(order: list[str], received: list[dict[str, Any]] | None = None) -> Any:
    async def report(state: dict[str, Any]) -> dict[str, Any]:
        order.append("report")
        if received is not None:
            received.append(dict(state))
        return {"reports": [*state["reports"], _DRAFT]}

    return report


async def _resume_run(
    monkeypatch: pytest.MonkeyPatch,
    resumed: ResumableSnapshot,
    *,
    agent_tools: list[Any] | None = None,
    store: DataQueryStore | None = None,
    **property_overrides: Any,
) -> tuple[ResearchRunner, ChoiceSpy]:
    _load_tools(monkeypatch, agent_tools=agent_tools or [], store=store or DataQueryStore())
    choice = ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]
    await runner.run(
        _prep_state(),
        properties=_resume_properties(**property_overrides),
        data_sources=DataSources(text="The topics map."),
        resumed=resumed,
    )
    return runner, choice


async def test_a_resumed_iteration_repeats_only_the_failed_model_call(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The failed run: two completed model calls, then the third model call fails.
    _use_agent_script(
        monkeypatch, _calls(_tool_call("c1")), _calls(_tool_call("c2")), RuntimeError("quota")
    )
    failed = await _run_until_it_fails(_compile_research_graph(monkeypatch))
    progress = failed.captured_progress()
    assert progress is not None
    snapshot = await build_snapshot(
        progress,
        plan_id=_PLAN_ID,
        repeating_failure=False,
        dial=_UploadingDial(),  # type: ignore[arg-type]
    )
    resumed = read_snapshot(snapshot.model_dump(mode="json"), current_plan_id=_PLAN_ID)
    assert isinstance(resumed, ResumableSnapshot)

    # The resumed run: the repeated model call finishes the iteration.
    model = _RecordingToolModel(messages=_script(_calls(_tool_call("f1", name="finish_iteration"))))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
    order: list[str] = []
    _stub_node(monkeypatch, "make_research_review_node", _record_order(order, "research-review"))
    _stub_node(monkeypatch, "make_report_node", _report_writer(order))
    rag_calls: list[str] = []
    iterations: list[int] = []
    _load_tools(monkeypatch, agent_tools=[_counting_rag_tool(rag_calls)], store=DataQueryStore())
    choice = ChoiceSpy()
    runner = ResearchRunner(choice)  # type: ignore[arg-type]
    handle_part = runner._handle_part

    def spy(part: Any) -> None:
        if part["type"] == "values" and not part["ns"]:
            iterations.append(part["data"]["research_iteration"])
        handle_part(part)

    runner._handle_part = spy  # type: ignore[method-assign]
    caplog.set_level(logging.INFO)

    await runner.run(
        _prep_state(),
        properties=_resume_properties(),
        data_sources=DataSources(text="The topics map."),
        resumed=resumed,
    )

    [only_call] = model.received
    assert [m.type for m in only_call] == ["system", "human", "ai", "tool", "ai", "tool"]
    assert rag_calls == []
    assert (iterations[0], iterations[-1]) == (0, 1)
    assert order == ["research-review", "report"]
    assert not any("rag_search" in title for title in choice.stage_titles)
    assert not any("Tool call completed" in r.getMessage() for r in caplog.records)


async def test_resuming_at_research_review_runs_it_first(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    _stub_node(monkeypatch, "make_research_agent_node", _record_order(order, "research-agent"))
    _stub_node(monkeypatch, "make_research_review_node", _record_order(order, "research-review"))
    _stub_node(monkeypatch, "make_report_node", _report_writer(order))
    resumed = _resumed(
        resume_at=ResumePoint.RESEARCH_REVIEW.value,
        research_iteration=2,
        research_reviews=[_review("b").model_dump(mode="json")],
    )

    await _resume_run(monkeypatch, resumed)

    assert order == ["research-review", "report"]


async def test_resuming_at_the_report_writes_draft_one_from_the_saved_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    received: list[dict[str, Any]] = []
    _stub_node(monkeypatch, "make_research_agent_node", _record_order(order, "research-agent"))
    _stub_node(monkeypatch, "make_research_review_node", _record_order(order, "research-review"))
    _stub_node(monkeypatch, "make_report_node", _report_writer(order, received))

    runner, choice = await _resume_run(monkeypatch, _resumed(resume_at=ResumePoint.REPORT.value))

    assert order == ["report"]
    [state] = received
    assert state["reports"] == []
    assert [m.id for m in state["research_agent_messages"]] == ["h1", "a1", "t1", "a2", "t2"]
    assert "Inflation rose." in choice.content


async def test_resuming_at_report_review_reviews_the_saved_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    reviewed: list[tuple[str, int]] = []

    def review(state: dict[str, Any]) -> dict[str, Any]:
        reviewed.append((state["reports"][-1], len(state["reports"])))
        approval = ReportReviewRound(
            draft_number=2, rule_violations=[], blind_review=None, grounded_review=None
        )
        return {"report_reviews": [*state["report_reviews"], approval]}

    _stub_node(monkeypatch, "make_report_node", _report_writer(order))
    _stub_node(
        monkeypatch, "make_report_review_node", _record_order(order, "report-review", review)
    )
    resumed = _resumed(
        resume_at=ResumePoint.REPORT_REVIEW.value,
        reports=["Draft one.", _DRAFT],
        report_reviews=[_review_round(1, "Shorten the summary.").model_dump(mode="json")],
    )

    await _resume_run(monkeypatch, resumed, max_report_versions=3)

    assert order == ["report-review"]
    assert reviewed == [(_DRAFT, 2)]


async def test_the_iteration_cap_counts_the_iterations_before_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    def one_iteration(state: dict[str, Any]) -> dict[str, Any]:
        return {"research_iteration": state["research_iteration"] + 1}

    _stub_node(
        monkeypatch,
        "make_research_agent_node",
        _record_order(order, "research-agent", one_iteration),
    )
    _stub_node(monkeypatch, "make_research_review_node", _record_order(order, "research-review"))
    _stub_node(monkeypatch, "make_report_node", _report_writer(order))

    await _resume_run(monkeypatch, _resumed(research_iteration=2), max_research_iterations=3)

    # The resumed iteration is the third and last permitted one, so it goes to the report unreviewed.
    assert order == ["research-agent", "report"]


async def test_the_version_budget_counts_the_drafts_before_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    _stub_node(monkeypatch, "make_report_node", _report_writer(order))
    _stub_node(monkeypatch, "make_report_review_node", _record_order(order, "report-review"))
    resumed = _resumed(
        resume_at=ResumePoint.REPORT.value,
        reports=["Draft one.", _DRAFT],
        report_reviews=[
            _review_round(1, "Shorten the summary.").model_dump(mode="json"),
            _review_round(2, "Shorten the summary.").model_dump(mode="json"),
        ],
    )

    await _resume_run(monkeypatch, resumed, max_report_versions=3)

    # Draft 3 is the last the budget permits, so it is delivered without a review.
    assert order == ["report"]


async def test_the_resumed_agent_call_receives_the_snapshots_transcript_with_its_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript = _transcript()
    transcript[2] = ToolMessage(
        content=[
            {
                "type": "image",
                "url": "files/ub/dial-deep-research/c1-0.png",
                "mime_type": "image/png",
            }
        ],
        tool_call_id="c1",
        id="t1",
    )
    model = _RecordingToolModel(messages=_script(_calls(_tool_call("f1", name="finish_iteration"))))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
    order: list[str] = []
    _stub_node(monkeypatch, "make_research_review_node", _record_order(order, "research-review"))
    _stub_node(monkeypatch, "make_report_node", _report_writer(order))

    resumed = _resumed(research_agent_messages=messages_to_dict(transcript))
    # The coordinator downloads the images before the run starts.
    assert await download_snapshot_images(resumed.messages, _DownloadingDial()) == 0  # type: ignore[arg-type]
    await _resume_run(monkeypatch, resumed)

    [first_call, *_] = model.received
    assert [m.type for m in first_call] == ["system", "human", "ai", "tool", "ai", "tool"]
    [image] = first_call[3].content
    assert image["base64"] == base64.b64encode(_PNG_BYTES).decode()
    assert "url" not in image
    assert not any(m.type == "system" and m.content == FAILED_TURN_NOTE for m in first_call)


async def test_a_query_captured_before_the_failure_resolves_after_the_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    async def report(state: dict[str, Any]) -> dict[str, Any]:
        order.append("report")
        return {"reports": [f"{_DRAFT} [data_query dq_0123abcd45]"]}

    _stub_node(monkeypatch, "make_report_node", report)
    store = DataQueryStore()

    _, choice = await _resume_run(
        monkeypatch, _resumed(resume_at=ResumePoint.REPORT.value), store=store
    )

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    urls = [a["body"]["source"]["attachment"]["url"] for a in annotations]
    assert "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)" in urls
    assert "dq_0123abcd45" in store.records


async def test_a_record_captured_after_the_resume_replaces_the_restored_one() -> None:
    store = DataQueryStore(records=_records())
    capture = DataQueryCapture(
        server_name="datasets", meta_key="acme.example.org/client", store=store
    )
    newer_url = "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE"
    result = CallToolResult.model_validate(
        {
            "content": [TextContent(type="text", text="{}")],
            "_meta": {
                "acme.example.org/client": {
                    "queries": [{"queryId": "dq_0123abcd45", "dataExplorerUrl": newer_url}]
                }
            },
        }
    )

    async def handler(_request: MCPToolCallRequest) -> CallToolResult:
        return result

    await capture(MCPToolCallRequest(name="query_data", args={}, server_name="datasets"), handler)

    assert store.records["dq_0123abcd45"].data_explorer_url == newer_url


# --- The turn: a harness over the HTTP app ---------------------------------------------------------

_COMPLETIONS_URL = "/openai/deployments/deep-research/chat/completions"

_TURN_PROPERTIES: dict[str, Any] = {
    "prompts": {"client_name": "ACME", "agent_name": "ACME Deep Research"},
    "mcp_servers": [
        {
            "server_name": "rag",
            "server_type": "generic_rag",
            "description": "## report\n\nA report.",
            "deployment_id": "generic-rag-mcp",
            "file_sharing_tool": "get_citation_url",
            "document_metadata_resource": "documents://metadata/{document_ids}",
            "document_title_key": "publication_title",
            "references_table": {
                "title": "Documents",
                "columns": [{"heading": "Title", "key": "publication_title"}],
            },
        }
    ],
}


class _TurnResult:
    """A streamed answer, read back: its content, its state, its stages and its error."""

    def __init__(self, response: Any) -> None:
        self.chunks = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        self.states = [state for state in map(self._state, self.chunks) if state is not None]
        self.errors = [chunk["error"] for chunk in self.chunks if "error" in chunk]

    @staticmethod
    def _state(chunk: dict[str, Any]) -> Any:
        for choice in chunk.get("choices") or []:
            custom_content = (choice.get("delta") or {}).get("custom_content") or {}
            if "state" in custom_content:
                return custom_content["state"]
        return None

    @property
    def state(self) -> dict[str, Any]:
        [state] = self.states
        return state

    def position_of_state(self) -> int:
        return next(i for i, chunk in enumerate(self.chunks) if self._state(chunk) is not None)

    def position_of_error(self) -> int:
        return next(i for i, chunk in enumerate(self.chunks) if "error" in chunk)

    def stages(self) -> list[tuple[str, str]]:
        """Each stage's name and body, in the order the stages opened."""
        names: dict[int, str] = {}
        bodies: dict[int, str] = {}
        for chunk in self.chunks:
            for choice in chunk.get("choices") or []:
                custom_content = (choice.get("delta") or {}).get("custom_content") or {}
                for stage in custom_content.get("stages") or []:
                    position = stage["index"]
                    names[position] = names.get(position, "") + stage.get("name", "")
                    bodies[position] = bodies.get(position, "") + stage.get("content", "")
        return [(names[i], bodies[i]) for i in sorted(names)]


class _TurnDial:
    """The turn's `AsyncDial`: uploads succeed unless the bucket lookup is set to fail."""

    def __init__(self, *, bucket_fails: bool = False) -> None:
        self.bucket = _UploadingDial._Bucket(bucket_fails)
        self.files = _DownloadingDial._DownloadingFiles()


def _post_turn(client: TestClient, messages: list[dict[str, Any]]) -> _TurnResult:
    response = client.post(
        _COMPLETIONS_URL,
        json={"messages": messages, "stream": True},
        headers={
            "Api-Key": "test-key",
            "X-DIAL-APPLICATION-PROPERTIES": json.dumps(_TURN_PROPERTIES),
        },
    )
    return _TurnResult(response)


@pytest.fixture
def turn_dial(monkeypatch: pytest.MonkeyPatch) -> _TurnDial:
    """The fake DIAL client every turn gets, and a data-sources fetch with nothing to fetch."""
    dial = _TurnDial()
    monkeypatch.setattr(completion_module, "AsyncDial", lambda **_kwargs: dial)

    async def fetch(properties: ApplicationProperties, **_kwargs: Any) -> DataSources:
        return DataSources(text="The topics map.")

    monkeypatch.setattr(completion_module, "fetch_data_sources", fetch)
    return dial


def _prep_runner(behave: Any) -> type:
    """A preparation runner whose `run` calls `behave(prep_state)` and returns its messages."""

    class _Prep:
        appended_content = False

        def __init__(self, choice: Any) -> None:
            self._choice = choice
            self.reviews = PrepReviews()

        async def run(self, *, prep_state: CrossTurnPrepState, **_kwargs: Any) -> list[Any]:
            return behave(prep_state)

    return _Prep


def _hand_off(prep_state: CrossTurnPrepState) -> list[Any]:
    """The preparation agent approves the recorded plan and starts research."""
    prep_state.plan_approved = True
    if prep_state.plan_id is None:
        prep_state.plan_id = _PLAN_ID
    prep_state.research_started = True
    return [
        AIMessage(content="", tool_calls=[_tool_call("s1", name="start_research")], id="p1"),
        ToolMessage(content="Research has started.", tool_call_id="s1", id="p2"),
    ]


class _ResearchSpy:
    """Stands in for `ResearchRunner`, recording each run and failing it when told to."""

    runs: list[dict[str, Any]] = []
    fail_with: BaseException | None = None
    progress: CapturedProgress | None = None
    messages: list[Any] = []

    def __init__(self, choice: Any, **_kwargs: Any) -> None:
        self._choice = choice

    async def run(self, prep_state: CrossTurnPrepState, **kwargs: Any) -> list[Any]:
        type(self).runs.append({"prep_state": prep_state.model_copy(), **kwargs})
        # The real runner's first activity stage, so the order of stages can be checked.
        with self._choice.create_stage("Starting research"):
            pass
        if type(self).fail_with is not None:
            raise type(self).fail_with
        self._choice.append_content(_DRAFT)
        return list(type(self).messages)

    def captured_progress(self) -> CapturedProgress | None:
        return type(self).progress

    def completed_progress(self) -> CapturedProgress:
        return CapturedProgress(
            resume_at=None,
            messages=list(type(self).messages),
            channels={**_channels(), "reports": [_DRAFT]},
            data_queries={},
        )


@pytest.fixture
def research(monkeypatch: pytest.MonkeyPatch) -> type[_ResearchSpy]:
    spy = type("_Research", (_ResearchSpy,), {"runs": [], "fail_with": None, "progress": None})
    spy.messages = []
    monkeypatch.setattr(completion_module, "ResearchRunner", spy)
    return spy


def _recorded_plan_state(**overrides: Any) -> dict[str, Any]:
    prep = CrossTurnPrepState(
        current_query="How did inflation change in 2024?",
        clarification=Clarification(questions=[]),
        plan=Plan(steps=["Find the annual inflation rate."]),
        plan_id=_PLAN_ID,
        **overrides,
    )
    return create_dial_state(PreparationDialState(prep_state=prep))


def _conversation(*turns: tuple[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    """User messages alternating with assistant answers carrying the given states."""
    messages: list[dict[str, Any]] = []
    for user_text, assistant_state in turns:
        messages.append({"role": "user", "content": user_text})
        if assistant_state is not None:
            messages.append(
                {"role": "assistant", "content": "", "custom_content": {"state": assistant_state}}
            )
    return messages


# --- The turn: nothing after the report fails it ----------------------------------------------------


def _image_tool_message() -> ToolMessage:
    return ToolMessage(
        content=[{"type": "image", "base64": _PNG_B64, "mime_type": "image/png"}],
        tool_call_id="c1",
        id="t1",
    )


class _NoFilesDial:
    """A DIAL client that fails the test on any bucket or files call."""

    class _Refuse:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"unexpected files call: {name}")

    bucket = _Refuse()
    files = _Refuse()


def test_a_completed_research_turn_saves_its_record_with_placeholders_and_no_files_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(completion_module, "AsyncDial", lambda **_kwargs: _NoFilesDial())
    research.messages = [HumanMessage(content="Research the question.", id="h1")]
    research.messages.append(_image_tool_message())
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    assert result.errors == []
    state = result.state
    assert FAILURE_STATE_KEY not in state
    assert state["preparation"]["research_started"] is True
    assert [m["data"]["id"] for m in state["preparation"]["agent_messages"]] == ["p1", "p2"]
    record = state[SNAPSHOT_STATE_KEY]
    assert (record["resumable"], record["not_resumable_reason"], record["resume_at"]) == (
        False,
        "completed",
        None,
    )
    assert record["reports"] == [_DRAFT]
    assert not any(m["type"] == "ai" for m in record["research_agent_messages"])
    tool_entry = record["research_agent_messages"][-1]
    assert tool_entry["data"]["content"] == [
        {
            "type": "text",
            "text": f"[image not stored: successful run, image/png, sha256={_PNG_SHA256}]",
        }
    ]
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert any("outcome=completed" in r.getMessage() for r in caplog.records)


def _closing_state() -> dict[str, Any]:
    """The state a turn whose report was written saves when its full state cannot be saved."""
    return _recorded_plan_state(plan_approved=True, research_started=True)


class _StateWriteRecorder:
    """Just enough of a `Choice` for a state write: it records each state, or raises when told."""

    def __init__(self, *, fail: bool = False) -> None:
        self.states: list[Any] = []
        self.calls = 0
        self._fail = fail

    def set_state(self, state: Any) -> None:
        self.calls += 1
        if self._fail:
            raise RuntimeError("Trying to append state to a closed choice")
        self.states.append(state)


@pytest.mark.parametrize(
    "unencodable",
    [{1, 2}, float("nan"), "\ud800"],
    ids=["value json cannot encode", "nan", "lone surrogate"],
)
def test_a_state_that_cannot_be_encoded_leaves_the_write_unused(unencodable: Any) -> None:
    turn = completion_module._TurnProgress(prep_state=CrossTurnPrepState())
    choice = _StateWriteRecorder()

    with pytest.raises((TypeError, ValueError)):
        turn.save_state(choice, {"preparation": {"agent_messages": [unencodable]}})  # type: ignore[arg-type]

    assert choice.calls == 0
    assert turn.state_saved is False


def test_a_full_state_that_cannot_be_encoded_after_the_report_saves_the_closing_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A lone surrogate from a tool result: the record's JSON dump keeps it, and UTF-8 refuses it.
    research.messages = [ToolMessage(content="\ud800", tool_call_id="c1", id="t1")]
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    assert result.errors == []
    assert result.state == _closing_state()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    [warning] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "step=save_state error=UnicodeEncodeError saved=closing_state" in warning
    assert any("outcome=completed" in r.getMessage() for r in caplog.records)


def test_a_full_state_that_cannot_be_built_after_the_report_saves_the_closing_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("state unbuildable")

    monkeypatch.setattr(completion_module, "build_completed_record", fail)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    assert result.errors == []
    assert result.state == _closing_state()
    [warning] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "step=save_state error=RuntimeError saved=closing_state" in warning


def test_after_a_closing_state_the_same_research_never_runs_again(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    # A resumed run delivers its report, but its full state cannot be encoded. The older
    # resumable snapshot stays in the history, and must not be resumed again.
    research.messages = [ToolMessage(content="\ud800", tool_call_id="c1", id="t1")]
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    failed = ("yes", _failed_research_state())

    resumed = _post_turn(client, _conversation(failed, ("continue", None)))
    closing = resumed.state
    refused = _post_turn(client, _conversation(failed, ("continue", closing), ("continue", None)))

    assert closing == _closing_state()
    assert len(research.runs) == 1
    assert refused.states == []
    [error] = refused.errors
    assert "new conversation" in error["display_message"]


async def test_a_state_write_that_raises_after_the_report_saves_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    turn = completion_module._TurnProgress(prep_state=CrossTurnPrepState(research_started=True))
    choice = _StateWriteRecorder(fail=True)
    caplog.set_level(logging.INFO)

    completion_module.DeepResearchCompletion._persist(
        turn, choice, report_written=True  # type: ignore[arg-type]
    )

    # The refused write is the only one: no closing state is tried after it.
    assert choice.calls == 1
    [warning] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "step=save_state error=RuntimeError saved=nothing" in warning


# --- The turn: what a failed turn persists ---------------------------------------------------------

_REQUEST = httpx.Request("POST", "https://core.example/openai")
_QUOTA_MESSAGE = "You've exceeded your daily token limit."


def _quota_error() -> openai.RateLimitError:
    body = {"error": {"code": "429", "display_message": _QUOTA_MESSAGE}}
    return openai.RateLimitError(
        "quota", response=httpx.Response(429, request=_REQUEST, json=body), body=body["error"]
    )


def _context_overflow() -> openai.BadRequestError:
    body = {"error": {"code": "context_length_exceeded"}}
    return openai.BadRequestError(
        "too long", response=httpx.Response(400, request=_REQUEST, json=body), body=body["error"]
    )


def _research_progress(**channel_overrides: Any) -> CapturedProgress:
    return CapturedProgress(
        resume_at=ResumePoint.RESEARCH,
        messages=_transcript(),
        channels={**_channels(), **channel_overrides, "research_agent_messages": []},
        data_queries=_records(),
    )


def _failing(error: Exception) -> Any:
    def behave(prep_state: CrossTurnPrepState) -> list[Any]:
        raise error

    return behave


def _started_prep() -> dict[str, Any]:
    return _recorded_plan_state()["preparation"]


def _failure_record() -> dict[str, Any]:
    """The failure record: the `CrossTurnPrepState` the turn started from, nothing beside it, and
    the flag."""
    return {**_recorded_plan_state(), FAILURE_STATE_KEY: True}


def test_a_failed_properties_fetch_persists_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, turn_dial: _TurnDial
) -> None:
    async def fail(request: Any) -> Any:
        raise httpx.ConnectError("core unreachable", request=_REQUEST)

    monkeypatch.setattr(completion_module, "load_application_properties", fail)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.states == []
    assert result.errors


def test_a_preparation_failure_persists_the_state_the_turn_started_from(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, turn_dial: _TurnDial
) -> None:
    def record_a_new_plan_then_fail(prep_state: CrossTurnPrepState) -> list[Any]:
        prep_state.plan = Plan(steps=["A plan this failed turn recorded."])
        prep_state.plan_id = "0000ffff0000ffff0000ffff0000ffff"
        raise _quota_error()

    monkeypatch.setattr(
        completion_module, "PrepAgentRunner", _prep_runner(record_a_new_plan_then_fail)
    )

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state == _failure_record()
    assert result.position_of_state() < result.position_of_error()
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]


def test_research_tools_that_cannot_load_persist_the_failure_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    research.fail_with = httpx.ConnectError("mcp unreachable", request=_REQUEST)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state == _failure_record()


async def test_a_cancelled_turn_persists_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StateRecordingChoice(ChoiceSpy):
        def __init__(self) -> None:
            super().__init__()
            self.states: list[Any] = []

        def set_state(self, state: Any) -> None:
            self.states.append(state)

    async def properties(request: Any) -> ApplicationProperties:
        return ApplicationProperties.model_validate(_TURN_PROPERTIES)

    async def fetch(properties: ApplicationProperties, **_kwargs: Any) -> DataSources:
        return DataSources(text="The topics map.")

    def cancel(prep_state: CrossTurnPrepState) -> list[Any]:
        raise asyncio.CancelledError()

    monkeypatch.setattr(completion_module, "load_application_properties", properties)
    monkeypatch.setattr(completion_module, "fetch_data_sources", fetch)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(cancel))
    choice = _StateRecordingChoice()
    request = Request.model_construct(messages=[Message(role=Role.USER, content="go")])

    with pytest.raises(asyncio.CancelledError):
        await completion_module.DeepResearchCompletion()._run_turn(request, choice)  # type: ignore[arg-type]

    assert choice.states == []


def test_a_quota_error_in_research_saves_the_snapshot_ahead_of_the_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    research.fail_with = _quota_error()
    research.progress = _research_progress()
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    state = result.state
    assert [m["data"]["id"] for m in state["preparation"]["agent_messages"]] == ["p1", "p2"]
    preparation = state["preparation"]
    assert (preparation["plan_approved"], preparation["research_started"]) == (False, False)
    assert preparation["plan_id"] == _PLAN_ID
    assert preparation["plan"] == _started_prep()["plan"]
    assert state[FAILURE_STATE_KEY] is True
    snapshot = state[SNAPSHOT_STATE_KEY]
    assert (snapshot["plan_id"], snapshot["resumable"]) == (_PLAN_ID, True)
    assert snapshot["resume_at"] == "research"
    assert result.position_of_state() < result.position_of_error()
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]


def test_a_context_overflow_saves_a_snapshot_that_is_not_resumable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    research.fail_with = _context_overflow()
    research.progress = _research_progress()
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state[SNAPSHOT_STATE_KEY]["resumable"] is False


def test_a_bucket_that_cannot_be_resolved_saves_a_snapshot_that_is_not_resumable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    turn_dial.bucket = _UploadingDial._Bucket(True)
    research.fail_with = _quota_error()
    research.progress = _research_progress()
    research.progress.messages.append(_image_tool_message())
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    snapshot = result.state[SNAPSHOT_STATE_KEY]
    assert (snapshot["resumable"], snapshot["not_resumable_reason"]) == (
        False,
        "image_upload_failed",
    )
    assert snapshot["research_agent_messages"][-1]["data"]["content"] == [
        {
            "type": "text",
            "text": f"[image not stored: upload failed, image/png, sha256={_PNG_SHA256}]",
        }
    ]
    assert result.state[FAILURE_STATE_KEY] is True
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    warnings = [text for level, text in messages if level == logging.WARNING]
    assert len(warnings) == 1 and "Files bucket lookup failed" in warnings[0]
    [saved] = [text for _, text in messages if "Snapshot saved" in text]
    assert "resumable=False not_resumable_reason=image_upload_failed resume_at=" in saved
    assert sum(1 for level, _ in messages if level >= logging.ERROR) == 1


def test_a_snapshot_that_cannot_be_built_falls_back_to_the_failure_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def unbuildable(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("snapshot unbuildable")

    monkeypatch.setattr(completion_module, "build_snapshot", unbuildable)
    research.fail_with = _quota_error()
    research.progress = _research_progress()
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state == _failure_record()
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    warnings = [text for level, text in messages if level == logging.WARNING]
    assert warnings == [
        "Snapshot could not be saved; saving the failure record instead: error=RuntimeError"
    ]
    assert any("Failure recorded: reason=snapshot_failed" in text for _, text in messages)
    assert not any("Snapshot saved" in text for _, text in messages)
    assert sum(1 for level, _ in messages if level >= logging.ERROR) == 1


def test_a_failure_record_that_cannot_be_saved_still_delivers_the_original_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    caplog: pytest.LogCaptureFixture,
) -> None:
    loads = 0
    real_load = completion_module.load_last_prep_state

    def load_once(request: Any) -> CrossTurnPrepState:
        nonlocal loads
        loads += 1
        if loads > 1:
            raise RuntimeError("state unreadable")
        return real_load(request)

    monkeypatch.setattr(completion_module, "load_last_prep_state", load_once)
    monkeypatch.setattr(
        completion_module, "PrepAgentRunner", _prep_runner(_failing(_quota_error()))
    )
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.states == []
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Failure record could not be saved: error=RuntimeError"]


def _hand_off_with_a_nan(prep_state: CrossTurnPrepState) -> list[Any]:
    """`_hand_off`, with a preparation message holding a `NaN`, which the state check refuses."""
    messages = _hand_off(prep_state)
    messages[0].additional_kwargs["score"] = float("nan")
    return messages


def test_a_snapshot_state_that_cannot_be_encoded_falls_back_to_the_failure_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    research.fail_with = _quota_error()
    research.progress = _research_progress()
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off_with_a_nan))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state == _failure_record()
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        "Snapshot could not be saved; saving the failure record instead: error=ValueError"
    ]


def test_a_failure_record_that_cannot_be_encoded_saves_nothing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _UnencodableState:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def to_dict(self) -> dict[str, Any]:
            return {"messages": [float("nan")]}

    monkeypatch.setattr(completion_module, "PreparationDialState", _UnencodableState)
    monkeypatch.setattr(
        completion_module, "PrepAgentRunner", _prep_runner(_failing(_quota_error()))
    )
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.states == []
    assert _QUOTA_MESSAGE in result.errors[0]["display_message"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Failure record could not be saved: error=ValueError"]


@pytest.mark.parametrize("failure", ["build", "encode"])
def test_a_preparation_only_turn_whose_own_save_fails_saves_the_failure_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    builds = 0

    def unbuildable(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # The full state fails; the failure record that follows it is built as usual.
        nonlocal builds
        builds += 1
        if builds == 1:
            raise RuntimeError("state unbuildable")
        return create_dial_state(*args, **kwargs)

    def present_a_plan(prep_state: CrossTurnPrepState) -> list[Any]:
        # Preparation itself succeeds; only the turn's own save fails.
        score = float("nan") if failure == "encode" else 1.0
        return [AIMessage(content="Here is the plan.", additional_kwargs={"score": score})]

    if failure == "build":
        monkeypatch.setattr(completion_module, "create_dial_state", unbuildable)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(present_a_plan))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    assert result.state == _failure_record()
    # The save's failure is the turn's only failure, so it is the one error delivered.
    assert len(result.errors) == 1
    expected = RuntimeError if failure == "build" else ValueError
    [error_record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_record.exc_info is not None and error_record.exc_info[0] is expected
    records = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert [level for level, _ in records if level == logging.WARNING] == []
    recorded = [i for i, (_, text) in enumerate(records) if "Failure recorded" in text]
    errors = [i for i, (level, _) in enumerate(records) if level >= logging.ERROR]
    assert [records[i][1] for i in recorded] == ["Failure recorded: reason=preparation_failed"]
    assert len(errors) == 1 and recorded[0] < errors[0]


# --- The turn: the records a failed turn logs -------------------------------------------------------


def _records_in_order(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records]


def test_a_preparation_failure_logs_the_failure_record_before_its_one_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        completion_module, "PrepAgentRunner", _prep_runner(_failing(_quota_error()))
    )
    caplog.set_level(logging.INFO)

    _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    records = _records_in_order(caplog)
    recorded = [i for i, (_, text) in enumerate(records) if "Failure recorded" in text]
    errors = [i for i, (level, _) in enumerate(records) if level >= logging.ERROR]
    assert [records[i][1] for i in recorded] == ["Failure recorded: reason=preparation_failed"]
    assert len(errors) == 1
    assert recorded[0] < errors[0]
    assert not any("Snapshot saved" in text for _, text in records)


def test_a_saved_snapshot_is_logged_with_its_facts_and_no_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    research.fail_with = _context_overflow()
    research.progress = _research_progress(research_iteration=1)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    _post_turn(client, _conversation(("yes", _recorded_plan_state()), ("go", None)))

    records = _records_in_order(caplog)
    [(position, saved)] = [
        (i, text) for i, (_, text) in enumerate(records) if "Snapshot saved" in text
    ]
    assert f"plan_id={_PLAN_ID}" in saved
    assert (
        "resumable=False not_resumable_reason=repeating_failure failure_class=input_rejected"
        in saved
    )
    assert "resume_at=research research_iteration=1 messages=5 draft_number=0" in saved
    assert "data_queries=1" in saved
    assert re.search(r"snapshot_bytes=\d+ state_bytes=\d+", saved)
    errors = [i for i, (level, _) in enumerate(records) if level >= logging.ERROR]
    assert len(errors) == 1 and position < errors[0]
    content = [
        "How did inflation change",
        "Find the annual inflation rate",
        "dq_0123abcd45",
        "http",
        "result one",
    ]
    for _, text in records:
        if "Snapshot saved" in text or "Failure recorded" in text:
            assert not any(fragment in text for fragment in content)


# --- The turn: the conversation stays open after a failed research turn ------------------------------


def _failed_research_state(*, resumable: bool = True) -> dict[str, Any]:
    """The state a failed research turn persisted: its preparation messages, the reset
    `CrossTurnPrepState`, the snapshot and the failure flag."""
    preparation = PreparationDialState(
        prep_state=CrossTurnPrepState.model_validate(_started_prep()),
        agent_messages=_hand_off(CrossTurnPrepState()),
    )
    snapshot = _snapshot_dict(resumable=resumable)
    if not resumable:
        snapshot["not_resumable_reason"] = "repeating_failure"
    return create_dial_state(preparation, research=snapshot, turn_failed=True)


def test_the_turn_after_a_failed_research_turn_runs_preparation_on_its_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, turn_dial: _TurnDial
) -> None:
    histories: list[list[Any]] = []

    class _HistoryPrep:
        appended_content = False

        def __init__(self, choice: Any) -> None:
            self._choice = choice
            self.reviews = PrepReviews()

        async def run(self, *, request: Any, prep_state: CrossTurnPrepState, **_: Any) -> list[Any]:
            histories.append(reconstruct_prep_agent_history(request))
            self._choice.append_content("It failed with an error.")
            return [AIMessage(content="It failed with an error.")]

    monkeypatch.setattr(completion_module, "PrepAgentRunner", _HistoryPrep)

    result = _post_turn(
        client,
        _conversation(
            ("yes, go", _recorded_plan_state()),
            ("go", _failed_research_state()),
            ("what happened?", None),
        ),
    )

    assert result.errors == []
    [history] = histories
    assert [m.type for m in history[-4:]] == ["ai", "tool", "system", "human"]
    assert history[-2].content == FAILED_TURN_NOTE
    assert not any(getattr(m, "tool_call_id", None) in {"c1", "c2"} for m in history)
    # A completed turn after a failed one carries neither a snapshot nor the flag.
    assert set(result.state) == {"preparation"}


def test_a_conversation_whose_report_was_delivered_is_still_refused(
    client: TestClient, turn_dial: _TurnDial
) -> None:
    delivered = _recorded_plan_state(plan_approved=True, research_started=True)

    result = _post_turn(client, _conversation(("go", delivered), ("one more thing", None)))

    assert result.states == []
    [error] = result.errors
    assert "new conversation" in error["display_message"]


# --- The turn: resuming from the latest snapshot -----------------------------------------------------


def _with_new_plan(prep_state: CrossTurnPrepState) -> list[Any]:
    """The user changed the plan: `update_plan` renewed its id, and the new plan was approved."""
    prep_state.plan = Plan(steps=["A different first step."])
    prep_state.plan_id = "ffff0000ffff0000ffff0000ffff0000"
    return _hand_off(prep_state)


def test_continue_with_an_unchanged_plan_resumes_from_the_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(
        client, _conversation(("yes, go", _failed_research_state()), ("continue", None))
    )

    assert result.errors == []
    [run] = research.runs
    resumed = run["resumed"]
    assert isinstance(resumed, ResumableSnapshot)
    assert resumed.snapshot.plan_id == _PLAN_ID
    assert resumed.data_queries == _records()
    assert "dial" not in run


@pytest.mark.parametrize(
    ("prep", "snapshot_state", "reason"),
    [
        (_with_new_plan, _failed_research_state(), "plan_changed"),
        (_hand_off, _failed_research_state(resumable=False), "not_resumable"),
    ],
)
def test_a_snapshot_that_will_not_be_resumed_starts_research_fresh(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
    prep: Any,
    snapshot_state: dict[str, Any],
    reason: str,
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(prep))
    caplog.set_level(logging.INFO)

    result = _post_turn(client, _conversation(("yes, go", snapshot_state), ("continue", None)))

    [run] = research.runs
    assert run["resumed"] is None
    (title, body), *_ = result.stages()
    assert title == "[DEBUG] existing snapshot discarded"
    assert f"**reason** {reason}" in body
    assert f"**plan_id** {_PLAN_ID}" in body
    assert f"**current_plan_id** {run['prep_state'].plan_id}" in body
    assert "**resume_at** research" in body
    [record] = [r.getMessage() for r in caplog.records if "Snapshot discarded" in r.getMessage()]
    assert f"reason={reason}" in record


def test_a_refused_snapshot_is_refused_again_on_the_next_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    unreadable = _failed_research_state()
    unreadable[SNAPSHOT_STATE_KEY] = _snapshot_dict(version=SNAPSHOT_VERSION + 1)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    first = _post_turn(client, _conversation(("yes, go", unreadable), ("continue", None)))

    assert "different version" in first.errors[0]["display_message"]
    assert first.state == _failure_record()

    second = _post_turn(
        client,
        _conversation(("yes, go", unreadable), ("continue", first.state), ("continue", None)),
    )

    assert "different version" in second.errors[0]["display_message"]
    assert research.runs == []


def test_a_resumed_run_that_fails_before_its_graph_starts_keeps_the_earlier_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    research.fail_with = httpx.ConnectError("mcp unreachable", request=_REQUEST)
    history = _conversation(("yes, go", _failed_research_state()), ("continue", None))

    failed = _post_turn(client, history)
    research.fail_with = None
    resumed_turn = _post_turn(
        client,
        _conversation(
            ("yes, go", _failed_research_state()), ("continue", failed.state), ("continue", None)
        ),
    )

    assert SNAPSHOT_STATE_KEY not in failed.state
    assert resumed_turn.errors == []
    assert research.runs[-1]["resumed"].snapshot.plan_id == _PLAN_ID


def test_a_second_failure_after_the_graph_streamed_state_is_resumed_from_next(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    research.fail_with = _quota_error()
    research.progress = _research_progress(research_iteration=1)

    failed_again = _post_turn(
        client, _conversation(("yes, go", _failed_research_state()), ("continue", None))
    )
    research.fail_with, research.progress = None, None
    _post_turn(
        client,
        _conversation(
            ("yes, go", _failed_research_state()),
            ("continue", failed_again.state),
            ("continue", None),
        ),
    )

    assert failed_again.state[SNAPSHOT_STATE_KEY]["research_iteration"] == 1
    assert research.runs[-1]["resumed"].snapshot.research_iteration == 1


# --- The turn: the stage that says whether a snapshot was reused -------------------------------------


def test_a_reused_snapshot_is_shown_before_research_starts_and_logged(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(
        client, _conversation(("yes, go", _failed_research_state()), ("continue", None))
    )

    (title, body), (next_title, _) = result.stages()[:2]
    assert (title, next_title) == ("[DEBUG] reusing snapshot", "Starting research")
    expected = [
        ("plan_id", _PLAN_ID),
        ("resume_at", "research"),
        ("research_iteration", "0"),
        ("messages", "5"),
        ("draft_number", "0"),
        ("restored_model_calls_in_iteration", "2"),
    ]
    assert body == "\n\n".join(f"**{key}** {value}" for key, value in expected)
    [record] = [r.getMessage() for r in caplog.records if "Snapshot reused" in r.getMessage()]
    assert record == "Snapshot reused: " + " ".join(f"{key}={value}" for key, value in expected)


def test_a_reused_snapshot_at_report_review_shows_the_round(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    state = _failed_research_state()
    state[SNAPSHOT_STATE_KEY] = _snapshot_dict(
        resume_at=ResumePoint.REPORT_REVIEW.value, reports=["Draft one.", _DRAFT]
    )
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(client, _conversation(("yes, go", state), ("continue", None)))

    (_, body), *_ = result.stages()
    assert "**report_review_round** 2" in body
    assert "restored_model_calls_in_iteration" not in body


def test_a_discarded_snapshot_names_its_resume_point_only_when_known(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    state = _failed_research_state()
    state[SNAPSHOT_STATE_KEY] = _snapshot_dict(resume_at="somewhere-new")
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_with_new_plan))

    result = _post_turn(client, _conversation(("yes, go", state), ("continue", None)))

    (title, body), *_ = result.stages()
    assert title == "[DEBUG] existing snapshot discarded"
    assert "resume_at" not in body


def test_no_snapshot_stage_without_a_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    assert [title for title, _ in result.stages()] == ["Starting research"]
    assert research.runs[0]["resumed"] is None


# --- The turn: a snapshot's images are downloaded before its stage ----------------------------------

_IMAGE_URL = "files/ub/dial-deep-research/c1-0.png"
_OTHER_IMAGE_URL = "files/ub/dial-deep-research/c1-1.png"


def _status_error(status: int) -> DialException:
    return DialException(message=f"HTTP {status}", status_code=status)


class _ScriptedDownloads:
    """A files API whose downloads fail as scripted per URL, then succeed."""

    def __init__(self, failures: dict[str, list[Exception]]) -> None:
        self._failures = {url: list(errors) for url, errors in failures.items()}
        self.requests: list[str] = []

    async def download(self, url: str) -> Any:
        self.requests.append(url)
        if self._failures.get(url):
            raise self._failures[url].pop(0)

        class _Downloaded:
            async def aget_content(self) -> bytes:
                return _PNG_BYTES

        return _Downloaded()


def _failed_research_state_with_images(*urls: str) -> dict[str, Any]:
    transcript = _transcript()
    transcript[2] = ToolMessage(
        content=[{"type": "image", "url": url, "mime_type": "image/png"} for url in urls],
        tool_call_id="c1",
        id="t1",
    )
    state = _failed_research_state()
    state[SNAPSHOT_STATE_KEY] = _snapshot_dict(research_agent_messages=messages_to_dict(transcript))
    return state


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(image_attachments.asyncio, "sleep", sleep)
    return sleeps


def test_a_snapshot_whose_images_download_is_resumed_with_them(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    no_sleep: list[float],
) -> None:
    files = _ScriptedDownloads({_IMAGE_URL: [_status_error(502)]})
    turn_dial.files = files  # type: ignore[assignment]
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    result = _post_turn(
        client,
        _conversation(
            ("yes, go", _failed_research_state_with_images(_IMAGE_URL)), ("continue", None)
        ),
    )

    assert result.errors == []
    [run] = research.runs
    [image] = run["resumed"].messages[2].content
    assert image["base64"] == base64.b64encode(_PNG_BYTES).decode()
    assert files.requests == [_IMAGE_URL, _IMAGE_URL]
    assert result.stages()[0][0] == "[DEBUG] reusing snapshot"


@pytest.mark.parametrize(
    "failures",
    [
        {_IMAGE_URL: [ResourceNotFoundError(message="gone")]},
        {
            _IMAGE_URL: [ResourceNotFoundError(message="gone")],
            _OTHER_IMAGE_URL: [_status_error(503)] * 3,
        },
    ],
    ids=["one image gone", "one image gone and another keeps failing"],
)
def test_a_snapshot_whose_image_is_gone_is_discarded_and_research_runs_fresh(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
    no_sleep: list[float],
    failures: dict[str, list[Exception]],
) -> None:
    files = _ScriptedDownloads(failures)
    turn_dial.files = files  # type: ignore[assignment]
    research.fail_with = _quota_error()
    research.progress = _research_progress(research_iteration=1)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)
    failed = ("yes, go", _failed_research_state_with_images(_IMAGE_URL, _OTHER_IMAGE_URL))

    result = _post_turn(client, _conversation(failed, ("continue", None)))

    [run] = research.runs
    assert run["resumed"] is None
    (title, body), (next_title, _) = result.stages()[:2]
    assert (title, next_title) == ("[DEBUG] existing snapshot discarded", "Starting research")
    assert "**reason** image_missing" in body
    assert "**resume_at** research" in body
    assert files.requests.count(_IMAGE_URL) == 1
    gone = [r.getMessage() for r in caplog.records if "Snapshot image is gone" in r.getMessage()]
    assert gone == [f"Snapshot image is gone: url={_IMAGE_URL}"]
    [record] = [r.getMessage() for r in caplog.records if "Snapshot discarded" in r.getMessage()]
    assert "reason=image_missing" in record
    # The fresh run's own snapshot is the one a later request finds.
    later = _conversation(failed, ("continue", result.state), ("continue", None))
    assert (
        find_latest_snapshot([Message.model_validate(m) for m in later])
        == result.state[SNAPSHOT_STATE_KEY]
    )
    assert result.state[SNAPSHOT_STATE_KEY]["research_iteration"] == 1


def test_a_snapshot_image_that_keeps_failing_fails_the_turn_as_no_graph_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    caplog: pytest.LogCaptureFixture,
    no_sleep: list[float],
) -> None:
    files = _ScriptedDownloads({_IMAGE_URL: [_status_error(503)] * 3})
    turn_dial.files = files  # type: ignore[assignment]
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))
    caplog.set_level(logging.INFO)

    result = _post_turn(
        client,
        _conversation(
            ("yes, go", _failed_research_state_with_images(_IMAGE_URL)), ("continue", None)
        ),
    )

    assert research.runs == []
    assert files.requests == [_IMAGE_URL] * 3
    assert no_sleep == [1.0, 2.0]
    [error] = result.errors
    assert "could not be loaded" in error["display_message"]
    assert result.state == _failure_record()
    assert result.stages() == []
    records = _records_in_order(caplog)
    recorded = [text for _, text in records if "Failure recorded" in text]
    assert recorded == ["Failure recorded: reason=no_graph_state"]
    assert sum(1 for level, _ in records if level >= logging.ERROR) == 1


# --- The turn: a record that is not resumable starts research fresh ----------------------------------


@pytest.mark.parametrize("reason", ["completed", "repeating_failure", "image_upload_failed"])
def test_a_record_that_is_not_resumable_starts_research_fresh_and_is_replaced(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
    reason: str,
) -> None:
    state = _failed_research_state()
    state[SNAPSHOT_STATE_KEY] = _snapshot_dict(
        resumable=False,
        not_resumable_reason=reason,
        resume_at=None if reason == "completed" else "research",
        research_iteration=3,
        reports=["A draft of the earlier run."],
    )
    research.fail_with = _quota_error()
    research.progress = _research_progress(research_iteration=1)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner(_hand_off))

    first = _post_turn(client, _conversation(("yes, go", state), ("continue", None)))

    [run] = research.runs
    assert run["resumed"] is None
    (title, body), *_ = first.stages()
    assert title == "[DEBUG] existing snapshot discarded"
    assert f"**not_resumable_reason** {reason}" in body
    own_record = first.state[SNAPSHOT_STATE_KEY]
    assert own_record["resumable"] is True
    assert own_record["reports"] == []

    research.fail_with, research.progress = None, None
    _post_turn(
        client, _conversation(("yes, go", state), ("continue", first.state), ("continue", None))
    )

    assert research.runs[-1]["resumed"].snapshot.research_iteration == 1


# --- The turn: preparation's reviews --------------------------------------------------------------


def _prep_runner_with_reviews(behave: Any) -> type:
    """`_prep_runner`, whose checks each made one review this turn."""
    base = _prep_runner(behave)

    class _ReviewingPrep(base):  # type: ignore[misc, valid-type]
        def __init__(self, choice: Any) -> None:
            super().__init__(choice)
            self.reviews = PrepReviews(
                query_reviews=[
                    QueryReviewResponse(assessment="The query names its period.", questions=[])
                ],
                plan_reviews=[
                    PlanReviewResponse(
                        assessment="The user approved the plan.",
                        recorded_plan_matches=True,
                        user_approved_a_plan=True,
                        failure_reason="",
                    )
                ],
            )

    return _ReviewingPrep


def _saved_reviews(state: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    preparation = state["preparation"]
    return preparation["query_reviews"], preparation["plan_reviews"]


def test_preparations_reviews_are_saved_whole_on_success(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner_with_reviews(_hand_off))

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    query_reviews, plan_reviews = _saved_reviews(result.state)
    assert query_reviews == [{"assessment": "The query names its period.", "questions": []}]
    assert plan_reviews[0]["assessment"] == "The user approved the plan."


def test_preparations_reviews_are_saved_with_a_failed_research_turns_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    research.fail_with = _quota_error()
    research.progress = _research_progress()
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner_with_reviews(_hand_off))

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    query_reviews, plan_reviews = _saved_reviews(result.state)
    assert len(query_reviews) == 1 and len(plan_reviews) == 1
    assert result.state[FAILURE_STATE_KEY] is True


def test_the_failure_record_saves_no_reviews(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    turn_dial: _TurnDial,
    research: type[_ResearchSpy],
) -> None:
    research.fail_with = httpx.ConnectError("mcp unreachable", request=_REQUEST)
    monkeypatch.setattr(completion_module, "PrepAgentRunner", _prep_runner_with_reviews(_hand_off))

    result = _post_turn(client, _conversation(("yes, go", _recorded_plan_state()), ("go", None)))

    assert _saved_reviews(result.state) == ([], [])
    assert result.state["preparation"]["agent_messages"] == []
