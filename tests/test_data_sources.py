"""The datasets part of the data-sources fetch: attempts, deadlines, rendering and log records."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest

from dial_deep_research.app import data_source_calls, data_sources
from dial_deep_research.app.data_sources import (
    DataSources,
    fetch_data_sources,
    fetch_datasets,
)
from dial_deep_research.app_properties import ApplicationProperties, MCPClientSettings
from tests.mcp_fakes import FakeMcpServer, failing_first, mcp_error, structured

_LIST_TOOL = "list_datasets"
_STRUCTURE_TOOL = "describe_dataset"
_WEO = "IMF:WEO(1.0.0)"
_DOTS = "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"
_LIST = {
    "datasets": [
        {"id": _WEO, "name": "World Economic Outlook — April", "url": "https://x.example.org/w"},
        {"id": _DOTS, "name": "Direction of Trade Statistics"},
    ],
    "totalDatasets": 2,
}


def _structure(dataset_id: str) -> dict[str, Any]:
    return {"datasetId": dataset_id, "dimensions": [{"id": "COUNTRY", "values": ["DE"]}]}


def _server(**overrides: Any) -> MCPClientSettings:
    return MCPClientSettings.model_validate(
        {
            "server_name": "datasets",
            "server_type": "statgpt",
            "deployment_id": "statgpt-mcp",
            "list_datasets_tool": _LIST_TOOL,
            "data_query_meta_key": "acme.example.org/client",
            "references_table": {"title": "Datasets", "columns": [{"heading": "N", "key": "name"}]},
            **overrides,
        }
    )


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the pauses between attempts instead of waiting them out."""
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr(data_source_calls, "sleep", sleep)
    return pauses


def _fake(*, list_handler: Any = None, structure_handler: Any = None) -> FakeMcpServer:
    return FakeMcpServer(
        {
            _LIST_TOOL: list_handler or (lambda _args: structured(_LIST)),
            _STRUCTURE_TOOL: structure_handler
            or (lambda args: structured(_structure(args["dataset_id"]))),
        }
    )


async def test_the_list_is_called_with_no_arguments_and_rendered_as_sent() -> None:
    fake = _fake()

    fetched = await fetch_datasets(fake.client(), server=_server())

    assert fake.calls == [(_LIST_TOOL, {})]
    assert fetched.section == f"Datasets:\n{json.dumps(_LIST, ensure_ascii=False)}"
    assert "—" in fetched.section, "non-ASCII characters are written as themselves"
    assert fetched.catalogue is not None
    assert set(fetched.catalogue) == {_WEO, _DOTS}
    assert fetched.structures_rendered is False


async def test_a_transient_failure_is_retried_once(instant_retries: list[float]) -> None:
    fake = _fake(list_handler=failing_first(1, lambda _args: structured(_LIST)))

    fetched = await fetch_datasets(fake.client(), server=_server())

    assert len(fake.calls_of(_LIST_TOOL)) == 2
    assert fetched.catalogue is not None
    assert len(instant_retries) == 1
    assert 0.75 <= instant_retries[0] <= 1.25


async def test_three_failures_give_the_failure_text_and_no_structure_call(
    instant_retries: list[float],
) -> None:
    fake = _fake(list_handler=lambda _args: mcp_error())

    fetched = await fetch_datasets(
        fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL)
    )

    assert len(fake.calls_of(_LIST_TOOL)) == 3
    assert fake.calls_of(_STRUCTURE_TOOL) == []
    assert fetched.section == "Datasets:\nfailed to obtain list of datasets"
    assert fetched.catalogue is None
    assert [round(p) for p in instant_retries] == [1, 2]


@pytest.mark.parametrize(
    "answer",
    [
        structured({"items": []}),
        structured([{"id": _WEO}]),
        structured(None),
    ],
)
async def test_a_list_without_a_datasets_array_is_a_failed_attempt(answer: Any) -> None:
    fake = _fake(list_handler=lambda _args: answer)

    fetched = await fetch_datasets(fake.client(), server=_server())

    assert len(fake.calls_of(_LIST_TOOL)) == 3
    assert fetched.catalogue is None


async def test_a_stalled_call_is_cut_off_at_its_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data_source_calls, "CALL_TIMEOUT_SECONDS", 0.05)

    async def stall_once(_args: dict[str, Any]) -> Any:
        if len(fake.calls_of(_LIST_TOOL)) == 1:
            await asyncio.sleep(10)
        return structured(_LIST)

    fake = _fake(list_handler=stall_once)

    fetched = await fetch_datasets(fake.client(), server=_server())

    assert len(fake.calls_of(_LIST_TOOL)) == 2
    assert fetched.catalogue is not None


