"""One turn's lookups of cited identifiers, shared by the report review and the delivery.

The report review checks that every dataset URN and document id a draft cites is one its server
knows, and the delivery labels and lists the same sources. Both ask the same two surfaces — the
dataset-metadata tool and the document-metadata resource — so one object per request holds what
they answered, and neither surface is asked twice about the same thing:

- the catalogue, fetched once and cached only after a successful call;
- each document id's metadata, where an id absent from a successful answer is recorded as unknown.

A failed lookup caches nothing, so the ids it was asked about stay "not looked up": no check
reports them as unknown, and the next check or the delivery asks again.

Nothing here logs an id, a URN, a name or a URL.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.app_properties import DocumentMetadataSource

from .citations import DatasetSource, cited_dataset_urns, cited_document_ids
from .data_queries import DataQueryStore
from .dataset_metadata import (
    KIND_DATASET_CALL_FAILED,
    DatasetMetadataError,
    read_catalogue,
    select_cited,
)
from .document_metadata import (
    KIND_METADATA_READ_FAILED,
    DocumentMetadataError,
    read_document_metadata,
)

logger = logging.getLogger(__name__)


class CitationLookups:
    """The catalogue and the document metadata this turn has looked up, and the means to ask.

    `dataset_tool` is the dataset-metadata tool the server advertised, and `document_source` the
    configured document-metadata resource; either is `None` on a channel without that server, and
    then every id of its kind stays not looked up. `data_queries` is read to find the dataset a
    cited query ran against.
    """

    def __init__(
        self,
        *,
        dataset_tool: BaseTool | None,
        client: MultiServerMCPClient,
        document_source: DocumentMetadataSource | None,
        data_queries: DataQueryStore,
    ) -> None:
        self._dataset_tool = dataset_tool
        self._client = client
        self._document_source = document_source
        self._data_queries = data_queries
        self._catalogue: dict[str, DatasetSource] | None = None
        # `None` for an id a successful answer omitted, which is what "unknown" means.
        self._documents: dict[int, dict[str, Any] | None] = {}

    @property
    def has_dataset_tool(self) -> bool:
        return self._dataset_tool is not None

    @property
    def document_source(self) -> DocumentMetadataSource | None:
        return self._document_source

    @property
    def data_queries(self) -> DataQueryStore:
        return self._data_queries

    async def dataset_sources(self, dataset_ids: Sequence[str]) -> dict[str, DatasetSource]:
        """The catalogue's records for these URNs, calling the tool only if no call succeeded yet.

        Raises what `read_catalogue` raises, and `ValueError` on a channel with no dataset tool.
        """
        if self._catalogue is None:
            if self._dataset_tool is None:
                raise ValueError("no dataset-metadata tool is available")
            self._catalogue = await read_catalogue(tool=self._dataset_tool)
        return select_cited(self._catalogue, dataset_ids=dataset_ids)

    async def document_metadata(self, document_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
        """The metadata of every known document among these ids, reading only ids not looked up.

        One resource read at most. An id the answer omits is recorded as unknown and left out of
        the result; a known id is in it even when its metadata object is empty.

        Raises what `read_document_metadata` raises, and `ValueError` on a channel with no
        document-metadata resource.
        """
        missing = [
            document_id for document_id in document_ids if document_id not in self._documents
        ]
        if missing:
            if self._document_source is None:
                raise ValueError("no document-metadata resource is configured")
            answer = await read_document_metadata(
                client=self._client, source=self._document_source, document_ids=missing
            )
            for document_id in missing:
                self._documents[document_id] = answer.get(document_id)
        return {
            document_id: metadata
            for document_id in document_ids
            if (metadata := self._documents.get(document_id)) is not None
        }

    def dataset_known(self, urn: str) -> bool | None:
        """Whether the catalogue carries this URN, or `None` when no catalogue call succeeded."""
        if self._catalogue is None:
            return None
        return urn in self._catalogue

    def document_known(self, document_id: int) -> bool | None:
        """Whether the resource knows this id, or `None` when it has not been looked up."""
        if document_id not in self._documents:
            return None
        return self._documents[document_id] is not None

    async def prefetch(self, draft: str) -> None:
        """Look up what the draft cites and the cache lacks, before the review's rules run.

        The datasets are the draft's dataset URNs and the datasets of its cited queries with an
        explorer link — the ones the delivery will label — so a catalogue fetched here serves the
        delivery too. Each failure is one WARNING and caches nothing. A channel whose dataset tool
        was not advertised is skipped silently here: the delivery warns about it once.
        """
        urns = cited_dataset_urns(draft, data_queries=self._data_queries.records)
        document_ids = cited_document_ids(draft)
        await asyncio.gather(self._prefetch_catalogue(urns), self._prefetch_documents(document_ids))

    async def _prefetch_catalogue(self, urns: Sequence[str]) -> None:
        if not urns or self._catalogue is not None or self._dataset_tool is None:
            return
        try:
            await self.dataset_sources(urns)
        except DatasetMetadataError as failure:
            _warn_review_lookup_failure(kind=failure.kind)
        except Exception as error:
            _warn_review_lookup_failure(kind=KIND_DATASET_CALL_FAILED, error=error)

    async def _prefetch_documents(self, document_ids: Sequence[int]) -> None:
        if not document_ids or self._document_source is None:
            return
        try:
            await self.document_metadata(document_ids)
        except DocumentMetadataError as failure:
            _warn_review_lookup_failure(kind=failure.kind)
        except Exception as error:
            _warn_review_lookup_failure(kind=KIND_METADATA_READ_FAILED, error=error)


def _warn_review_lookup_failure(*, kind: str, error: BaseException | None = None) -> None:
    """One WARNING per failed review-time lookup: the delivery's failure kind, marked as review."""
    fields = [f"kind={kind}", "during=review"]
    if error is not None:
        fields.append(f"error={type(error).__name__}")
    logger.warning("Report citations failed: %s", " ".join(fields))
