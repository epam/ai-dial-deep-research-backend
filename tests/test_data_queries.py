"""The data-query capture keeps each query's `_meta` and structured elements, joined by query id,
and never changes the tool result the research agent reads."""

from __future__ import annotations

from typing import Any

from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from mcp.types import CallToolResult, TextContent

from dial_deep_research.app.research.data_queries import (
    DataQueryCapture,
    DataQueryRecord,
    DataQueryStore,
)

_KEY = "acme.example.org/client"
_SERVER = "datasets"
_URL_1 = "https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE+US.GDP"
_URL_2 = "https://portal.example.org/explorer?urn=IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"


def _result(
    *,
    meta: dict[str, Any] | None = None,
    structured: dict[str, Any] | None = None,
    is_error: bool = False,
) -> CallToolResult:
    return CallToolResult.model_validate(
        {
            "content": [TextContent(type="text", text="{}")],
            "structuredContent": structured,
            "isError": is_error,
            "_meta": meta,
        }
    )


async def _capture(
    result: CallToolResult, *, store: DataQueryStore | None = None, server_name: str = _SERVER
) -> tuple[DataQueryStore, MCPToolCallResult]:
    store = store if store is not None else DataQueryStore()
    capture = DataQueryCapture(server_name=_SERVER, meta_key=_KEY, store=store)

    async def handler(_request: MCPToolCallRequest) -> MCPToolCallResult:
        return result

    request = MCPToolCallRequest(name="query_data", args={}, server_name=server_name)
    returned = await capture(request, handler)
    return store, returned


def _two_queries() -> CallToolResult:
    return _result(
        meta={
            _KEY: {
                "status": "ok",
                "version": 3,
                "queries": [
                    {"queryId": "dq_0000000002", "dataExplorerUrl": _URL_2},
                    {"queryId": "dq_0000000001", "dataExplorerUrl": _URL_1},
                ],
            }
        },
        structured={
            "queries": [
                {
                    "queryId": "dq_0000000001",
                    "datasetUrn": "IMF:WEO(1.0.0)",
                    "seriesCount": 2,
                    "querySummary": "Real GDP growth",
                    "datasetName": "World Economic Outlook",
                    "factualPeriod": {"startPeriod": "2020"},
                },
                {
                    "queryId": "dq_0000000002",
                    "datasetUrn": "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)",
                    "seriesCount": 5,
                },
            ]
        },
    )


async def test_two_queries_listed_in_different_orders_are_joined_by_id() -> None:
    store, _ = await _capture(_two_queries())

    first = store.records["dq_0000000001"]
    second = store.records["dq_0000000002"]
    assert first.data_explorer_url == _URL_1
    assert first.dataset_urn == "IMF:WEO(1.0.0)"
    assert first.series_count == 2
    assert second.data_explorer_url == _URL_2
    assert second.dataset_urn == "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"


async def test_a_record_keeps_both_elements_whole() -> None:
    store, _ = await _capture(_two_queries())

    dumped = store.records["dq_0000000001"].model_dump(by_alias=True)
    assert set(dumped) == {"_meta", "structured_content"}
    assert dumped["_meta"] == {"queryId": "dq_0000000001", "dataExplorerUrl": _URL_1}
    assert dumped["structured_content"]["querySummary"] == "Real GDP growth"
    assert dumped["structured_content"]["datasetName"] == "World Economic Outlook"
    assert dumped["structured_content"]["factualPeriod"] == {"startPeriod": "2020"}


async def test_a_constructed_query_is_kept_without_a_link() -> None:
    store, _ = await _capture(
        _result(
            meta={_KEY: {"queries": [{"queryId": "dq_0123abcd45", "urn": "IMF:WEO(1.0.0)"}]}},
            structured={"queries": [{"queryId": "dq_0123abcd45", "datasetUrn": "IMF:WEO(1.0.0)"}]},
        )
    )

    record = store.records["dq_0123abcd45"]
    assert record.has_explorer_link is False
    assert record.returned_data is False