async def test_an_empty_list_is_a_success_with_no_structure_call() -> None:
    fake = _fake(list_handler=lambda _args: structured({"datasets": []}))

    fetched = await fetch_datasets(
        fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL)
    )

    assert fetched.catalogue == {}
    assert fake.calls_of(_STRUCTURE_TOOL) == []
    assert fetched.section == 'Datasets:\n{"datasets": []}'
    assert fetched.structures_rendered is False


async def test_every_listed_dataset_gets_one_structure_call_in_its_own_session() -> None:
    fake = _fake()

    fetched = await fetch_datasets(
        fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL)
    )

    assert fake.calls_of(_STRUCTURE_TOOL) == [{"dataset_id": _WEO}, {"dataset_id": _DOTS}]
    assert fake.sessions == 3
    structures = [_structure(_WEO), _structure(_DOTS)]
    assert fetched.section == (
        f"Datasets:\n{json.dumps(_LIST, ensure_ascii=False)}\n\n"
        f"Dataset structures:\n{json.dumps(structures, ensure_ascii=False)}"
    )
    assert fetched.structures_rendered is True
    assert fetched.structures_failed == 0


async def test_the_structure_calls_run_concurrently() -> None:
    in_flight = 0
    peak = 0

    async def slow_structure(args: dict[str, Any]) -> Any:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return structured(_structure(args["dataset_id"]))

    fake = _fake(structure_handler=slow_structure)

    await fetch_datasets(fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL))

    assert peak == 2


async def test_a_record_without_a_string_id_gets_no_structure_call() -> None:
    listing = {"datasets": [{"id": 7}, {"name": "no id"}, {"id": _WEO}, {"id": _WEO}]}
    fake = _fake(list_handler=lambda _args: structured(listing))

    await fetch_datasets(fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL))

    assert fake.calls_of(_STRUCTURE_TOOL) == [{"dataset_id": _WEO}]


async def test_only_the_failed_structure_call_is_repeated() -> None:
    weo_calls = 0

    def structure(args: dict[str, Any]) -> Any:
        nonlocal weo_calls
        if args["dataset_id"] == _WEO:
            weo_calls += 1
            if weo_calls == 1:
                raise RuntimeError("HTTP 502 from the gateway")
        return structured(_structure(args["dataset_id"]))

    fake = _fake(structure_handler=structure)

    fetched = await fetch_datasets(
        fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL)
    )

    calls = fake.calls_of(_STRUCTURE_TOOL)
    assert calls.count({"dataset_id": _WEO}) == 2
    assert calls.count({"dataset_id": _DOTS}) == 1
    assert fetched.structures_failed == 0


async def test_a_structure_that_is_not_an_object_is_a_failed_attempt() -> None:
    fake = _fake(
        structure_handler=lambda args: (
            structured([1, 2]) if args["dataset_id"] == _DOTS else structured(_structure(_WEO))
        )
    )

    fetched = await fetch_datasets(
        fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL)
    )

    assert fake.calls_of(_STRUCTURE_TOOL).count({"dataset_id": _DOTS}) == 3
    assert fetched.structures_failed == 1
    entries = json.loads(fetched.section.split("Dataset structures:\n", 1)[1])
    assert entries == [
        _structure(_WEO),
        {"dataset_id": _DOTS, "error": "failed to obtain dataset structure"},
    ]


async def test_a_cancelled_fetch_propagates_and_makes_no_further_attempt() -> None:
    async def never(_args: dict[str, Any]) -> Any:
        await asyncio.sleep(10)

    fake = _fake(list_handler=never)
    task = asyncio.create_task(fetch_datasets(fake.client(), server=_server()))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(fake.calls_of(_LIST_TOOL)) == 1


async def test_a_complete_fetch_logs_one_info_event_and_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _fake()

    with caplog.at_level(logging.INFO, logger=data_sources.__name__):
        await fetch_datasets(fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL))

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert messages[0].startswith(
        "Datasets fetched: server=datasets list_attempts=1 datasets=2 structures_requested=2 "
        "structures_obtained=2 structures_failed=0 duration="
    )
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_failures_are_counted_and_never_named(caplog: pytest.LogCaptureFixture) -> None:
    fake = _fake(structure_handler=lambda _args: mcp_error())

    with caplog.at_level(logging.INFO, logger=data_sources.__name__):
        await fetch_datasets(fake.client(), server=_server(dataset_structure_tool=_STRUCTURE_TOOL))

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        "Dataset structures could not be fetched: server=datasets structures_failed=2"
    ]
    for record in caplog.records:
        assert "IMF" not in record.getMessage()
        assert "World Economic" not in record.getMessage()


