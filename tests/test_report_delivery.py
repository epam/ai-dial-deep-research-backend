"""The citation step, as the research runner runs it between the graph and the report.

What is protected here: the delivered text is the settled draft with its hyperlinks gone and
each convertible citation replaced by a marker tag; that same text is what gets persisted; the
annotations follow the content; the step's stage opens only when it has work; and no failure of
any of it costs the report. The string rules themselves are `test_citations.py`'s — this suite
is about what the runner does with them.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from aidial_sdk.chat_completion import Status
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import ValuesStreamPart

from dial_deep_research.app.research import runner as runner_module
from dial_deep_research.app.research.runner import CITATIONS_ACTIVITY, ResearchRunner
from tests.dial_spies import ChoiceSpy

_TOOL_NAME = "share_documents"
_URL = "files/bucket/appdata/deep-research/docs/outlook.pdf"
_OTHER_URL = "files/bucket/appdata/deep-research/docs/review.pdf"


def _make_runner(*, content_already_streamed: bool = False) -> tuple[ResearchRunner, ChoiceSpy]:
    choice = ChoiceSpy()
    runner = ResearchRunner(  # type: ignore[arg-type]
        choice, content_already_streamed=content_already_streamed
    )
    return runner, choice


def _settle(runner: ResearchRunner, report: str, *, transcript: list[Any] | None = None) -> None:
    """Put the runner in the state the graph leaves it in: a transcript and a settled draft."""
    runner._handle_part(
        ValuesStreamPart(
            type="values",
            ns=(),
            data={
                "messages": transcript if transcript is not None else [HumanMessage(content="q")],
                "report": report,
            },
            interrupts=(),
        )
    )


def _sharing_tool(
    *,
    urls: dict[str, str] | None = None,
    artifact: Any = None,
    raises: Exception | None = None,
    calls: list[list[int]] | None = None,
) -> BaseTool:
    """A file-sharing tool shaped like the MCP adapter's: the mapping in the artifact."""
    payload = artifact if urls is None else {"structured_content": urls}

    async def share(document_ids: list[int]) -> tuple[str, Any]:
        if calls is not None:
            calls.append(document_ids)
        if raises is not None:
            raise raises
        return "the mapping, serialized as text", payload

    return StructuredTool.from_function(
        coroutine=share,
        name=_TOOL_NAME,
        description="Copy each document into the caller's storage and return its URL.",
        response_format="content_and_artifact",
    )


async def _deliver(
    runner: ResearchRunner,
    *,
    tool: BaseTool | None = None,
    configured_tool_name: str | None = _TOOL_NAME,
) -> None:
    await runner._deliver_report(file_sharing_tool=tool, configured_tool_name=configured_tool_name)


# --- the delivered text -------------------------------------------------------------------------


async def test_a_convertible_citation_is_delivered_as_a_marker_tag() -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert "[doc 442, page 3]" not in choice.content
    assert '<cit data-id="' in choice.content
    assert len(choice.chunks) == 1
    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == ["doc 442, page 3"]
    assert annotations[0]["body"]["source"]["attachment"]["url"] == _URL


async def test_the_delivered_text_is_what_gets_persisted() -> None:
    """A later turn reads back what the user saw, marker tags included."""
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    report_message = runner._messages[-1]
    assert isinstance(report_message, AIMessage)
    assert report_message.content == choice.content


async def test_a_hyperlink_is_removed_even_with_no_file_sharing_tool() -> None:
    """The hyperlink rule has no configuration switch; the citation conversion does."""
    runner, choice = _make_runner()
    _settle(runner, "See the [latest outlook](https://example.org/o) — [doc 442, page 3].")

    await _deliver(runner, tool=None, configured_tool_name=None)

    assert choice.content == "See the latest outlook — [doc 442, page 3]."
    assert choice.chunks == []


