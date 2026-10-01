"""The documents part of the data-sources fetch: paging, statistics, rendering and log records."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from dial_deep_research.app import data_source_calls, data_sources, document_stats
from dial_deep_research.app.data_sources import fetch_data_sources, join_data_sources
from dial_deep_research.app.document_stats import (
    compute_document_stats,
    fetch_document_stats,
    parse_date,
    render_document_stats,
)
from dial_deep_research.app_properties import (
    MAX_DOCUMENT_PAGES,
    ApplicationProperties,
    DocumentStats,
)
from tests.mcp_fakes import FakeMcpServer, structured

_TOOL = "list_documents"
_DATE = "publication_date"
_TYPE = "publication_type"
_FAILED_BLOCK = "Document statistics:\nfailed to obtain list of documents"


def _config(**overrides: Any) -> DocumentStats:
    return DocumentStats.model_validate(
        {"list_documents_tool": _TOOL, "document_date_key": _DATE, **overrides}
    )


def _document(number: int, *, date: Any = "2024-01-10", doc_type: Any = "Newsletter") -> dict:
    document: dict[str, Any] = {"id": number, "title": f"Market Outlook {number}.pdf"}
    if date is not None:
        document[_DATE] = date
    if doc_type is not None:
        document[_TYPE] = doc_type
    return document


def _collection(documents: list[dict[str, Any]]) -> Any:
    """A handler answering each page of `documents` as the Generic RAG list tool does."""

    def handler(args: dict[str, Any]) -> Any:
        offset, limit = args["offset"], args["limit"]
        return structured(
            {
                "total_count": len(documents),
                "offset": offset,
                "limit": limit,
                "results": documents[offset : offset + limit],
            }
        )

    return handler


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(data_source_calls, "sleep", sleep)


async def _fetch(fake: FakeMcpServer, **overrides: Any) -> document_stats.DocumentStatsFetch:
    return await fetch_document_stats(
        fake.client(), server_name="documents", config=_config(**overrides)
    )


# --- paging --------------------------------------------------------------------------------------


async def test_one_page_covers_the_collection() -> None:
    fake = FakeMcpServer({_TOOL: _collection([_document(n) for n in range(40)])})

    fetched = await _fetch(fake)

    assert fake.calls == [(_TOOL, {"offset": 0, "limit": 1000})]
    assert fetched.statistics is not None
    assert fetched.statistics.overall.count == 40


async def test_a_larger_collection_is_listed_page_after_page() -> None:
    in_flight = 0
    peak = 0
    pages = _collection([_document(n) for n in range(250)])

    async def slow(args: dict[str, Any]) -> Any:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return pages(args)

    fake = FakeMcpServer({_TOOL: slow})

    fetched = await _fetch(fake, page_size=100)

    assert fake.calls_of(_TOOL) == [
        {"offset": 0, "limit": 100},
        {"offset": 100, "limit": 100},
        {"offset": 200, "limit": 100},
    ]
    assert peak == 1
    assert fetched.statistics is not None
    assert fetched.statistics.overall.count == 250


async def test_the_next_offset_is_the_number_received() -> None:
    """A server returning fewer results than the limit is paged from where it stopped."""
    documents = [_document(n) for n in range(5)]

    def capped(args: dict[str, Any]) -> Any:
        offset = args["offset"]
        return structured({"total_count": 5, "results": documents[offset : offset + 2]})

    fake = FakeMcpServer({_TOOL: capped})

    fetched = await _fetch(fake, page_size=10)

    assert [call["offset"] for call in fake.calls_of(_TOOL)] == [0, 2, 4]
    assert fetched.text is not None


async def test_a_transient_page_failure_is_retried() -> None:
    pages = _collection([_document(n) for n in range(150)])
    second_page_calls = 0

    def handler(args: dict[str, Any]) -> Any:
        nonlocal second_page_calls
        if args["offset"] == 100:
            second_page_calls += 1
            if second_page_calls == 1:
                raise RuntimeError("HTTP 502 from the gateway")
        return pages(args)

    fake = FakeMcpServer({_TOOL: handler})

    fetched = await _fetch(fake, page_size=100)

    assert len(fake.calls_of(_TOOL)) == 3
    assert fetched.text is not None


async def test_a_page_that_fails_three_times_gives_the_failure_text() -> None:
    pages = _collection([_document(n) for n in range(250)])

    def handler(args: dict[str, Any]) -> Any:
        if args["offset"] == 100:
            raise RuntimeError("HTTP 502 from the gateway")
        return pages(args)

    fake = FakeMcpServer({_TOOL: handler})

    fetched = await _fetch(fake, page_size=100)

    assert [call["offset"] for call in fake.calls_of(_TOOL)] == [0, 100, 100, 100]
    assert fetched.text == _FAILED_BLOCK
    assert fetched.statistics is None


async def test_an_empty_page_ends_the_listing() -> None:
    documents = [_document(n) for n in range(100)]

    def handler(args: dict[str, Any]) -> Any:
        offset = args["offset"]
        return structured({"total_count": 250, "results": documents[offset : offset + 100]})

    fake = FakeMcpServer({_TOOL: handler})

    fetched = await _fetch(fake, page_size=100)

    assert len(fake.calls_of(_TOOL)) == 2
    assert fetched.text == _FAILED_BLOCK


@pytest.mark.parametrize(
    "answer",
    [
        {"results": []},
        {"total_count": "3", "results": []},
        {"total_count": 3, "results": "none"},
        {"total_count": 3, "results": [1, 2, 3]},
        [1, 2],
    ],
)
async def test_an_answer_without_the_expected_shape_is_a_failed_attempt(answer: Any) -> None:
    fake = FakeMcpServer({_TOOL: lambda _args: structured(answer)})

    fetched = await _fetch(fake)

    assert len(fake.calls_of(_TOOL)) == 3
    assert fetched.text == _FAILED_BLOCK


async def test_a_total_beyond_the_page_cap_ends_the_listing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeMcpServer(
        {_TOOL: _collection([_document(n) for n in range(MAX_DOCUMENT_PAGES + 5)])}
    )

    with caplog.at_level(logging.INFO, logger=document_stats.__name__):
        fetched = await _fetch(fake, page_size=1)

    assert len(fake.calls_of(_TOOL)) == MAX_DOCUMENT_PAGES
    assert fetched.text == _FAILED_BLOCK
    warning, _info = caplog.records
    assert f"offset={MAX_DOCUMENT_PAGES} failure=page_limit" in warning.getMessage()


async def test_a_total_the_page_cap_reaches_is_listed() -> None:
    fake = FakeMcpServer({_TOOL: _collection([_document(n) for n in range(MAX_DOCUMENT_PAGES)])})

    fetched = await _fetch(fake, page_size=1)

    assert len(fake.calls_of(_TOOL)) == MAX_DOCUMENT_PAGES
    assert fetched.statistics is not None
    assert fetched.statistics.overall.count == MAX_DOCUMENT_PAGES


async def test_a_cancelled_listing_propagates() -> None:
    async def never(_args: dict[str, Any]) -> Any:
        await asyncio.sleep(10)

    fake = FakeMcpServer({_TOOL: never})
    task = asyncio.create_task(_fetch(fake))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(fake.calls_of(_TOOL)) == 1


# --- statistics ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "parsed"),
    [
        ("2025-04-30", "2025-04-30"),
        ("2025-04-30T09:00:00", "2025-04-30"),
        ("2025-04-30T23:30:00+02:00", "2025-04-30"),
        ("May 2024", None),
        ("", None),
        (20250430, None),
        (None, None),
    ],
)
def test_a_date_is_valid_only_as_an_iso_string(value: Any, parsed: str | None) -> None:
    result = parse_date(value)
    assert (result.isoformat() if result is not None else None) == parsed


def test_a_malformed_date_is_ignored_and_the_document_still_counts() -> None:
    documents = [_document(1), _document(2, date="May 2024"), _document(3, date=None)]

    statistics = compute_document_stats(documents, date_key=_DATE, type_key=None)

    assert statistics.overall.count == 3
    assert statistics.overall.dates is not None
    assert statistics.overall.dates.earliest.isoformat() == "2024-01-10"
    assert statistics.overall.dates.latest.isoformat() == "2024-01-10"
    assert statistics.by_type is None


def test_types_are_grouped_exactly() -> None:
    documents = [
        _document(1, doc_type="Annual report"),
        _document(2, doc_type=" "),
        _document(3, doc_type="annual report"),
        _document(4, doc_type="Annual report"),
    ]

    statistics = compute_document_stats(documents, date_key=_DATE, type_key=_TYPE)

    assert statistics.by_type is not None
    assert {name: group.count for name, group in statistics.by_type.items()} == {
        " ": 1,
        "Annual report": 2,
        "annual report": 1,
    }


def test_a_document_without_a_usable_type_counts_only_overall() -> None:
    documents = [_document(n) for n in range(8)]
    documents += [_document(8, doc_type=None), _document(9, doc_type=["Annual report"])]

    statistics = compute_document_stats(documents, date_key=_DATE, type_key=_TYPE)

    assert statistics.overall.count == 10
    assert statistics.by_type is not None
    assert {name: group.count for name, group in statistics.by_type.items()} == {"Newsletter": 8}


# --- rendering -----------------------------------------------------------------------------------


def test_a_collection_with_types_is_rendered_per_type() -> None:
    documents = [
        _document(1, date="2024-06-10"),
        _document(2, date="2024-01-10"),
        _document(3, date=None, doc_type="Annual report"),
    ]
    statistics = compute_document_stats(documents, date_key=_DATE, type_key=_TYPE)

    assert render_document_stats(statistics, type_key=_TYPE) == (
        "Document statistics:\n"
        "3 documents, published from 2024-01-10 to 2024-06-10.\n"
        "By publication_type:\n"
        '- "Annual report": 1 document, publication dates unknown\n'
        '- "Newsletter": 2 documents, published from 2024-01-10 to 2024-06-10'
    )


def test_a_type_is_written_as_a_json_string() -> None:
    documents = [_document(1, doc_type=" "), _document(2, doc_type='Bulletin "Q1" — Kraków')]
    statistics = compute_document_stats(documents, date_key=_DATE, type_key=_TYPE)

    rendered = render_document_stats(statistics, type_key=_TYPE)

    assert '- " ": 1 document, published from 2024-01-10 to 2024-01-10' in rendered
    assert '- "Bulletin \\"Q1\\" — Kraków": 1 document' in rendered


def test_a_collection_without_a_type_key_has_no_by_line() -> None:
    statistics = compute_document_stats(
        [_document(n) for n in range(40)], date_key=_DATE, type_key=None
    )

    assert render_document_stats(statistics, type_key=None) == (
        "Document statistics:\n40 documents, published from 2024-01-10 to 2024-01-10."
    )


def test_no_group_means_no_by_line() -> None:
    statistics = compute_document_stats(
        [_document(1, doc_type=None)], date_key=_DATE, type_key=_TYPE
    )

    assert render_document_stats(statistics, type_key=_TYPE) == (
        "Document statistics:\n1 document, published from 2024-01-10 to 2024-01-10."
    )


async def test_an_empty_collection() -> None:
    fake = FakeMcpServer({_TOOL: _collection([])})

    fetched = await _fetch(fake, document_type_key=_TYPE)

    assert fake.calls == [(_TOOL, {"offset": 0, "limit": 1000})]
    assert fetched.text == "Document statistics:\n0 documents, publication dates unknown."


# --- log records ---------------------------------------------------------------------------------


async def test_a_complete_fetch_logs_one_info_event_and_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    documents = [_document(n, doc_type=f"Type {n % 4}") for n in range(250)]
    fake = FakeMcpServer({_TOOL: _collection(documents)})

    with caplog.at_level(logging.INFO, logger=document_stats.__name__):
        await _fetch(fake, page_size=100, document_type_key=_TYPE)

    [record] = caplog.records
    assert record.levelno == logging.INFO
    assert (
        "server=documents pages=3 attempts=3 documents=250 total_count=250 groups=4 complete=True"
        in record.getMessage()
    )


async def test_a_failed_page_is_logged_by_its_offset_and_names_no_document(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pages = _collection([_document(n) for n in range(250)])

    def handler(args: dict[str, Any]) -> Any:
        if args["offset"] == 100:
            raise RuntimeError("HTTP 502 from the gateway")
        return pages(args)

    fake = FakeMcpServer({_TOOL: handler})

    with caplog.at_level(logging.INFO, logger=document_stats.__name__):
        await _fetch(fake, page_size=100, document_type_key=_TYPE)

    warning, info = caplog.records
    assert warning.levelno == logging.WARNING
    assert "server=documents offset=100 failure=RuntimeError" in warning.getMessage()
    assert "pages=1 attempts=4 documents=100 total_count=250" in info.getMessage()
    assert "complete=False" in info.getMessage()
    for record in caplog.records:
        assert "Market Outlook" not in record.getMessage()
        assert "Newsletter" not in record.getMessage()
        assert "2024-01-10" not in record.getMessage()


async def test_a_failed_first_page_logs_an_absent_total(caplog: pytest.LogCaptureFixture) -> None:
    def down(_args: dict[str, Any]) -> Any:
        raise RuntimeError("HTTP 502 from the gateway")

    fake = FakeMcpServer({_TOOL: down})

    with caplog.at_level(logging.INFO, logger=document_stats.__name__):
        await _fetch(fake)

    assert "documents=0 total_count=None" in caplog.records[-1].getMessage()


async def test_an_empty_page_is_logged_as_such(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeMcpServer({_TOOL: lambda _args: structured({"total_count": 3, "results": []})})

    with caplog.at_level(logging.WARNING, logger=document_stats.__name__):
        await _fetch(fake)

    assert "offset=0 failure=empty_page" in caplog.records[0].getMessage()


# --- the data-sources string ---------------------------------------------------------------------


def test_the_parts_are_joined_in_order_and_absent_parts_leave_nothing() -> None:
    assert join_data_sources(
        document_stats="S",
        documents_description="D",
        datasets="L",
        datasets_description="E",
        glossary="G",
    ) == (
        "S\n\n<documents_description>\nD\n</documents_description>\n\nL\n\n"
        "<datasets_description>\nE\n</datasets_description>\n\nG"
    )
    assert join_data_sources(document_stats="S", datasets="L") == "S\n\nL"


def test_a_descriptions_headings_stay_inside_its_tag() -> None:
    description = "## Publication types\n\n### Annual report\n\nOne issue a year.\n\n### Newsletter"

    assert join_data_sources(documents_description=description, datasets="Datasets:\n[]") == (
        f"<documents_description>\n{description}\n</documents_description>\n\nDatasets:\n[]"
    )


_DOCUMENT_SERVER: dict[str, Any] = {
    "server_name": "documents",
    "server_type": "generic_rag",
    "deployment_id": "rag-mcp",
    "description": "## Publications",
    "file_sharing_tool": "get_citation_url",
    "document_metadata_resource": "documents://metadata/{document_ids}",
    "document_title_key": "publication_title",
    "references_table": {"title": "Documents", "columns": [{"heading": "T", "key": "t"}]},
}

_DATASET_SERVER: dict[str, Any] = {
    "server_name": "datasets",
    "server_type": "statgpt",
    "deployment_id": "statgpt-mcp",
    "list_datasets_tool": "list_datasets",
    "client_meta_key": "acme.example.org/client",
    "references_table": {"title": "Datasets", "columns": [{"heading": "N", "key": "name"}]},
}

_STATS = {"list_documents_tool": _TOOL, "document_date_key": _DATE}


def _properties(*servers: dict[str, Any]) -> ApplicationProperties:
    return ApplicationProperties.model_validate(
        {
            "prompts": {"client_name": "ACME", "agent_name": "ACME Deep Research"},
            "mcp_servers": list(servers),
        }
    )


def _route(fakes: dict[str, FakeMcpServer], monkeypatch: pytest.MonkeyPatch) -> None:
    """Build each server's client from its own fake, so a call reaching the wrong server fails."""

    def build(servers: list[Any], **_kwargs: Any) -> Any:
        [server] = servers
        return fakes[server.server_name].client()

    monkeypatch.setattr(data_sources, "build_mcp_client", build)


