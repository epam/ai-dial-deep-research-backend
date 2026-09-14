"""The citation step, as the research runner runs it between the graph and the report.

What is protected here: the delivered text is the settled draft with its hyperlinks gone and
each convertible citation replaced by a marker tag; that same text is what gets persisted; the
annotations follow the content; the step's stage opens only when it has work; and no failure of
any of it costs the report. The string rules themselves are `test_citations.py`'s — this suite
is about what the runner does with them.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from aidial_sdk.chat_completion import Status
from langchain_core.documents.base import Blob
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import ValuesStreamPart

from dial_deep_research.app.research import runner as runner_module
from dial_deep_research.app.research.runner import CITATIONS_ACTIVITY, ResearchRunner
from dial_deep_research.app_properties import DocumentMetadataSource
from tests.dial_spies import ChoiceSpy

_TOOL_NAME = "share_documents"
_DATASET_TOOL_NAME = "list_datasets"
_TITLE_KEY = "publication_title"
_METADATA_SOURCE = DocumentMetadataSource(
    server_name="publications",
    resource_template="documents://metadata/{document_ids}",
    title_key=_TITLE_KEY,
)
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


class _MetadataClient:
    """Answers the document-metadata read, and records the URIs it was asked for.

    A stub rather than a live client: what the read costs the delivery is decided by the answer,
    and every answer shape is exercised in `test_document_metadata.py`.
    """

    def __init__(
        self, titles: dict[int, str] | None = None, *, raises: Exception | None = None
    ) -> None:
        self._titles = titles or {}
        self._raises = raises
        self.requested_uris: list[str] = []

    async def get_resources(self, server_name: str, *, uris: list[str]) -> list[Blob]:
        self.requested_uris.extend(uris)
        if self._raises is not None:
            raise self._raises
        body = {str(i): {_TITLE_KEY: title} for i, title in self._titles.items()}
        return [Blob.from_data(data=json.dumps(body), mime_type="application/json")]


class _UnreadableMetadataClient(_MetadataClient):
    async def get_resources(self, server_name: str, *, uris: list[str]) -> list[Blob]:
        self.requested_uris.extend(uris)
        return [Blob.from_data(data="not json at all", mime_type="application/json")]


def _catalogue_tool(
    *,
    datasets: list[dict[str, Any]] | None = None,
    artifact: Any = None,
    raises: Exception | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> BaseTool:
    """A dataset-metadata tool shaped like the MCP adapter's: the catalogue in the artifact."""
    payload = artifact if datasets is None else {"structured_content": {"datasets": datasets}}

    async def list_datasets() -> tuple[str, Any]:
        if calls is not None:
            calls.append({})
        if raises is not None:
            raise raises
        return "the catalogue, serialized as text", payload

    return StructuredTool.from_function(
        coroutine=list_datasets,
        name=_DATASET_TOOL_NAME,
        description="List the datasets this channel exposes.",
        response_format="content_and_artifact",
    )


async def _deliver(
    runner: ResearchRunner,
    *,
    tool: BaseTool | None = None,
    configured_tool_name: str | None = _TOOL_NAME,
    mcp_client: Any = None,
    metadata_source: DocumentMetadataSource | None = None,
    dataset_tool: BaseTool | None = None,
    configured_dataset_tool_name: str | None = None,
    pill_title_max_chars: int | None = 20,
) -> None:
    await runner._deliver_report(
        file_sharing_tool=tool,
        configured_tool_name=configured_tool_name,
        mcp_client=mcp_client or _MetadataClient(),
        metadata_source=metadata_source,
        dataset_metadata_tool=dataset_tool,
        configured_dataset_tool_name=configured_dataset_tool_name,
        pill_title_max_chars=pill_title_max_chars,
    )


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


# --- document titles ----------------------------------------------------------------------------


_TITLE = "Market Outlook 2025"


async def test_a_resolved_title_labels_the_pill_and_its_popup_entry() -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(
        runner,
        tool=_sharing_tool(urls={"442": _URL}),
        mcp_client=_MetadataClient({442: _TITLE}),
        metadata_source=_METADATA_SOURCE,
    )

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == [f"{_TITLE}, page 3"]
    assert annotations[0]["body"]["source"]["attachment"]["title"] == f"{_TITLE}, page 3"