async def test_one_call_carries_every_cited_document_id_once() -> None:
    runner, _ = _make_runner()
    _settle(
        runner,
        "One [doc 442, page 3]. Two [doc 12, page 1]. Again [doc 442, page 9].",
    )
    calls: list[list[int]] = []

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL, "12": _OTHER_URL}, calls=calls))

    assert calls == [[442, 12]]


async def test_a_partially_resolved_response_converts_what_it_can() -> None:
    runner, choice = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert "[doc 442, page 3]" not in choice.content
    assert "[doc 12, page 1]" in choice.content


async def test_a_report_that_cites_nothing_is_delivered_unchanged() -> None:
    runner, choice = _make_runner()
    _settle(runner, "## Overview\n\nNothing was found.")
    calls: list[list[int]] = []

    await _deliver(runner, tool=_sharing_tool(urls={}, calls=calls))

    assert choice.content == "## Overview\n\nNothing was found."
    assert calls == []
    assert choice.chunks == []


async def test_preparation_text_still_gets_its_separator() -> None:
    runner, choice = _make_runner(content_already_streamed=True)
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert choice.content.startswith("\n\nDefaults rise. ")


async def test_a_turn_with_no_report_delivers_nothing() -> None:
    runner, choice = _make_runner()
    _settle(runner, "")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert choice.content == ""
    assert choice.chunks == []
    assert runner._messages == [HumanMessage(content="q")]


# --- the annotations reach the choice after the content -----------------------------------------


async def test_the_annotations_follow_the_content() -> None:
    """The client reads them off a finished message, and content is append-only."""
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")
    sent: list[str] = []
    original_append = choice.append_content
    original_send = choice.send_chunk

    def append(text: str) -> None:
        sent.append("content")
        original_append(text)

    def send(chunk: object) -> None:
        sent.append("annotations")
        original_send(chunk)

    choice.append_content = append  # type: ignore[method-assign]
    choice.send_chunk = send  # type: ignore[method-assign]

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert sent == ["content", "annotations"]


# --- the activity stage -------------------------------------------------------------------------


async def test_the_step_announces_itself_while_it_resolves_documents() -> None:
    runner, choice = _make_runner()
    runner._set_activity("Writing the report")
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert choice.stage_titles == ["Writing the report", CITATIONS_ACTIVITY]
    assert choice.open_stages == []


async def test_the_content_arrives_after_the_step_closed_its_stage() -> None:
    runner, choice = _make_runner()
    runner._set_activity("Writing the report")
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    citation_stage = choice.stages[-1]
    assert citation_stage.status is Status.COMPLETED
    assert choice.content.startswith("Defaults rise.")


async def test_a_step_with_nothing_to_do_opens_no_stage() -> None:
    """It would open and close in the same instant, which renders as a finished step."""
    runner, choice = _make_runner()
    runner._set_activity("Writing the report")
    _settle(runner, "## Overview\n\nNothing was found.")

    await _deliver(runner, tool=_sharing_tool(urls={}))

    assert choice.stage_titles == ["Writing the report"]
    assert choice.open_stages == []


async def test_a_draft_carrying_only_a_link_still_announces_the_edit() -> None:
    runner, choice = _make_runner()
    runner._set_activity("Writing the report")
    _settle(runner, "See the [latest outlook](https://example.org/o).")

    await _deliver(runner, tool=None, configured_tool_name=None)

    assert choice.stage_titles == ["Writing the report", CITATIONS_ACTIVITY]


# --- every failure costs the citations and never the report -------------------------------------