async def test_a_document_only_channel_fetches_the_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMcpServer({_TOOL: _collection([_document(1)])})
    _route({"documents": fake}, monkeypatch)
    server = {**_DOCUMENT_SERVER, "document_stats": _STATS}

    fetched = await fetch_data_sources(_properties(server))

    assert fetched.text == (
        "Document statistics:\n1 document, published from 2024-01-10 to 2024-01-10.\n\n"
        "<documents_description>\n## Publications\n</documents_description>"
    )
    assert fetched.datasets is None
    assert fetched.documents is not None


async def test_a_failed_listing_gives_its_failure_text_before_the_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(_args: dict[str, Any]) -> Any:
        raise RuntimeError("HTTP 502 from the gateway")

    documents = FakeMcpServer({_TOOL: down})
    datasets = FakeMcpServer({"list_datasets": lambda _args: structured({"datasets": []})})
    _route({"documents": documents, "datasets": datasets}, monkeypatch)
    document_server = {**_DOCUMENT_SERVER, "document_stats": _STATS}

    fetched = await fetch_data_sources(_properties(document_server, _DATASET_SERVER))

    assert fetched.text == (
        f"{_FAILED_BLOCK}\n\n"
        "<documents_description>\n## Publications\n</documents_description>\n\n"
        'Datasets:\n{"datasets": []}'
    )


