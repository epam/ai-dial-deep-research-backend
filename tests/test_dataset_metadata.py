"""Calling the list-datasets tool and reading the catalogue it answers with.

The tool is called in an MCP session, as the app calls it, so a result reaches these tests with
its structured content and its `_meta` the way a server sends them.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.types import CallToolResult

from dial_deep_research.app.research.citations import DatasetSource
from dial_deep_research.app.research.dataset_metadata import (
    KIND_DATASET_CALL_FAILED,
    KIND_DATASET_NO_STRUCTURED_RESULT,
    KIND_DATASET_UNREADABLE_RESULT,
    CatalogueTool,
    DatasetMetadataError,
    parse_catalogue,
    read_catalogue,
    select_cited,
)
from tests.mcp_fakes import FakeMcpServer, mcp_error, structured

_URN = "IMF:WEO(1.0.0)"
_NAME = "World Economic Outlook"
_URL = "https://portal.example.org/datasets/imf-weo"
_EXPLORER_URL = "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)"
_TOOL_NAME = "list_datasets"
_KEY = "acme.example.org/client"
_TOOL = CatalogueTool(server_name="datasets", tool_name=_TOOL_NAME, client_meta_key=_KEY)


def _catalogue_tool(
    *,
    datasets: list[dict[str, Any]] | None = None,
    structured_content: Any = None,
    meta: dict[str, Any] | None = None,
    answer: CallToolResult | None = None,
    raises: Exception | None = None,
) -> FakeMcpServer:
    content = structured_content if datasets is None else {"datasets": datasets}

    def list_datasets(_arguments: dict[str, Any]) -> CallToolResult:
        if raises is not None:
            raise raises
        return answer if answer is not None else structured(content, meta=meta)

    return FakeMcpServer({_TOOL_NAME: list_datasets})


async def _read(
    *, tool: FakeMcpServer, dataset_ids: list[str], catalogue_tool: CatalogueTool = _TOOL
) -> dict[str, DatasetSource]:
    """What the dataset server `tool` answers about the cited datasets, called as the app calls."""
    catalogue = await read_catalogue(client=tool.client(), tool=catalogue_tool)
    return select_cited(catalogue, dataset_ids=dataset_ids)


async def test_the_reported_record_is_read_off_the_structured_result() -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "name": _NAME, "url": _URL, "lastUpdated": "2025-04-30"}]
    )

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url == _URL
    assert sources[_URN].name == _NAME
    assert sources[_URN].last_updated == "2025-04-30"


async def test_the_call_carries_no_arguments() -> None:
    """The contract's input is none: the tool answers with the channel's whole catalogue."""
    tool = _catalogue_tool(datasets=[])

    await _read(tool=tool, dataset_ids=[_URN])

    assert tool.calls == [(_TOOL_NAME, {})]
    assert tool.sessions == 1


async def test_one_call_serves_every_cited_dataset() -> None:
    other = "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)"
    tool = _catalogue_tool(
        datasets=[
            {"id": _URN, "name": _NAME, "url": _URL},
            {"id": other, "name": "Primary Commodity Prices", "url": f"{_URL}-pcp"},
            {"id": "IMF:NOT_CITED(1.0.0)", "name": "Not cited", "url": f"{_URL}-nc"},
        ],
    )

    sources = await _read(tool=tool, dataset_ids=[_URN, other])

    assert sorted(sources) == sorted([_URN, other])
    assert len(tool.calls) == 1


async def test_a_record_the_answer_omits_is_absent_rather_than_a_failure() -> None:
    tool = _catalogue_tool(datasets=[{"id": _URN, "name": _NAME, "url": _URL}])

    sources = await _read(tool=tool, dataset_ids=[_URN, "IMF:UNKNOWN(1.0.0)"])

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

    sources = await _read(tool=tool, dataset_ids=[_URN])

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

    sources = await _read(tool=tool, dataset_ids=[_URN])

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

    sources = await _read(tool=tool, dataset_ids=[_URN])

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

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].last_updated is None, case


async def test_a_urn_is_matched_character_for_character() -> None:
    tool = _catalogue_tool(
        datasets=[
            {"id": "imf:weo(1.0.0)", "name": "Case-folded", "url": f"{_URL}-folded"},
            {"id": _URN, "name": _NAME, "url": _URL},
        ]
    )

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert list(sources) == [_URN]
    assert sources[_URN].url == _URL


async def test_an_error_result_is_a_failed_call() -> None:
    tool = _catalogue_tool(answer=mcp_error())

    with pytest.raises(DatasetMetadataError) as excinfo:
        await _read(tool=tool, dataset_ids=[_URN])

    assert excinfo.value.kind == KIND_DATASET_CALL_FAILED


async def test_no_structured_result_is_a_failed_call() -> None:
    """MCP sends one only for a tool that declares an output schema, as the contract requires."""
    tool = _catalogue_tool(structured_content=None)

    with pytest.raises(DatasetMetadataError) as excinfo:
        await _read(tool=tool, dataset_ids=[_URN])

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
    tool = _catalogue_tool(structured_content=structured)

    with pytest.raises(DatasetMetadataError) as excinfo:
        await _read(tool=tool, dataset_ids=[_URN])

    assert excinfo.value.kind == KIND_DATASET_UNREADABLE_RESULT, case


async def test_a_raising_tool_raises() -> None:
    tool = _catalogue_tool(raises=RuntimeError("the server said no"))

    with pytest.raises(RuntimeError):
        await _read(tool=tool, dataset_ids=[_URN])


async def test_a_record_whose_id_is_not_a_string_is_skipped_rather_than_fatal() -> None:
    """One unreadable record costs that record, never the other datasets' pills."""
    tool = _catalogue_tool(
        datasets=[{"id": 7, "name": "Numbered", "url": _URL}, {"id": _URN, "url": _URL}]
    )

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert list(sources) == [_URN]


