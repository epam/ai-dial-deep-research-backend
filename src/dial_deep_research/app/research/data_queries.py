"""Data-query records captured from the dataset server's tool results during one research turn.

A `[data_query <id>]` citation opens the cited query in the dataset server's data explorer. The
address of that page is in the tool result's `_meta`, which the MCP adapter drops before a tool
message exists, so `DataQueryCapture` reads each raw result as it passes and keeps what the
citation step and the report review need, keyed by query id. Nothing it keeps reaches a model.

The shapes of the `_meta` payload and of the structured result are defined by the dataset server
and are the same in every deployment, so they are pinned by the models below. Only the `_meta` key
is configured (`data_query_meta_key`). The models read only what a citation uses and ignore every
other field; a record keeps each element whole regardless, so a later feature can read a field
the capture did not know about.

Nothing here logs a URL, a filter value or a query id.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dial_deep_research.app.research.web_urls import is_web_url

logger = logging.getLogger(__name__)

_LENIENT = ConfigDict(extra="ignore", populate_by_name=True)


class FilterValue(BaseModel):
    """One value a filter selects: the code the query used, and its display name."""

    model_config = _LENIENT
    id: str
    name: str | None = None


class QueryFilter(BaseModel):
    """One element of `StructuredQuery.filters`."""

    model_config = _LENIENT
    dimension_id: str = Field(alias="dimensionId")
    dimension_name: str | None = Field(default=None, alias="dimensionName")
    operator: str
    values: list[FilterValue] = []


class RequestedPeriod(BaseModel):
    """The period the query asked for, which is the period its data explorer link opens."""

    model_config = _LENIENT
    start_period: str | None = Field(default=None, alias="startPeriod")
    end_period: str | None = Field(default=None, alias="endPeriod")


class StructuredQuery(BaseModel):
    """One element of `StructuredResult.queries`, or a `CandidateDataset.query`.

    `filters` stays a list of dicts so that each filter is validated on its own: a bad filter
    costs its own card item and nothing else.
    """

    model_config = _LENIENT
    query_id: str = Field(alias="queryId")
    dataset_urn: str | None = Field(default=None, alias="datasetUrn")
    series_count: int | None = Field(default=None, alias="seriesCount")
    filters: list[dict[str, Any]] = []
    requested_period: RequestedPeriod | None = Field(default=None, alias="requestedPeriod")


class CandidateDataset(BaseModel):
    """One element of `candidateDatasets`: the query the server offers to run on that dataset."""

    model_config = _LENIENT
    query: dict[str, Any] | None = None


class StructuredResult(BaseModel):
    """The tool result's `structuredContent`."""

    model_config = _LENIENT
    queries: list[dict[str, Any]] = []
    candidate_datasets: list[CandidateDataset] = Field(default=[], alias="candidateDatasets")


class ClientMetaQuery(BaseModel):
    """One element of `ClientMeta.queries`: where the query opens in the data explorer."""

    model_config = _LENIENT
    query_id: str = Field(alias="queryId")
    data_explorer_url: str | None = Field(default=None, alias="dataExplorerUrl")


class ClientMeta(BaseModel):
    """The payload at `_meta[<data_query_meta_key>]`."""

    model_config = _LENIENT
    queries: list[dict[str, Any]]


class DataQueryRecord(BaseModel):
    """What the turn's tool results reported about one query, as the server sent it.

    `meta` is the query's element of the `_meta` payload and `structured_content` its element of
    the structured result (or a candidate's `query`), each whole, and each `None` when that part
    did not report the id. A record dumps by alias as `{"_meta": ..., "structured_content": ...}`.

    The properties validate on read, so a field the app does not read can never make a record
    unreadable, and an element that fails validation reads as absent: a bad `_meta` element costs
    the explorer link, and a bad structured element costs the dataset, the series count and the
    filter.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    meta: dict[str, Any] | None = Field(default=None, alias="_meta")
    structured_content: dict[str, Any] | None = None

    @property
    def data_explorer_url(self) -> str | None:
        """The address that opens this query in the data explorer, when it is a web URL."""
        meta = _validated(ClientMetaQuery, self.meta)
        url = meta.data_explorer_url if meta is not None else None
        return url if url and is_web_url(url) else None

    @property
    def has_explorer_link(self) -> bool:
        """Whether a citation of this query can become a pill and a References row."""
        return self.data_explorer_url is not None

    @property
    def dataset_urn(self) -> str | None:
        """The URN of the dataset the query ran against, in the spelling the writer saw."""
        query = self._structured_query
        return (query.dataset_urn or None) if query is not None else None

    @property
    def series_count(self) -> int | None:
        query = self._structured_query
        return query.series_count if query is not None else None

    @property
    def returned_data(self) -> bool:
        """Whether the query returned data, which is what makes it citable.

        Independent of the explorer link: a query that returned nothing may still carry one.
        """
        count = self.series_count
        return count is not None and count > 0

    @property
    def filters(self) -> list[QueryFilter]:
        """The query's filters in the order the server reported them, each validated alone."""
        query = self._structured_query
        if query is None:
            return []
        return [
            parsed for raw in query.filters if (parsed := _validated(QueryFilter, raw)) is not None
        ]

    @property
    def requested_period(self) -> RequestedPeriod | None:
        query = self._structured_query
        return query.requested_period if query is not None else None

    @property
    def _structured_query(self) -> StructuredQuery | None:
        return _validated(StructuredQuery, self.structured_content)


