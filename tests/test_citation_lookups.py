"""The review and the delivery share one turn's lookups: the catalogue is fetched once, a
document is read once, and a failed lookup caches nothing."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import pytest
from langchain_core.documents.base import Blob
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.app.research.citation_lookups import CitationLookups
from dial_deep_research.app.research.data_queries import DataQueryRecord, DataQueryStore
from dial_deep_research.app_properties import DocumentMetadataSource

_URN = "IMF:WEO(1.0.0)"
_SOURCE = DocumentMetadataSource(
    server_name="documents",
    resource_template="documents://metadata/{document_ids}",
    title_key="publication_title",
)


class _Catalogue:
    """A dataset-metadata tool counting its calls, failing the first `fail_first` of them."""

    def __init__(self, *, fail_first: int = 0) -> None:
        self.calls = 0
        self._fail_first = fail_first

    def tool(self) -> BaseTool:
        async def list_datasets(**_kwargs: Any) -> tuple[str, Any]:
            self.calls += 1
            if self.calls <= self._fail_first:
                raise RuntimeError("the server is down")
            return "text", {"structured_content": {"datasets": [{"id": _URN, "name": "WEO"}]}}

        return StructuredTool.from_function(
            coroutine=list_datasets,
            name="list_datasets",
            description="List the datasets.",
            response_format="content_and_artifact",
        )


class _Resource:
    """A document-metadata resource answering for the ids it knows, recording each read."""

    def __init__(self, known: dict[int, dict[str, Any]], *, fail_first: int = 0) -> None:
        self._known = known
        self._fail_first = fail_first
        self.uris: list[str] = []

    async def get_resources(self, _server_name: str, *, uris: list[str]) -> list[Blob]:
        self.uris.extend(uris)
        if len(self.uris) <= self._fail_first:
            raise RuntimeError("the server is down")
        requested = {int(i) for i in uris[0].rsplit("/", 1)[1].split(",")}
        body = {str(i): fields for i, fields in self._known.items() if i in requested}
        return [Blob.from_data(data=json.dumps(body), mime_type="application/json")]


def _lookups(
    *,
    catalogue: _Catalogue | None = None,
    resource: _Resource | None = None,
    data_queries: DataQueryStore | None = None,
) -> CitationLookups:
    return CitationLookups(
        dataset_tool=catalogue.tool() if catalogue is not None else None,
        client=cast(MultiServerMCPClient, resource or _Resource({})),
        document_source=_SOURCE,
        data_queries=data_queries or DataQueryStore(),
    )


async def test_one_catalogue_call_serves_every_draft_and_the_delivery() -> None:
    catalogue = _Catalogue()
    lookups = _lookups(catalogue=catalogue)

    await lookups.prefetch(f"First [dataset {_URN}].")
    await lookups.prefetch(f"Second [dataset {_URN}] and [dataset IMF:WEO(2.0.0)].")
    sources = await lookups.dataset_sources([_URN])

    assert catalogue.calls == 1
    assert set(sources) == {_URN}
    assert lookups.dataset_known(_URN) is True
    assert lookups.dataset_known("IMF:WEO(2.0.0)") is False


async def test_a_draft_citing_no_dataset_makes_no_call() -> None:
    catalogue = _Catalogue()
    lookups = _lookups(catalogue=catalogue)

    await lookups.prefetch("Only a document [doc 1, page 2].")

    assert catalogue.calls == 0
    assert lookups.dataset_known(_URN) is None


async def test_a_cited_query_with_a_link_fetches_its_datasets_catalogue() -> None:
    catalogue = _Catalogue()
    store = DataQueryStore(
        records={
            "dq_1": DataQueryRecord.model_validate(
                {
                    "_meta": {"queryId": "dq_1", "dataExplorerUrl": "https://x.example.org/e"},
                    "structured_content": {"queryId": "dq_1", "datasetUrn": _URN},
                }
            )
        }
    )
    lookups = _lookups(catalogue=catalogue, data_queries=store)

    await lookups.prefetch("A value [data_query dq_1].")

    assert catalogue.calls == 1


async def test_documents_already_looked_up_are_not_read_again() -> None:
    resource = _Resource({207: {"publication_title": "Market Outlook 2025"}, 442: {}})
    lookups = _lookups(resource=resource)

    await lookups.prefetch("A [doc 207, page 1] and B [doc 442, page 3].")
    metadata = await lookups.document_metadata([207, 442])

    assert resource.uris == ["documents://metadata/207,442"]
    assert metadata == {207: {"publication_title": "Market Outlook 2025"}, 442: {}}


async def test_only_ids_not_yet_looked_up_are_read() -> None:
    resource = _Resource({207: {}, 442: {}})
    lookups = _lookups(resource=resource)

    await lookups.prefetch("A [doc 207, page 1].")
    await lookups.prefetch("A [doc 207, page 1] and B [doc 442, page 3].")

    assert resource.uris == ["documents://metadata/207", "documents://metadata/442"]


async def test_an_omitted_document_id_is_recorded_as_unknown() -> None:
    lookups = _lookups(resource=_Resource({207: {"publication_title": "Market Outlook 2025"}}))

    await lookups.prefetch("A [doc 207, page 1] and B [doc 999, page 2].")

    assert lookups.document_known(207) is True
    assert lookups.document_known(999) is False
    assert await lookups.document_metadata([999]) == {}


async def test_a_failed_catalogue_call_is_not_cached_and_is_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    catalogue = _Catalogue(fail_first=1)
    lookups = _lookups(catalogue=catalogue)

    with caplog.at_level(logging.WARNING):
        await lookups.prefetch(f"A [dataset {_URN}].")
    assert lookups.dataset_known(_URN) is None

    sources = await lookups.dataset_sources([_URN])

    assert catalogue.calls == 2
    assert set(sources) == {_URN}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "kind=dataset_call_failed" in warnings[0]
    assert "during=review" in warnings[0]
    assert _URN not in warnings[0]


async def test_a_failed_document_read_is_one_warning_and_is_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    resource = _Resource({999: {}}, fail_first=1)
    lookups = _lookups(resource=resource)

    with caplog.at_level(logging.WARNING):
        await lookups.prefetch("A [doc 999, page 2].")
        await lookups.prefetch("A [doc 999, page 2].")

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "kind=metadata_read_failed" in warnings[0]
    assert "during=review" in warnings[0]
    assert "999" not in warnings[0]
    assert lookups.document_known(999) is True
