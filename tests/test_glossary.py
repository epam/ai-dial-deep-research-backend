"""The glossary part of the data-sources fetch: batches, rounds, rendering and log records."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from dial_deep_research.app import data_source_calls, glossary
from dial_deep_research.app.glossary import fetch_glossary
from dial_deep_research.app_properties import GlossaryTools
from tests.mcp_fakes import FakeMcpServer, mcp_error, structured

_LIST_TOOL = "list_terms"
_DEFINITIONS_TOOL = "define_terms"


def _tools(limit: int = 10) -> GlossaryTools:
    return GlossaryTools.model_validate(
        {
            "list_terms_tool": _LIST_TOOL,
            "definitions_tool": _DEFINITIONS_TOOL,
            "max_terms_per_definitions_call": limit,
            "references_table": {
                "title": "Glossary",
                "columns": [
                    {"heading": "Term", "key": "term"},
                    {"heading": "Definition", "key": "definition"},
                ],
            },
        }
    )


def _terms(count: int) -> list[dict[str, Any]]:
    return [{"term": f"Term {i}", "category": "c"} for i in range(1, count + 1)]


def _definitions_for(arguments: dict[str, Any], *, skip: set[str] | None = None) -> Any:
    skip = skip or set()
    return structured(
        {
            "definitions": [
                {"term": term, "definition": f"What {term} means.", "source": "s"}
                for term in arguments["terms"]
                if term not in skip
            ],
            **({"notFound": sorted(skip & set(arguments["terms"]))} if skip else {}),
        }
    )


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr(data_source_calls, "sleep", sleep)
    return pauses


def _fake(*, terms: list[dict[str, Any]], definitions: Any = None) -> FakeMcpServer:
    return FakeMcpServer(
        {
            _LIST_TOOL: lambda _args: structured({"terms": terms}),
            _DEFINITIONS_TOOL: definitions or _definitions_for,
        }
    )


def _rendered(text: str) -> list[dict[str, Any]]:
    heading, array = text.split("\n", 1)
    assert heading == "Glossary terms:"
    return json.loads(array)


async def test_a_glossary_larger_than_the_limit_is_split_into_concurrent_batches() -> None:
    fake = _fake(terms=_terms(25))

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools(limit=10))

    batches = fake.calls_of(_DEFINITIONS_TOOL)
    assert [len(call["terms"]) for call in batches] == [10, 10, 5]
    assert fetched.listed == 25
    assert fetched.unresolved == 0


async def test_only_the_unresolved_terms_are_re_requested(instant_retries: list[float]) -> None:
    calls = 0

    def definitions(arguments: dict[str, Any]) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("HTTP 502 from the gateway")
        return _definitions_for(arguments)

    fake = _fake(terms=_terms(25), definitions=definitions)

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools(limit=10))

    batches = fake.calls_of(_DEFINITIONS_TOOL)
    assert len(batches) == 4
    assert batches[3]["terms"] == batches[0]["terms"]
    assert fetched.unresolved == 0
    assert len(instant_retries) == 1


async def test_a_term_not_found_stays_listed_without_a_definition_after_three_rounds(
    instant_retries: list[float],
) -> None:
    fake = _fake(terms=_terms(3), definitions=lambda args: _definitions_for(args, skip={"Term 2"}))

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    batches = fake.calls_of(_DEFINITIONS_TOOL)
    assert [call["terms"] for call in batches] == [
        ["Term 1", "Term 2", "Term 3"],
        ["Term 2"],
        ["Term 2"],
    ]
    assert [round(p) for p in instant_retries] == [1, 2]
    rendered = _rendered(fetched.text)
    assert rendered[1] == {"index": 2, "term": "Term 2", "definition": None, "category": "c"}
    assert fetched.unresolved == 1


async def test_resolved_and_unresolved_terms_are_rendered_side_by_side() -> None:
    terms = [{"term": "Primary Commodity Prices"}, {"term": "World Economic Outlook"}]
    fake = _fake(
        terms=terms,
        definitions=lambda args: _definitions_for(args, skip={"Primary Commodity Prices"}),
    )

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert _rendered(fetched.text) == [
        {"index": 1, "term": "Primary Commodity Prices", "definition": None},
        {
            "index": 2,
            "term": "World Economic Outlook",
            "definition": "What World Economic Outlook means.",
            "source": "s",
        },
    ]


async def test_a_term_is_matched_by_its_trimmed_case_folded_name() -> None:
    terms = [{"term": " world economic outlook"}, {"term": "World Economic Outlook"}]

    def definitions(_args: dict[str, Any]) -> Any:
        return structured(
            {
                "definitions": [
                    {"term": "WORLD ECONOMIC OUTLOOK ", "definition": "The outlook."},
                    {"term": "Something unrequested", "definition": "Ignored."},
                ]
            }
        )

    fake = _fake(terms=terms, definitions=definitions)

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert fake.calls_of(_DEFINITIONS_TOOL) == [{"terms": [" world economic outlook"]}]
    assert fetched.unresolved == 0
    assert [entry["definition"] for entry in _rendered(fetched.text)] == [
        "The outlook.",
        "The outlook.",
    ]


async def test_an_empty_glossary_renders_an_empty_array_and_requests_nothing() -> None:
    fake = _fake(terms=[])

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert fetched.text == "Glossary terms:\n[]"
    assert fake.calls_of(_DEFINITIONS_TOOL) == []
    assert fetched.listed == 0


async def test_a_failed_list_gives_the_failure_text_and_no_definitions_call() -> None:
    fake = FakeMcpServer({_LIST_TOOL: lambda _args: mcp_error()})

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert len(fake.calls_of(_LIST_TOOL)) == 3
    assert fetched.text == "Glossary terms:\nfailed to obtain list of terms"
    assert fetched.records is None
    assert fetched.listed is None


async def test_a_list_without_term_strings_is_a_failed_attempt() -> None:
    fake = FakeMcpServer({_LIST_TOOL: lambda _args: structured({"terms": [{"name": "x"}]})})

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert len(fake.calls_of(_LIST_TOOL)) == 3
    assert fetched.records is None


async def test_the_fetch_keeps_one_record_per_listed_term_for_the_references_table() -> None:
    fake = _fake(terms=_terms(2), definitions=lambda args: _definitions_for(args, skip={"Term 1"}))

    fetched = await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    assert fetched.records == [
        {"term": "Term 1", "category": "c"},
        {"term": "Term 2", "definition": "What Term 2 means.", "source": "s"},
    ]


async def test_a_complete_fetch_logs_one_info_event_and_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _fake(terms=_terms(25))

    with caplog.at_level(logging.INFO, logger=glossary.__name__):
        await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert messages[0].startswith(
        "Glossary fetched: server=datasets list_attempts=1 listed=25 resolved=25 unresolved=0 "
        "rounds=1 duration="
    )


async def test_unresolved_terms_are_counted_and_never_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _fake(
        terms=_terms(3), definitions=lambda args: _definitions_for(args, skip={"Term 1", "Term 3"})
    )

    with caplog.at_level(logging.INFO, logger=glossary.__name__):
        await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Glossary terms left without a definition: server=datasets unresolved=2"]
    assert all("Term" not in record.getMessage() for record in caplog.records)


async def test_a_failed_list_logs_its_kind_and_an_absent_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeMcpServer({_LIST_TOOL: lambda _args: mcp_error()})

    with caplog.at_level(logging.INFO, logger=glossary.__name__):
        await fetch_glossary(fake.client(), server_name="datasets", tools=_tools())

    messages = [r.getMessage() for r in caplog.records]
    assert "Glossary terms could not be listed: server=datasets failure=mcp_error attempts=3" in (
        messages
    )
    assert any("listed=None resolved=0 unresolved=0 rounds=0" in message for message in messages)
