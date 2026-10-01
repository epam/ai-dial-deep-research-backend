"""The data-sources fetch: what the channel's servers report, fetched once per turn.

The turn starts by fetching up to three parts concurrently:

- **the datasets**, on a channel with a `statgpt` server: the list-datasets tool's answer, and,
  when a `dataset_structure_tool` is configured, the structure of every listed dataset, one call
  per dataset, all at once;
- **the glossary**, when the `statgpt` server configures one (see `glossary.py`);
- **the documents**, when the `generic_rag` server configures `document_stats` (see
  `document_stats.py`).

Each call gets up to three attempts (see `data_source_calls.py`). What the models see is the
**data-sources string**: the document statistics, the document server's `description`, the
datasets section, the dataset server's `description` and the glossary, each part present only when
its server is configured and the part has content, joined by blank lines, and each description
inside a tag of its own. The string goes to every model call that plans, researches or writes the
report, and `DataSources` also carries what the rest of the turn reads: the catalogue the
citations resolve against, and what the agents' instructions depend on (see the
data-sources-discovery capability).

No failure of the fetch fails the turn: a failed or incomplete list becomes its failure text, and a
structure that was not obtained becomes a failure entry. Cancellation propagates.

The log records carry counts and failure kinds only: the catalogue is the client's content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.types import CallToolResult
from pydantic import BaseModel, Field

from dial_deep_research.app.data_source_calls import (
    InvalidResultError,
    call_with_attempts,
    of_structured,
)
from dial_deep_research.app.document_stats import DocumentStatsFetch, fetch_document_stats
from dial_deep_research.app.glossary import GlossaryFetch, fetch_glossary
from dial_deep_research.app.mcp_tools import build_mcp_client
from dial_deep_research.app.research.citations import DatasetSource
from dial_deep_research.app.research.dataset_metadata import (
    DatasetMetadataError,
    parse_catalogue,
    read_client_payload,
)
from dial_deep_research.app_properties import ApplicationProperties, MCPClientSettings

logger = logging.getLogger(__name__)

DATASETS_HEADING = "Datasets:"
STRUCTURES_HEADING = "Dataset structures:"
DATASETS_LIST_FAILED_TEXT = "failed to obtain list of datasets"
STRUCTURE_FAILED_TEXT = "failed to obtain dataset structure"
DOCUMENTS_DESCRIPTION_TAG = "documents_description"
DATASETS_DESCRIPTION_TAG = "datasets_description"

# The argument the dataset-structure tool takes, which also keys a failure entry: the app does not
# know which key the server's own answer names the dataset under.
STRUCTURE_ARGUMENT = "dataset_id"


class DatasetsFetch(BaseModel):
    """The datasets part's result: the rendered section, and what the rest of the turn reads.

    `catalogue` is `None` when the list failed. `structures_rendered` says whether the section
    carries a structures block, and `structures_failed` how many of its entries are failure
    entries.
    """

    section: str
    catalogue: dict[str, DatasetSource] | None
    structures_rendered: bool = False
    structures_failed: int = 0


class DataSources(BaseModel):
    """One turn's data sources: the string every planning, research and report call receives,
    and what the fetch learned that the turn's other steps depend on.

    `datasets` is `None` on a channel without a dataset server, `glossary` on a channel that
    configures no glossary, and `documents` on a channel that configures no document statistics;
    that part was not fetched then.
    """

    text: str
    datasets: DatasetsFetch | None = None
    glossary: GlossaryFetch | None = None
    documents: DocumentStatsFetch | None = None

    @property
    def catalogue(self) -> dict[str, DatasetSource] | None:
        """The catalogue the list call obtained, or `None` when there is none to seed from."""
        return self.datasets.catalogue if self.datasets is not None else None

    @property
    def dataset_list_failed(self) -> bool:
        """Whether the channel has a dataset server whose list call failed three times."""
        return self.datasets is not None and self.datasets.catalogue is None

    @property
    def structures_rendered(self) -> bool:
        return self.datasets is not None and self.datasets.structures_rendered

    @property
    def structures_failed(self) -> int:
        return self.datasets.structures_failed if self.datasets is not None else 0

    @property
    def glossary_listed(self) -> int | None:
        """How many terms the glossary listed, or `None` when it failed or is not configured."""
        return self.glossary.listed if self.glossary is not None else None

    @property
    def glossary_unresolved(self) -> int:
        return self.glossary.unresolved if self.glossary is not None else 0

    @property
    def glossary_list_failed(self) -> bool:
        return self.glossary is not None and self.glossary.records is None


class _ListedDatasets(BaseModel):
    """A successful list answer: the structured result as sent, and the catalogue parsed from it."""

    raw: dict[str, Any]
    catalogue: dict[str, DatasetSource] = Field(default_factory=dict)


def _list_reader(client_meta_key: str | None) -> Callable[[CallToolResult], _ListedDatasets]:
    """A reader accepting a list answer whose structured content carries a `datasets` array, the
    shape report-citations requires.

    The explorer links under `client_meta_key` in the result's `_meta` reach the catalogue alone,
    never `raw`, which is what the models are shown. A missing or unreadable payload is not a
    failed attempt: it costs the links.
    """

    def read(result: CallToolResult) -> _ListedDatasets:
        structured = result.structuredContent
        try:
            catalogue = parse_catalogue(
                structured,
                client_payload=read_client_payload(result.meta, client_meta_key=client_meta_key),
            )
        except DatasetMetadataError as error:
            raise InvalidResultError() from error
        return _ListedDatasets(raw=structured, catalogue=catalogue)

    return read


def _read_structure(structured: Any) -> dict[str, Any]:
    """Accept any structure answer that is a JSON object: the app reads nothing inside it."""
    if not isinstance(structured, dict):
        raise InvalidResultError()
    return structured


def _listed_ids(raw: dict[str, Any]) -> list[str]:
    """The distinct string `id`s of the listed datasets, in list order."""
    ids: list[str] = []
    for record in raw.get("datasets") or []:
        if (
            isinstance(record, dict)
            and isinstance(record.get("id"), str)
            and record["id"] not in ids
        ):
            ids.append(record["id"])
    return ids


def _dumps(value: Any) -> str:
    """One-line JSON with non-ASCII characters kept as themselves."""
    return json.dumps(value, ensure_ascii=False)


def render_datasets_section(
    listed: dict[str, Any] | None,
    *,
    structures: Sequence[tuple[str, dict[str, Any] | None]] | None,
) -> str:
    """The datasets section: the list answer, then the structures block when structures were
    requested, or the failure text for a failed list.

    `structures` pairs each requested dataset id, in list order, with its structure answer or
    `None` when it was not obtained; `None` itself means no structures block.
    """
    if listed is None:
        return f"{DATASETS_HEADING}\n{DATASETS_LIST_FAILED_TEXT}"
    section = f"{DATASETS_HEADING}\n{_dumps(listed)}"
    if structures is None:
        return section
    entries = [
        (
            answer
            if answer is not None
            else {STRUCTURE_ARGUMENT: dataset_id, "error": STRUCTURE_FAILED_TEXT}
        )
        for dataset_id, answer in structures
    ]
    return f"{section}\n\n{STRUCTURES_HEADING}\n{_dumps(entries)}"


async def fetch_datasets(
    client: MultiServerMCPClient, *, server: MCPClientSettings
) -> DatasetsFetch:
    """Fetch and render the datasets part. A failed MCP call does not raise; a server that names
    no `list_datasets_tool` raises `ValueError`; cancellation propagates."""
    started_at = time.monotonic()
    server_name = server.server_name
    list_tool = server.list_datasets_tool
    if list_tool is None:
        # Validation requires a statgpt server to name the list tool, so only a caller that
        # bypassed it gets here.
        raise ValueError(f"server {server_name!r} names no list_datasets_tool")
    listing = await call_with_attempts(
        client,
        server_name=server_name,
        tool_name=list_tool,
        arguments={},
        read=_list_reader(server.client_meta_key),
    )
    if listing.value is None:
        logger.warning(
            "Dataset list could not be fetched: server=%s failure=%s attempts=%d",
            server_name,
            listing.failure_kind,
            listing.attempts,
        )
        _log_fetched(
            server_name=server_name,
            list_attempts=listing.attempts,
            datasets=None,
            requested=0,
            obtained=0,
            started_at=started_at,
        )
        return DatasetsFetch(section=render_datasets_section(None, structures=None), catalogue=None)

    raw = listing.value.raw
    ids = _listed_ids(raw)
    structures: list[tuple[str, dict[str, Any] | None]] | None = None
    if server.dataset_structure_tool is not None and ids:
        tool_name = server.dataset_structure_tool
        answers = await asyncio.gather(
            *(
                call_with_attempts(
                    client,
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments={STRUCTURE_ARGUMENT: dataset_id},
                    read=of_structured(_read_structure),
                )
                for dataset_id in ids
            )
        )
        structures = [
            (dataset_id, answer.value) for dataset_id, answer in zip(ids, answers, strict=True)
        ]

    obtained = sum(1 for _, answer in structures or [] if answer is not None)
    failed = len(structures or []) - obtained
    if failed:
        logger.warning(
            "Dataset structures could not be fetched: server=%s structures_failed=%d",
            server_name,
            failed,
        )
    _log_fetched(
        server_name=server_name,
        list_attempts=listing.attempts,
        datasets=len(raw.get("datasets") or []),
        requested=len(structures or []),
        obtained=obtained,
        started_at=started_at,
    )
    return DatasetsFetch(
        section=render_datasets_section(raw, structures=structures),
        catalogue=listing.value.catalogue,
        structures_rendered=structures is not None,
        structures_failed=failed,
    )


def _log_fetched(
    *,
    server_name: str,
    list_attempts: int,
    datasets: int | None,
    requested: int,
    obtained: int,
    started_at: float,
) -> None:
    logger.info(
        "Datasets fetched: server=%s list_attempts=%d datasets=%s structures_requested=%d "
        "structures_obtained=%d structures_failed=%d duration=%.1fs",
        server_name,
        list_attempts,
        datasets,
        requested,
        obtained,
        requested - obtained,
        time.monotonic() - started_at,
    )


def _tagged(tag: str, text: str | None) -> str | None:
    """`text` between an opening and a closing `tag` line, or `None` when there is no text."""
    return None if text is None else f"<{tag}>\n{text}\n</{tag}>"


def join_data_sources(
    *,
    document_stats: str | None = None,
    documents_description: str | None = None,
    datasets: str | None = None,
    datasets_description: str | None = None,
    glossary: str | None = None,
) -> str:
    """The data-sources string: the parts that are set, in this order, joined by blank lines.

    A description is the admin's text and often carries Markdown headings, so each is wrapped in a
    tag of its own: without it, the part after it would read as a subsection of its last heading.
    The fetched parts each start with a label line and stay unwrapped. An unset part leaves
    nothing behind.
    """
    parts = [
        document_stats,
        _tagged(DOCUMENTS_DESCRIPTION_TAG, documents_description),
        datasets,
        _tagged(DATASETS_DESCRIPTION_TAG, datasets_description),
        glossary,
    ]
    return "\n\n".join(part for part in parts if part is not None)


async def fetch_data_sources(
    properties: ApplicationProperties, *, bearer_token: str | None = None
) -> DataSources:
    """Run the turn's data-sources fetch, or make no call when no part has anything to fetch.

    Each server gets a client built for this fetch alone, with the same connection and credentials
    as the turn's other MCP traffic to it. The parts run concurrently, so the turn waits for the
    slowest of them rather than for their sum.
    """
    dataset_server = properties.dataset_server
    document_server = properties.document_server

    async def datasets_part() -> tuple[DatasetsFetch, GlossaryFetch | None] | None:
        if dataset_server is None:
            return None
        client = build_mcp_client([dataset_server], bearer_token=bearer_token)
        glossary_tools = dataset_server.glossary

        async def glossary_part() -> GlossaryFetch | None:
            if glossary_tools is None:
                return None
            return await fetch_glossary(
                client, server_name=dataset_server.server_name, tools=glossary_tools
            )

        return await asyncio.gather(fetch_datasets(client, server=dataset_server), glossary_part())

    async def documents_part() -> DocumentStatsFetch | None:
        if document_server is None or document_server.document_stats is None:
            return None
        client = build_mcp_client([document_server], bearer_token=bearer_token)
        return await fetch_document_stats(
            client, server_name=document_server.server_name, config=document_server.document_stats
        )

    dataset_parts, documents = await asyncio.gather(datasets_part(), documents_part())
    datasets, glossary = dataset_parts if dataset_parts is not None else (None, None)
    return DataSources(
        text=join_data_sources(
            document_stats=documents.text if documents is not None else None,
            documents_description=(
                document_server.description if document_server is not None else None
            ),
            datasets=datasets.section if datasets is not None else None,
            datasets_description=dataset_server.description if dataset_server is not None else None,
            glossary=glossary.text if glossary is not None else None,
        ),
        datasets=datasets,
        glossary=glossary,
        documents=documents,
    )