async def test_one_read_asks_about_every_cited_document() -> None:
    """The ids come from the report text alone, which is what frees the read from waiting."""
    runner, _ = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")
    client = _MetadataClient({442: _TITLE})

    await _deliver(
        runner,
        tool=_sharing_tool(urls={"442": _URL}),
        mcp_client=client,
        metadata_source=_METADATA_SOURCE,
    )

    assert client.requested_uris == ["documents://metadata/442,12"]


async def test_a_title_for_a_document_that_resolved_no_url_is_not_shown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """It draws no pill, so the title reaches no label and is counted among none."""
    runner, choice = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")

    with caplog.at_level(logging.INFO):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL}),
            mcp_client=_MetadataClient({442: _TITLE, 12: "A Title Never Shown"}),
            metadata_source=_METADATA_SOURCE,
        )

    assert "[doc 12, page 1]" in choice.content
    assert "A Title Never Shown" not in choice.content
    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == [f"{_TITLE}, page 3"]
    event = next(r.message for r in caplog.records if "Report citations resolved" in r.message)
    assert "documents_requested=2 documents_resolved=1 documents_titled=1" in event


async def test_a_channel_serving_no_documents_labels_every_pill_from_its_marker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A document server must name a metadata resource, so no source means no document server —
    a routine configuration that must not warn on every report it delivers."""
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")
    client = _MetadataClient({442: _TITLE})

    with caplog.at_level(logging.DEBUG, logger=runner_module.logger.name):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL}),
            mcp_client=client,
            metadata_source=None,
        )

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == ["doc 442, page 3"]
    assert client.requested_uris == []
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert any("no MCP server serves documents" in r.message for r in caplog.records)


async def test_a_failing_metadata_read_still_delivers_every_pill(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL}),
            mcp_client=_MetadataClient(raises=RuntimeError("connection reset")),
            metadata_source=_METADATA_SOURCE,
        )

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == ["doc 442, page 3"]
    assert "kind=metadata_read_failed" in _one_warning(caplog)


async def test_an_unreadable_metadata_answer_still_delivers_every_pill(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL}),
            mcp_client=_UnreadableMetadataClient(),
            metadata_source=_METADATA_SOURCE,
        )

    assert '<cit data-id="' in choice.content
    assert "kind=metadata_unreadable_result" in _one_warning(caplog)


async def test_a_document_carrying_no_title_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A channel's metadata is its own; a missing key there costs a label, not a pill."""
    runner, choice = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")

    with caplog.at_level(logging.DEBUG, logger=runner_module.logger.name):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL, "12": _OTHER_URL}),
            mcp_client=_MetadataClient({442: _TITLE}),
            metadata_source=_METADATA_SOURCE,
        )

    annotations = choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]
    assert [a["body"]["title"] for a in annotations] == [f"{_TITLE}, page 3", "doc 12, page 1"]
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_the_step_event_counts_resolved_and_titled_documents(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, _ = _make_runner()
    _settle(runner, "One [doc 442, page 3]. Two [doc 12, page 1].")

    with caplog.at_level(logging.INFO):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL, "12": _OTHER_URL}),
            mcp_client=_MetadataClient({442: _TITLE}),
            metadata_source=_METADATA_SOURCE,
        )

    event = next(r.message for r in caplog.records if "Report citations resolved" in r.message)
    assert "documents_requested=2 documents_resolved=2 documents_titled=1" in event
    assert _TITLE not in event


# --- dataset citations ---------------------------------------------------------------------------


_URN = "IMF:WEO(1.0.0)"
_DATASET_NAME = "World Economic Outlook"
_PORTAL_URL = "https://portal.example.org/datasets/imf-weo"
_RECORD = {"id": _URN, "name": _DATASET_NAME, "url": _PORTAL_URL, "lastUpdated": "2025-04-30"}


def _dataset_annotations(choice: ChoiceSpy) -> list[dict[str, Any]]:
    return choice.chunks[0]["choices"][0]["delta"]["custom_content"]["annotations"]