def test_the_parser_reads_a_structured_result_given_as_a_dict() -> None:
    """The turn-start fetch reads the MCP result directly and hands the parser a dict."""
    sources = parse_catalogue({"datasets": [{"id": _URN, "name": _NAME, "url": _URL}]})

    assert sources[_URN].name == _NAME
    assert sources[_URN].url == _URL
    assert sources[_URN].raw_fields == {"id": _URN, "name": _NAME, "url": _URL}


@pytest.mark.parametrize("structured", [None, [], {"datasets": "none"}, {"items": []}])
def test_the_parser_refuses_a_result_without_a_datasets_array(structured: Any) -> None:
    with pytest.raises(DatasetMetadataError) as excinfo:
        parse_catalogue(structured)
    assert excinfo.value.kind == KIND_DATASET_UNREADABLE_RESULT


# --- the explorer links in `_meta` ---------------------------------------------------------------


def _links(*elements: Any) -> dict[str, Any]:
    return {_KEY: {"datasets": list(elements)}}


async def test_the_explorer_link_is_the_url_a_dataset_opens() -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "name": _NAME, "url": _URL}],
        meta=_links({"id": _URN, "dataExplorerUrl": _EXPLORER_URL, "citationUrl": f"{_URL}-cited"}),
    )

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url == _EXPLORER_URL
    # The row's columns read the structured record, which the payload does not touch.
    assert sources[_URN].raw_fields == {"id": _URN, "name": _NAME, "url": _URL}


@pytest.mark.parametrize(
    ("meta", "case"),
    [
        (None, "the result carries no _meta"),
        ({"other.example.org/client": {"datasets": [{"id": _URN}]}}, "the key is another one"),
        (_links({"id": "IMF:OTHER(1.0.0)", "dataExplorerUrl": _EXPLORER_URL}), "another id"),
        (_links({"id": _URN}), "the element carries no link"),
        (_links({"id": _URN, "dataExplorerUrl": None}), "the link is null"),
        (_links({"id": _URN, "dataExplorerUrl": 7}), "the link is not a string"),
        (_links({"id": _URN, "dataExplorerUrl": "files/b/explorer.html"}), "the link is relative"),
        (_links("not a record"), "the element is not a record"),
        ({_KEY: {"datasets": "none"}}, "the datasets value is not an array"),
        ({_KEY: ["a list"]}, "the payload is not an object"),
        ({_KEY: {"queries": []}}, "the payload is a data-query one"),
    ],
)
async def test_without_a_usable_explorer_link_a_dataset_opens_its_page(
    meta: dict[str, Any] | None, case: str
) -> None:
    """Neither a missing nor an unreadable payload fails the call: it costs the links alone."""
    tool = _catalogue_tool(datasets=[{"id": _URN, "name": _NAME, "url": _URL}], meta=meta)

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url == _URL, case


async def test_an_explorer_link_alone_makes_a_dataset_openable() -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "name": _NAME}],
        meta=_links({"id": _URN, "dataExplorerUrl": _EXPLORER_URL}),
    )

    sources = await _read(tool=tool, dataset_ids=[_URN])

    assert sources[_URN].url == _EXPLORER_URL


async def test_an_explorer_link_is_matched_to_its_record_by_id_not_by_position() -> None:
    other = "IMF:PRIMARY_COMMODITY_PRICES(1.0.0)"
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "url": _URL}, {"id": other, "url": f"{_URL}-pcp"}],
        meta=_links({"id": other, "dataExplorerUrl": f"{_EXPLORER_URL}-pcp"}),
    )

    sources = await _read(tool=tool, dataset_ids=[_URN, other])

    assert sources[_URN].url == _URL
    assert sources[other].url == f"{_EXPLORER_URL}-pcp"


async def test_a_tool_with_no_client_meta_key_reads_no_links() -> None:
    tool = _catalogue_tool(
        datasets=[{"id": _URN, "url": _URL}],
        meta=_links({"id": _URN, "dataExplorerUrl": _EXPLORER_URL}),
    )

    sources = await _read(
        tool=tool,
        dataset_ids=[_URN],
        catalogue_tool=CatalogueTool(server_name="datasets", tool_name=_TOOL_NAME),
    )

    assert sources[_URN].url == _URL


def test_the_parser_reads_the_links_from_the_payload_it_is_given() -> None:
    sources = parse_catalogue(
        {"datasets": [{"id": _URN, "url": _URL}]},
        client_payload={"datasets": [{"id": _URN, "dataExplorerUrl": _EXPLORER_URL}]},
    )

    assert sources[_URN].url == _EXPLORER_URL