async def test_a_failed_list_logs_its_kind_and_an_absent_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _fake(list_handler=lambda _args: mcp_error())

    with caplog.at_level(logging.INFO, logger=data_sources.__name__):
        await fetch_datasets(fake.client(), server=_server())

    messages = [r.getMessage() for r in caplog.records]
    assert "Dataset list could not be fetched: server=datasets failure=mcp_error attempts=3" in (
        messages
    )
    assert any("datasets=None structures_requested=0" in message for message in messages)


async def test_a_raised_failure_is_recorded_by_its_class(caplog: pytest.LogCaptureFixture) -> None:
    group = ExceptionGroup("session", [ConnectionError("refused")])

    def raise_group(_args: dict[str, Any]) -> Any:
        raise group

    fake = _fake(list_handler=raise_group)

    with caplog.at_level(logging.WARNING, logger=data_sources.__name__):
        await fetch_datasets(fake.client(), server=_server())

    assert "failure=ConnectionError" in caplog.records[0].getMessage()


# --- the whole fetch -----------------------------------------------------------------------------

_DESCRIPTIONS = "## Publications\n\nMarket Outlook 2025."


def _properties(*servers: dict[str, Any]) -> ApplicationProperties:
    return ApplicationProperties.model_validate(
        {
            "prompts": {
                "client_name": "ACME",
                "agent_name": "ACME Deep Research",
                "data_sources_descriptions": _DESCRIPTIONS,
            },
            "mcp_servers": list(servers),
        }
    )


_DOCUMENT_SERVER: dict[str, Any] = {
    "server_name": "documents",
    "server_type": "generic_rag",
    "deployment_id": "rag-mcp",
    "file_sharing_tool": "get_citation_url",
    "document_metadata_resource": "documents://metadata/{document_ids}",
    "document_title_key": "publication_title",
    "references_table": {"title": "Documents", "columns": [{"heading": "T", "key": "t"}]},
}


async def test_a_channel_without_a_dataset_server_makes_no_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no MCP client may be built")

    monkeypatch.setattr(data_sources, "build_mcp_client", no_client)

    fetched = await fetch_data_sources(_properties(_DOCUMENT_SERVER))

    assert fetched == DataSources(text=_DESCRIPTIONS)
    assert fetched.dataset_list_failed is False


async def test_the_data_sources_string_joins_the_descriptions_and_the_datasets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake()
    monkeypatch.setattr(data_sources, "build_mcp_client", lambda *_a, **_k: fake.client())
    server = _server().model_dump(mode="json")

    fetched = await fetch_data_sources(_properties(_DOCUMENT_SERVER, server))

    assert fetched.text == (
        f"{_DESCRIPTIONS}\n\nDatasets:\n{json.dumps(_LIST, ensure_ascii=False)}"
    )
    assert fetched.glossary is None
    assert fetched.catalogue is not None


async def test_the_tool_filter_does_not_stop_the_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake()
    monkeypatch.setattr(data_sources, "build_mcp_client", lambda *_a, **_k: fake.client())
    server = _server(tools_to_include=["query_datasets"]).model_dump(mode="json")

    await fetch_data_sources(_properties(server))

    assert fake.calls_of(_LIST_TOOL) == [{}]


async def test_an_unreachable_server_still_gives_a_data_sources_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(_args: dict[str, Any]) -> Any:
        raise ConnectionError("unreachable")

    fake = FakeMcpServer(
        {
            _LIST_TOOL: unreachable,
            "list_terms": unreachable,
        }
    )
    monkeypatch.setattr(data_sources, "build_mcp_client", lambda *_a, **_k: fake.client())
    server = _server(
        glossary={
            "list_terms_tool": "list_terms",
            "definitions_tool": "define_terms",
            "max_terms_per_definitions_call": 10,
            "references_table": {"title": "Glossary", "columns": [{"heading": "T", "key": "term"}]},
        }
    ).model_dump(mode="json")

    fetched = await fetch_data_sources(_properties(server))

    assert fetched.text == (
        f"{_DESCRIPTIONS}\n\nDatasets:\nfailed to obtain list of datasets\n\n"
        "Glossary terms:\nfailed to obtain list of terms"
    )
    assert fetched.dataset_list_failed is True
    assert fetched.glossary_list_failed is True
    assert fetched.glossary_listed is None