def _validated[M: BaseModel](model: type[M], value: dict[str, Any] | None) -> M | None:
    """`value` read as `model`, or `None` when it is absent or does not validate."""
    if value is None:
        return None
    try:
        return model.model_validate(value)
    except ValidationError:
        return None


@dataclass
class DataQueryStore:
    """One turn's captured records, keyed by query id, and how many payloads could not be read.

    Tool calls in one turn run on one event loop, so the dict needs no lock. The report review
    reads it while the turn is still running, which is safe because every tool call has finished
    by the time a report node runs, and records are only ever added or replaced.
    """

    records: dict[str, DataQueryRecord] = field(default_factory=dict)
    unreadable_payloads: int = 0


class DataQueryCapture:
    """A tool-call interceptor that keeps the data-query records of one server's tool results.

    It runs the call first and returns the **same** result object, so what the research agent
    reads is exactly what it would read with no capture at all. Only a successful result from the
    configured server whose `_meta` carries the configured key contributes; any exception while
    reading the payload counts as one unreadable payload and costs that result's records alone.
    """

    def __init__(self, *, server_name: str, meta_key: str, store: DataQueryStore) -> None:
        self._server_name = server_name
        self._meta_key = meta_key
        self._store = store

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
    ) -> MCPToolCallResult:
        result = await handler(request)
        if request.server_name != self._server_name:
            return result
        if not isinstance(result, CallToolResult) or result.isError:
            return result
        meta = result.meta
        if not isinstance(meta, dict) or self._meta_key not in meta:
            return result
        try:
            records = _join_records(
                payload=meta[self._meta_key], structured_content=result.structuredContent
            )
        except Exception:
            self._store.unreadable_payloads += 1
            logger.debug("A tool result carried an unreadable data-query payload in _meta")
            return result
        # A later record replaces an earlier one: a repeated query reports the same id, and the
        # latest report of it is the one the agent read last.
        self._store.records.update(records)
        logger.debug("Captured data-query records from a tool result: records=%d", len(records))
        return result


def _join_records(*, payload: Any, structured_content: Any) -> dict[str, DataQueryRecord]:
    """One record per query id either part reports, joining the two parts' elements by id.

    Raises when the payload is not a `ClientMeta`. A structured result that is not a
    `StructuredResult` is read as absent, so its queries keep their `_meta` elements alone.
    """
    meta_elements = _elements_by_id(ClientMeta.model_validate(payload).queries)
    structured = _validated(StructuredResult, structured_content)
    structured_elements: dict[str, dict[str, Any]] = {}
    if structured is not None:
        # Candidates first, so an id reported both as a query and as a candidate keeps the query.
        structured_elements.update(
            _elements_by_id(
                candidate.query
                for candidate in structured.candidate_datasets
                if candidate.query is not None
            )
        )
        structured_elements.update(_elements_by_id(structured.queries))
    return {
        query_id: DataQueryRecord(
            meta=meta_elements.get(query_id),
            structured_content=structured_elements.get(query_id),
        )
        for query_id in {**meta_elements, **structured_elements}
    }


def _elements_by_id(elements: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each element whose `queryId` is a string, whole, by that id; every other one skipped."""
    return {
        element["queryId"]: element
        for element in elements
        if isinstance(element.get("queryId"), str)
    }