async def test_the_parts_follow_the_fixed_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = FakeMcpServer({_TOOL: _collection([_document(1)])})
    datasets = FakeMcpServer({"list_datasets": lambda _args: structured({"datasets": []})})
    _route({"documents": documents, "datasets": datasets}, monkeypatch)

    fetched = await fetch_data_sources(
        _properties(
            {**_DATASET_SERVER, "description": "About the datasets."},
            {**_DOCUMENT_SERVER, "document_stats": _STATS},
        )
    )

    assert fetched.text == (
        "Document statistics:\n1 document, published from 2024-01-10 to 2024-01-10.\n\n"
        "<documents_description>\n## Publications\n</documents_description>\n\n"
        'Datasets:\n{"datasets": []}\n\n'
        "<datasets_description>\nAbout the datasets.\n</datasets_description>"
    )


async def test_the_documents_are_fetched_alongside_the_datasets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    both_started = asyncio.Event()

    def waiting(name: str, answer: dict[str, Any]) -> Any:
        async def handler(_args: dict[str, Any]) -> Any:
            started.append(name)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return structured(answer)

        return handler

    documents = FakeMcpServer({_TOOL: waiting("documents", {"total_count": 0, "results": []})})
    datasets = FakeMcpServer({"list_datasets": waiting("datasets", {"datasets": []})})
    _route({"documents": documents, "datasets": datasets}, monkeypatch)

    fetched = await fetch_data_sources(
        _properties({**_DOCUMENT_SERVER, "document_stats": _STATS}, _DATASET_SERVER)
    )

    assert sorted(started) == ["datasets", "documents"]
    assert fetched.documents is not None
    assert fetched.documents.statistics is not None


async def test_a_description_alone_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no MCP client may be built")

    monkeypatch.setattr(data_sources, "build_mcp_client", no_client)

    fetched = await fetch_data_sources(_properties(_DOCUMENT_SERVER))

    assert fetched.text == "<documents_description>\n## Publications\n</documents_description>"


async def test_statistics_alone_that_fail_still_name_the_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(_args: dict[str, Any]) -> Any:
        raise RuntimeError("HTTP 502 from the gateway")

    _route({"documents": FakeMcpServer({_TOOL: down})}, monkeypatch)
    server = {key: value for key, value in _DOCUMENT_SERVER.items() if key != "description"}

    fetched = await fetch_data_sources(_properties({**server, "document_stats": _STATS}))

    assert fetched.text == _FAILED_BLOCK