async def test_a_cited_dataset_is_delivered_as_a_pill_opening_its_page() -> None:
    runner, choice = _make_runner()
    _settle(runner, f"Growth slowed. [dataset {_URN}]")

    await _deliver(
        runner,
        configured_tool_name=None,
        dataset_tool=_catalogue_tool(datasets=[_RECORD]),
        configured_dataset_tool_name=_DATASET_TOOL_NAME,
    )

    assert f"[dataset {_URN}]" not in choice.content
    assert '<cit data-id="' in choice.content
    annotation = _dataset_annotations(choice)[0]
    assert annotation["body"]["title"] == f"{_DATASET_NAME} dataset"
    assert annotation["body"]["source"]["attachment"]["url"] == _PORTAL_URL
    assert annotation["body"]["source"]["attachment"]["type"] == "text/html"
    assert annotation["body"]["quote"] == f"* URN: {_URN}\n* Last update: 2025-04-30"
    assert "selector" not in annotation["body"]


async def test_a_document_and_a_dataset_citation_are_both_delivered() -> None:
    runner, choice = _make_runner()
    _settle(runner, f"One [doc 442, page 3]. Two [dataset {_URN}].")

    await _deliver(
        runner,
        tool=_sharing_tool(urls={"442": _URL}),
        dataset_tool=_catalogue_tool(datasets=[_RECORD]),
        configured_dataset_tool_name=_DATASET_TOOL_NAME,
    )

    assert [a["body"]["title"] for a in _dataset_annotations(choice)] == [
        "doc 442, page 3",
        f"{_DATASET_NAME} dataset",
    ]


async def test_the_three_resolutions_are_issued_together() -> None:
    """None of them waits on another: the ids each needs come from the report text alone."""
    order: list[str] = []

    async def _slow_sharing(document_ids: list[int]) -> tuple[str, Any]:
        order.append("file-sharing started")
        await asyncio.sleep(0)
        order.append("file-sharing finished")
        return "mapping", {"structured_content": {"442": _URL}}

    sharing_tool = StructuredTool.from_function(
        coroutine=_slow_sharing,
        name=_TOOL_NAME,
        description="Copy each document into the caller's storage and return its URL.",
        response_format="content_and_artifact",
    )

    class _RecordingMetadataClient(_MetadataClient):
        async def get_resources(self, server_name: str, *, uris: list[str]) -> list[Blob]:
            order.append("metadata read started")
            return await super().get_resources(server_name, uris=uris)

    calls: list[dict[str, Any]] = []
    runner, _ = _make_runner()
    _settle(runner, f"One [doc 442, page 3]. Two [dataset {_URN}].")

    await _deliver(
        runner,
        tool=sharing_tool,
        mcp_client=_RecordingMetadataClient({442: _TITLE}),
        metadata_source=_METADATA_SOURCE,
        dataset_tool=_catalogue_tool(datasets=[_RECORD], calls=calls),
        configured_dataset_tool_name=_DATASET_TOOL_NAME,
    )

    assert order.index("metadata read started") < order.index("file-sharing finished")
    assert len(calls) == 1


async def test_a_report_citing_no_dataset_makes_no_catalogue_call() -> None:
    calls: list[dict[str, Any]] = []
    runner, _ = _make_runner()
    _settle(runner, "Defaults rise. [doc 442, page 3]")

    await _deliver(
        runner,
        tool=_sharing_tool(urls={"442": _URL}),
        dataset_tool=_catalogue_tool(datasets=[_RECORD], calls=calls),
        configured_dataset_tool_name=_DATASET_TOOL_NAME,
    )

    assert calls == []


