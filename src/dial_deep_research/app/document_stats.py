"""The documents part of the data-sources fetch: the listing, the statistics, and the rendering.

The list-documents tool is called page by page with `{"offset": <n>, "limit": <page_size>}`. The
first page carries the collection's `total_count` as well as its first documents; while fewer
documents than that were received, the next page is requested at the number received so far, one
page after another, for at most `MAX_DOCUMENT_PAGES` pages. Each page gets up to three attempts. A
page that is not obtained, a page that adds no document before the total is reached, or a total
that the page cap does not reach makes the listing incomplete. An incomplete listing renders its
failure text rather than figures: partial figures would understate the collection, and the models
would read them as complete (see the data-sources-discovery capability).

From a complete listing the statistics are computed from each document's metadata: the count,
the earliest and latest valid publication dates, and, when a type key is configured, the same
three figures per type. A malformed date or type is ignored rather than failing the listing.

The log records carry counts, offsets and failure kinds only: a document's metadata is the
client's content.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

from dial_deep_research.app.data_source_calls import (
    InvalidResultError,
    call_with_attempts,
    of_structured,
)
from dial_deep_research.app_properties import MAX_DOCUMENT_PAGES, DocumentStats

logger = logging.getLogger(__name__)

DOCUMENT_STATS_HEADING = "Document statistics:"
DOCUMENTS_LIST_FAILED_TEXT = "failed to obtain list of documents"

# What the WARNING says ended a listing whose page returned successfully but added nothing.
KIND_EMPTY_PAGE = "empty_page"
# What the WARNING says ended a listing that reached `MAX_DOCUMENT_PAGES` before the total.
KIND_PAGE_LIMIT = "page_limit"


class _Page(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_count: StrictInt
    results: list[dict[str, Any]]


def read_page(structured: Any) -> _Page:
    """A list-documents answer, once its shape is checked.

    Raises `InvalidResultError` for an answer without an integer `total_count` and a `results`
    array of objects.
    """
    try:
        return _Page.model_validate(structured)
    except ValidationError as error:
        raise InvalidResultError() from error


class DateRange(BaseModel):
    """The earliest and the latest valid publication date of a set of documents."""

    earliest: date
    latest: date


class Aggregate(BaseModel):
    """How many documents a set holds, and which dates they cover; `dates` is `None` when no
    document of the set has a valid date."""

    count: int
    dates: DateRange | None = None


class DocumentStatistics(BaseModel):
    """The figures of a complete listing. `by_type` maps each type value to its figures, and is
    `None` when no type key is configured."""

    overall: Aggregate
    by_type: dict[str, Aggregate] | None = None


class DocumentStatsFetch(BaseModel):
    """The documents part's result. `text` is the rendered block, or the failure text when the
    listing was incomplete; `statistics` is `None` then."""

    text: str
    statistics: DocumentStatistics | None = None


def parse_date(value: Any) -> date | None:
    """The calendar date of an ISO 8601 date, or date and time, string; `None` for anything else.

    `datetime.fromisoformat` accepts both shapes, a date alone giving midnight, so the date part
    is the value's calendar date either way.
    """
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _aggregate(dates: list[date | None]) -> Aggregate:
    valid = [value for value in dates if value is not None]
    if not valid:
        return Aggregate(count=len(dates))
    return Aggregate(count=len(dates), dates=DateRange(earliest=min(valid), latest=max(valid)))


def compute_document_stats(
    documents: Iterable[dict[str, Any]], *, date_key: str, type_key: str | None
) -> DocumentStatistics:
    """The statistics of the listed documents, read from each document's metadata fields.

    A type groups the documents whose value under `type_key` is exactly that string, whitespace
    and case included; a document whose value is not a string belongs to no group.
    """
    dated = [(document, parse_date(document.get(date_key))) for document in documents]
    overall = _aggregate([parsed for _, parsed in dated])
    if type_key is None:
        return DocumentStatistics(overall=overall)
    groups: dict[str, list[date | None]] = {}
    for document, parsed in dated:
        doc_type = document.get(type_key)
        if isinstance(doc_type, str):
            groups.setdefault(doc_type, []).append(parsed)
    return DocumentStatistics(
        overall=overall,
        by_type={name: _aggregate(groups[name]) for name in sorted(groups)},
    )


def _describe(aggregate: Aggregate) -> str:
    noun = "document" if aggregate.count == 1 else "documents"
    if aggregate.dates is None:
        return f"{aggregate.count} {noun}, publication dates unknown"
    return (
        f"{aggregate.count} {noun}, published from {aggregate.dates.earliest.isoformat()}"
        f" to {aggregate.dates.latest.isoformat()}"
    )


def render_document_stats(statistics: DocumentStatistics, *, type_key: str | None) -> str:
    """`Document statistics:`, the overall line, and, when types were grouped, the line
    `By <type_key>:` and one line per type in the order `by_type` holds them.

    A type is written as a JSON string, so a whitespace-only type stays visible in its quotes.
    """
    lines = [DOCUMENT_STATS_HEADING, f"{_describe(statistics.overall)}."]
    if statistics.by_type:
        lines.append(f"By {type_key}:")
        lines.extend(
            f"- {json.dumps(name, ensure_ascii=False)}: {_describe(aggregate)}"
            for name, aggregate in statistics.by_type.items()
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class _Listing:
    """What the pages returned: the documents, or `None` when the listing is incomplete.

    `received` counts the documents the obtained pages carried, an incomplete listing's included.
    A dataclass rather than a model, so the documents `read_page` already validated are not
    validated and copied again.
    """

    documents: list[dict[str, Any]] | None
    received: int
    total_count: int | None
    pages: int
    attempts: int


async def _list_documents(
    client: MultiServerMCPClient, *, server_name: str, config: DocumentStats
) -> _Listing:
    """Request pages one after another until `total_count` documents were received, or until a
    page is not obtained, a page adds no document, or `MAX_DOCUMENT_PAGES` pages were requested,
    which makes the listing incomplete."""
    documents: list[dict[str, Any]] = []
    total_count: int | None = None
    pages = 0
    attempts = 0

    def incomplete(*, kind: str | None) -> _Listing:
        _log_incomplete(server_name=server_name, offset=len(documents), kind=kind)
        return _Listing(
            documents=None,
            received=len(documents),
            total_count=total_count,
            pages=pages,
            attempts=attempts,
        )

    while total_count is None or len(documents) < total_count:
        if pages == MAX_DOCUMENT_PAGES:
            return incomplete(kind=KIND_PAGE_LIMIT)
        offset = len(documents)
        page = await call_with_attempts(
            client,
            server_name=server_name,
            tool_name=config.list_documents_tool,
            arguments={"offset": offset, "limit": config.page_size},
            read=of_structured(read_page),
        )
        attempts += page.attempts
        if page.value is None:
            return incomplete(kind=page.failure_kind)
        pages += 1
        if total_count is None:
            total_count = page.value.total_count
        if not page.value.results and offset < total_count:
            # Requesting the same offset again would return the same empty page.
            return incomplete(kind=KIND_EMPTY_PAGE)
        documents.extend(page.value.results)
    return _Listing(
        documents=documents,
        received=len(documents),
        total_count=total_count,
        pages=pages,
        attempts=attempts,
    )


async def fetch_document_stats(
    client: MultiServerMCPClient, *, server_name: str, config: DocumentStats
) -> DocumentStatsFetch:
    """List the documents and render their statistics. No failure raises: an incomplete listing
    gives the failure text and no statistics. Cancellation propagates."""
    started_at = time.monotonic()
    listing = await _list_documents(client, server_name=server_name, config=config)
    statistics = (
        compute_document_stats(
            listing.documents,
            date_key=config.document_date_key,
            type_key=config.document_type_key,
        )
        if listing.documents is not None
        else None
    )
    logger.info(
        "Documents fetched: server=%s pages=%d attempts=%d documents=%d total_count=%s"
        " groups=%d complete=%s duration=%.1fs",
        server_name,
        listing.pages,
        listing.attempts,
        listing.received,
        listing.total_count,
        len(statistics.by_type or {}) if statistics is not None else 0,
        statistics is not None,
        time.monotonic() - started_at,
    )
    if statistics is None:
        return DocumentStatsFetch(text=f"{DOCUMENT_STATS_HEADING}\n{DOCUMENTS_LIST_FAILED_TEXT}")
    return DocumentStatsFetch(
        text=render_document_stats(statistics, type_key=config.document_type_key),
        statistics=statistics,
    )


def _log_incomplete(*, server_name: str, offset: int, kind: str | None) -> None:
    logger.warning(
        "Document listing incomplete: server=%s offset=%d failure=%s",
        server_name,
        offset,
        kind,
    )