async def test_no_configured_tool_is_not_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Inline citations are switched off there, so every turn would otherwise warn."""
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.DEBUG, logger=runner_module.logger.name):
        await _deliver(runner, tool=None, configured_tool_name=None)

    assert choice.content == "Defaults rise. [doc 442, page 3]"
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert any("no MCP server names a file-sharing tool" in r.message for r in caplog.records)


async def test_a_configured_tool_the_server_does_not_advertise_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=None, configured_tool_name=_TOOL_NAME)

    assert choice.content == "Defaults rise. [doc 442, page 3]"
    warning = _one_warning(caplog)
    assert "kind=tool_not_advertised" in warning
    assert f"tool={_TOOL_NAME}" in warning


async def test_a_failing_tool_call_delivers_every_marker_as_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(raises=RuntimeError("no")))

    assert choice.content == "Defaults rise. [doc 442, page 3]"
    assert choice.chunks == []
    assert "kind=call_failed" in _one_warning(caplog)


async def test_an_unreadable_response_delivers_every_marker_as_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(artifact={"structured_content": ["a list"]}))

    assert choice.content == "Defaults rise. [doc 442, page 3]"
    assert "kind=unreadable_result" in _one_warning(caplog)


async def test_a_response_with_no_structured_result_delivers_every_marker_as_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(artifact=None))

    assert choice.content == "Defaults rise. [doc 442, page 3]"
    assert "kind=no_structured_result" in _one_warning(caplog)


async def test_an_id_the_response_omitted_warns_with_its_count_and_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """That document's citations lost their pills, which the counts alone would not show."""
    runner, choice = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    warning = _one_warning(caplog)
    assert "kind=ids_unresolved" in warning
    assert "ids_unresolved=1" in warning
    assert "12" not in warning.replace(f"tool={_TOOL_NAME}", "")
    assert _URL not in warning


async def test_an_exception_in_the_link_pass_delivers_the_settled_draft(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "See https://example.org/o — [doc 442, page 3].")
    monkeypatch.setattr(runner_module, "remove_hyperlinks", _raise)

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert choice.content == "See https://example.org/o — [doc 442, page 3]."
    assert choice.chunks == []
    assert "kind=link_pass_failed" in _one_warning(caplog)


async def test_an_exception_in_the_conversion_keeps_the_link_removal(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "See the [latest outlook](https://example.org/o) — [doc 442, page 3].")
    monkeypatch.setattr(runner_module, "convert_citations", _raise)

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert choice.content == "See the latest outlook — [doc 442, page 3]."
    assert choice.chunks == []
    assert "kind=conversion_failed" in _one_warning(caplog)


async def test_a_failed_emission_leaves_its_tags_unclaimed(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The content is already appended and DIAL content is append-only: nothing is retried."""
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")
    monkeypatch.setattr(runner_module, "send_annotations", _raise)

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    assert '<cit data-id="' in choice.content
    assert choice.chunks == []
    assert "kind=emission_failed" in _one_warning(caplog)


# --- the step's own INFO event ------------------------------------------------------------------


async def test_the_step_reports_its_counts_and_no_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, _ = _make_runner()
    _settle(
        runner,
        "See the [latest outlook](https://example.org/o).\n\n"
        "One [doc 442, page 3]. Two [doc 12, page 1]. Again [doc 442, page 9].",
    )

    with caplog.at_level(logging.INFO, logger="dial_deep_research.app.research.runner"):
        await _deliver(runner, tool=_sharing_tool(urls={"442": _URL}))

    event = next(r.getMessage() for r in caplog.records if "Report citations resolved" in r.message)
    assert "documents_requested=2" in event
    assert "documents_resolved=1" in event
    assert "annotations=2" in event
    assert "markers_left=1" in event
    assert "hyperlinks_removed=1" in event
    assert _URL not in event


async def test_the_step_reports_even_when_it_converted_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, _ = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.INFO, logger="dial_deep_research.app.research.runner"):
        await _deliver(runner, tool=_sharing_tool(raises=RuntimeError("no")))

    event = next(r.getMessage() for r in caplog.records if "Report citations resolved" in r.message)
    assert "documents_requested=1" in event
    assert "documents_resolved=0" in event
    assert "annotations=0" in event
    assert "markers_left=1" in event


def _raise(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("this pass blew up")


def _one_warning(caplog: pytest.LogCaptureFixture) -> str:
    warnings = [
        record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1, warnings
    return warnings[0]