async def test_no_configured_dataset_tool_is_not_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Naming the tool is optional, so an instance without one would otherwise warn per turn."""
    runner, choice = _make_runner()
    _settle(runner, f"Growth slowed. [dataset {_URN}]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(
            runner,
            configured_tool_name=None,
            dataset_tool=None,
            configured_dataset_tool_name=None,
        )

    assert choice.content == f"Growth slowed. [dataset {_URN}]"
    assert choice.chunks == []
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_a_configured_dataset_tool_the_server_does_not_advertise_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner, choice = _make_runner()
    _settle(runner, f"Growth slowed. [dataset {_URN}]")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(
            runner,
            configured_tool_name=None,
            dataset_tool=None,
            configured_dataset_tool_name=_DATASET_TOOL_NAME,
        )

    assert choice.content == f"Growth slowed. [dataset {_URN}]"
    warning = _one_warning(caplog)
    assert "kind=dataset_tool_not_advertised" in warning
    assert f"tool={_DATASET_TOOL_NAME}" in warning


@pytest.mark.parametrize(
    ("tool_kwargs", "kind"),
    [
        pytest.param({"raises": RuntimeError("no")}, "dataset_call_failed", id="the-call-raises"),
        pytest.param({"artifact": None}, "dataset_no_structured_result", id="no-structured-result"),
        pytest.param(
            {"artifact": {"structured_content": {"items": []}}},
            "dataset_unreadable_result",
            id="unreadable-answer",
        ),
    ],
)
async def test_a_failed_catalogue_read_delivers_every_dataset_marker_as_text(
    caplog: pytest.LogCaptureFixture, tool_kwargs: dict[str, Any], kind: str
) -> None:
    runner, choice = _make_runner()
    _settle(runner, f"One [doc 442, page 3]. Two [dataset {_URN}].")

    with caplog.at_level(logging.WARNING, logger=runner_module.logger.name):
        await _deliver(
            runner,
            tool=_sharing_tool(urls={"442": _URL}),
            dataset_tool=_catalogue_tool(**tool_kwargs),
            configured_dataset_tool_name=_DATASET_TOOL_NAME,
        )

    # The document's pill is drawn all the same: the two resolutions fail independently.
    assert f"[dataset {_URN}]" in choice.content
    assert [a["body"]["title"] for a in _dataset_annotations(choice)] == ["doc 442, page 3"]
    assert f"kind={kind}" in _one_warning(caplog)


async def test_a_dataset_the_catalogue_reports_without_a_page_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Whether a dataset has a portal page is the channel's own data, not a fault."""
    runner, choice = _make_runner()
    _settle(runner, f"Growth slowed. [dataset {_URN}]")

    with caplog.at_level(logging.INFO):
        await _deliver(
            runner,
            configured_tool_name=None,
            dataset_tool=_catalogue_tool(datasets=[{"id": _URN, "name": _DATASET_NAME}]),
            configured_dataset_tool_name=_DATASET_TOOL_NAME,
        )

    assert choice.content == f"Growth slowed. [dataset {_URN}]"
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == []
    event = next(r.message for r in caplog.records if "Report citations resolved" in r.message)
    assert "datasets_requested=1 datasets_resolved=0" in event


async def test_the_step_event_counts_requested_and_resolved_datasets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    other = "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)"
    runner, _ = _make_runner()
    _settle(runner, f"One [dataset {_URN}]. Two [dataset {other}].")

    with caplog.at_level(logging.INFO):
        await _deliver(
            runner,
            configured_tool_name=None,
            dataset_tool=_catalogue_tool(datasets=[_RECORD]),
            configured_dataset_tool_name=_DATASET_TOOL_NAME,
        )

    event = next(r.message for r in caplog.records if "Report citations resolved" in r.message)
    assert "datasets_requested=2 datasets_resolved=1" in event
    assert _DATASET_NAME not in event
    assert _PORTAL_URL not in event
    assert _URN not in event


async def test_the_step_announces_itself_while_it_resolves_datasets() -> None:
    """A catalogue read is work worth announcing, as a file-sharing call is."""
    runner, choice = _make_runner()
    runner._set_activity("Writing the report")
    _settle(runner, f"Growth slowed. [dataset {_URN}]")

    await _deliver(
        runner,
        configured_tool_name=None,
        dataset_tool=_catalogue_tool(datasets=[_RECORD]),
        configured_dataset_tool_name=_DATASET_TOOL_NAME,
    )

    assert choice.stage_titles == ["Writing the report", CITATIONS_ACTIVITY]
    assert choice.open_stages == []