async def test_candidate_queries_are_kept_with_only_structured_content() -> None:
    store, _ = await _capture(
        _result(
            meta={_KEY: {"queries": []}},
            structured={
                "candidateDatasets": [
                    {"query": {"queryId": "dq_000000000a", "datasetUrn": "IMF:WEO(1.0.0)"}},
                    {"query": {"queryId": "dq_000000000b", "datasetUrn": "IMF:WEO(2.0.0)"}},
                    {"datasetUrn": "IMF:WEO(3.0.0)"},
                ]
            },
        )
    )

    assert set(store.records) == {"dq_000000000a", "dq_000000000b"}
    for record in store.records.values():
        assert record.meta is None
        assert record.structured_content is not None
        assert record.has_explorer_link is False
        assert record.returned_data is False


async def test_a_query_only_in_the_structured_result_is_still_a_record() -> None:
    store, _ = await _capture(
        _result(
            meta={_KEY: {"queries": []}},
            structured={"queries": [{"queryId": "dq_0123abcd45", "seriesCount": 3}]},
        )
    )

    record = store.records["dq_0123abcd45"]
    assert record.meta is None
    assert record.returned_data is True
    assert record.has_explorer_link is False


async def test_a_result_under_another_key_contributes_nothing() -> None:
    store, _ = await _capture(
        _result(
            meta={"other.example.org/client": {"queries": [{"queryId": "dq_1"}]}},
            structured={"queries": [{"queryId": "dq_1", "seriesCount": 1}]},
        )
    )

    assert store.records == {}
    assert store.unreadable_payloads == 0


async def test_a_result_without_meta_contributes_nothing() -> None:
    store, _ = await _capture(
        _result(structured={"queries": [{"queryId": "dq_1", "seriesCount": 1}]})
    )

    assert store.records == {}


async def test_another_servers_result_contributes_nothing() -> None:
    store, _ = await _capture(_two_queries(), server_name="documents")

    assert store.records == {}


async def test_an_unreadable_payload_costs_only_its_own_records() -> None:
    store, _ = await _capture(_two_queries())
    await _capture(_result(meta={_KEY: {"queries": "not a list"}}), store=store)

    assert store.unreadable_payloads == 1
    assert set(store.records) == {"dq_0000000001", "dq_0000000002"}


async def test_an_error_result_is_skipped() -> None:
    result = _two_queries()
    result.isError = True
    store, returned = await _capture(result)

    assert store.records == {}
    assert returned is result


async def test_the_returned_result_is_the_same_object_unchanged() -> None:
    result = _two_queries()
    before = result.model_dump(by_alias=True)

    _, returned = await _capture(result)

    assert returned is result
    assert result.model_dump(by_alias=True) == before


async def test_a_later_record_replaces_an_earlier_one() -> None:
    store, _ = await _capture(
        _result(meta={_KEY: {"queries": [{"queryId": "dq_1"}]}}),
    )
    await _capture(
        _result(meta={_KEY: {"queries": [{"queryId": "dq_1", "dataExplorerUrl": _URL_1}]}}),
        store=store,
    )

    assert store.records["dq_1"].data_explorer_url == _URL_1


async def test_a_missing_structured_result_keeps_the_link() -> None:
    store, _ = await _capture(
        _result(meta={_KEY: {"queries": [{"queryId": "dq_1", "dataExplorerUrl": _URL_1}]}})
    )

    record = store.records["dq_1"]
    assert record.has_explorer_link is True
    assert record.dataset_urn is None
    assert record.filters == []


def test_a_relative_link_is_not_an_explorer_link() -> None:
    record = DataQueryRecord.model_validate(
        {"_meta": {"queryId": "dq_1", "dataExplorerUrl": "explorer?urn=IMF:WEO(1.0.0)"}}
    )

    assert record.has_explorer_link is False


def test_a_bad_filter_costs_only_its_own_item() -> None:
    record = DataQueryRecord(
        structured_content={
            "queryId": "dq_1",
            "filters": [
                {"dimensionId": "COUNTRY", "operator": "in", "values": [{"id": "DE"}]},
                {"dimensionId": "SERIES", "values": "not a list"},
            ],
        }
    )

    assert [f.dimension_id for f in record.filters] == ["COUNTRY"]


def test_a_non_integer_series_count_means_no_data() -> None:
    record = DataQueryRecord(structured_content={"queryId": "dq_1", "seriesCount": "many"})

    assert record.returned_data is False
    assert record.dataset_urn is None
