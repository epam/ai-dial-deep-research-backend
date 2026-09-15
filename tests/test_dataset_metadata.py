"""Calling the dataset-metadata tool and reading the catalogue it answers with.

The tools here are real LangChain `StructuredTool`s built the way `langchain-mcp-adapters`
builds them — `response_format="content_and_artifact"`, the structured result in the artifact —
so these tests exercise how a catalogue actually reaches the app rather than a stand-in for it.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, ToolException

from dial_deep_research.app.research.dataset_metadata import (
    KIND_DATASET_CALL_FAILED,
    KIND_DATASET_NO_STRUCTURED_RESULT,
    KIND_DATASET_UNREADABLE_RESULT,
    DatasetMetadataError,
    read_dataset_sources,
)

_URN = "IMF:WEO(1.0.0)"
_NAME = "World Economic Outlook"
_URL = "https://portal.example.org/datasets/imf-weo"
_TOOL_NAME = "list_datasets"


def _catalogue_tool(
    *,
    datasets: list[dict[str, Any]] | None = None,
    artifact: Any = None,
    raises: Exception | None = None,
    calls: list[dict[str, Any]] | None = None,
    handle_tool_error: bool = False,
) -> BaseTool:
    payload = artifact if datasets is None else {"structured_content": {"datasets": datasets}}

    async def list_datasets(**kwargs: Any) -> tuple[str, Any]:
        if calls is not None:
            calls.append(kwargs)
        if raises is not None:
            raise raises
        return "the catalogue, serialized as text", payload

    tool = StructuredTool.from_function(
        coroutine=list_datasets,
        name=_TOOL_NAME,
        description="List the datasets this channel exposes.",
        response_format="content_and_artifact",
    )
    # This tool keeps the research agent's error handling, which is what turns a server error
    # into an error `ToolMessage` instead of an exception.
    tool.handle_tool_error = handle_tool_error
    return tool


async def test_the_reported_record_is_read_off_the_structured_result() -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "name": _NAME, "url": _URL, "lastUpdated": "2025-04-30"}]
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url == _URL
    assert sources[_URN].name == _NAME
    assert sources[_URN].last_updated == "2025-04-30"


async def test_the_call_carries_no_arguments() -> None:
    """The contract's input is none: the tool answers with the channel's whole catalogue."""
    calls: list[dict[str, Any]] = []
    tool = _catalogue_tool(datasets=[], calls=calls)

    await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert calls == [{}]


async def test_one_call_serves_every_cited_dataset() -> None:
    other = "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)"
    calls: list[dict[str, Any]] = []
    tool = _catalogue_tool(
        datasets=[
            {"id": _URN, "name": _NAME, "url": _URL},
            {"id": other, "name": "Primary Commodity Prices", "url": f"{_URL}-pcp"},
            {"id": "IMF:NOT_CITED(1.0.0)", "name": "Not cited", "url": f"{_URL}-nc"},
        ],
        calls=calls,
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN, other])

    assert sorted(sources) == sorted([_URN, other])
    assert len(calls) == 1


async def test_a_record_the_answer_omits_is_absent_rather_than_a_failure() -> None:
    tool = _catalogue_tool(datasets=[{"id": _URN, "name": _NAME, "url": _URL}])

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN, "IMF:UNKNOWN(1.0.0)"])

    assert list(sources) == [_URN]


async def test_extra_fields_in_a_record_are_ignored() -> None:
    """A server may report more than a citation uses without breaking the contract."""
    tool = _catalogue_tool(
        datasets=[
            {
                "id": _URN,
                "name": _NAME,
                "url": _URL,
                "description": "Projections and historical data.",
                "provider": "IMF",
                "numberOfIndicators": 47,
            }
        ]
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].name == _NAME
    # Every reported field is carried whole, which is what a References column reads.
    assert sources[_URN].raw_fields["numberOfIndicators"] == 47
    assert sources[_URN].raw_fields["provider"] == "IMF"


@pytest.mark.parametrize(
    ("record", "case"),
    [
        ({"id": _URN, "name": _NAME}, "the url is absent"),
        ({"id": _URN, "name": _NAME, "url": None}, "the url is null"),
        ({"id": _URN, "name": _NAME, "url": ""}, "the url is empty"),
        ({"id": _URN, "name": _NAME, "url": "files/bucket/catalogue.pdf"}, "the url is relative"),
        ({"id": _URN, "name": _NAME, "url": 42}, "the url is not a string"),
    ],
)
async def test_a_dataset_with_no_page_a_browser_can_open_is_kept_without_a_url(
    record: dict[str, Any], case: str
) -> None:
    """It is a cited dataset either way: its citations keep their marker text for want of a page
    to open, and the report's References section still lists it by name."""
    tool = _catalogue_tool(datasets=[record])

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url is None, case
    assert sources[_URN].name == _NAME, case


@pytest.mark.parametrize(
    ("name", "case"),
    [
        (None, "the name is null"),
        ("", "the name is empty"),
        ("   ", "the name is only whitespace"),
        (2025, "the name is not a string"),
    ],
)
async def test_a_record_with_no_usable_name_is_still_citable(name: Any, case: str) -> None:
    """The page is what makes a dataset citable; the label falls back to the URN."""
    tool = _catalogue_tool(datasets=[{"id": _URN, "name": name, "url": _URL}])

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].name is None, case
    assert sources[_URN].url == _URL


@pytest.mark.parametrize(
    ("last_updated", "case"),
    [
        (None, "the date is null"),
        ("", "the date is empty"),
        (20250430, "the date is not a string"),
    ],
)
async def test_a_date_that_is_not_a_usable_string_reads_as_absent(
    last_updated: Any, case: str
) -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "name": _NAME, "url": _URL, "lastUpdated": last_updated}]
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].last_updated is None, case


async def test_a_urn_is_matched_character_for_character() -> None:
    tool = _catalogue_tool(
        datasets=[
            {"id": "imf:weo(1.0.0)", "name": "Case-folded", "url": f"{_URL}-folded"},
            {"id": _URN, "name": _NAME, "url": _URL},
        ]
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert list(sources) == [_URN]
    assert sources[_URN].url == _URL


async def test_a_plain_argument_call_would_lose_the_structured_result() -> None:
    """Why the call is tool-call-shaped: no tool-call id, no `ToolMessage`, no artifact."""
    tool = _catalogue_tool(datasets=[{"id": _URN, "name": _NAME, "url": _URL}])

    plain = await tool.ainvoke({})
    tool_call_shaped = await tool.ainvoke(
        {"name": tool.name, "args": {}, "id": "c1", "type": "tool_call"}
    )

    assert not isinstance(plain, ToolMessage)
    assert isinstance(tool_call_shaped, ToolMessage)
    assert tool_call_shaped.artifact["structured_content"]["datasets"][0]["id"] == _URN


async def test_an_error_status_is_a_failed_call() -> None:
    """This tool keeps the agent's error handling, so an MCP error arrives as a message.

    `ToolException` is what langchain-mcp-adapters raises on an MCP error response, and
    `handle_tool_error` turns it into a `ToolMessage` carrying `status="error"` rather than
    letting it propagate.
    """
    tool = _catalogue_tool(raises=ToolException("the server said no"), handle_tool_error=True)

    with pytest.raises(DatasetMetadataError) as excinfo:
        await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert excinfo.value.kind == KIND_DATASET_CALL_FAILED


async def test_no_structured_result_is_a_failed_call() -> None:
    """MCP sends one only for a tool that declares an output schema, as the contract requires."""
    tool = _catalogue_tool(artifact=None)

    with pytest.raises(DatasetMetadataError) as excinfo:
        await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert excinfo.value.kind == KIND_DATASET_NO_STRUCTURED_RESULT


@pytest.mark.parametrize(
    ("structured", "case"),
    [
        ({"items": [{"id": _URN}]}, "the array is under another key"),
        ({"datasets": {"id": _URN}}, "the datasets value is not an array"),
        ({"datasets": ["IMF:WEO(1.0.0)"]}, "an element is not a record"),
        ([{"id": _URN}], "the answer is an array rather than an object"),
    ],
)
async def test_an_answer_carrying_no_readable_dataset_array_is_a_failed_call(
    structured: Any, case: str
) -> None:
    tool = _catalogue_tool(artifact={"structured_content": structured})

    with pytest.raises(DatasetMetadataError) as excinfo:
        await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert excinfo.value.kind == KIND_DATASET_UNREADABLE_RESULT, case


async def test_a_raising_tool_raises() -> None:
    tool = _catalogue_tool(raises=RuntimeError("the server said no"))

    with pytest.raises(RuntimeError):
        await read_dataset_sources(tool=tool, dataset_ids=[_URN])


async def test_a_record_whose_id_is_not_a_string_is_skipped_rather_than_fatal() -> None:
    """One unreadable record costs that record, never the other datasets' pills."""
    tool = _catalogue_tool(
        datasets=[{"id": 7, "name": "Numbered", "url": _URL}, {"id": _URN, "url": _URL}]
    )

    sources = await read_dataset_sources(tool=tool, dataset_ids=[_URN])

    assert list(sources) == [_URN]
