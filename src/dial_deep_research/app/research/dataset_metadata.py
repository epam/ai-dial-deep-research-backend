"""Calling the configured dataset-metadata tool, and reading the catalogue it answers with.

A dataset citation needs three things the app does not hold: the dataset's human name, which
labels the pill and the card and leads its References row; the address of its page, which is what
the pill's card opens; and its last-update date, which that card carries when the server knows
one. All three come from one MCP tool. The contract that tool must satisfy — no arguments, a
`datasets` array as its structured result, `url` and `lastUpdated` optional per record — is stated
by the report-citations capability; this module depends on nothing else about it.

The tool answers with the channel's whole catalogue, so selecting the cited datasets happens
here. A cited URN is matched against a record's `id` character for character, as the
source-attribution capability requires.

A selected record is carried out twice over: as the four fields the contract names, which is what
a pill is built from, and as the record the server sent, which is what a References row reads its
configured columns out of. The two views are why a record with nothing a pill can use is still
worth keeping.

Every failure here is one exception carrying a `kind`, the token the citation step's warning
reports. Nothing in this module logs: the answer is a tool response body, and the caller owns
what may be said about it (counts, never a name or a URL).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from dial_deep_research.app.research.citations import DatasetSource
from dial_deep_research.app.research.web_urls import is_web_url

# Failure kinds, as they appear in the citation step's warnings. Each names the dataset
# resolution, so one warning says which of the step's three resolutions failed.
KIND_DATASET_CALL_FAILED = "dataset_call_failed"
KIND_DATASET_NO_STRUCTURED_RESULT = "dataset_no_structured_result"
KIND_DATASET_UNREADABLE_RESULT = "dataset_unreadable_result"


def _as_text(value: Any) -> str | None:
    """The value when it is a string with something in it, and `None` otherwise.

    A field the contract asks for as a string may arrive as a null, a number or an empty string.
    Each of those is read as absent rather than as a failed answer, so one unreadable field
    costs at most what that field was for: a record with no usable name is labelled from its
    URN, and one with no usable URL is the one case that costs the pill. Kept unstripped,
    because an identifier is matched verbatim and a name is displayed as the server wrote it.
    """
    return value if isinstance(value, str) and value.strip() else None


_OptionalText = Annotated[str | None, BeforeValidator(_as_text)]


class _DatasetRecord(BaseModel):
    """One dataset the catalogue reports, read down to the fields a citation uses.

    Extra fields are ignored rather than refused, which the contract requires: a server may
    report a description, a provider or an indicator count without breaking it.
    """

    model_config = ConfigDict(extra="ignore")

    id: _OptionalText = None
    name: _OptionalText = None
    url: _OptionalText = None
    last_updated: _OptionalText = Field(default=None, alias="lastUpdated")


class _Catalogue(BaseModel):
    """The answer: one `datasets` array at the top level of the structured result.

    This shape is the whole of what the app refuses an answer over. Anything else that is wrong
    is wrong inside one record, and costs that record rather than every dataset pill.
    """

    model_config = ConfigDict(extra="ignore")

    datasets: list[_DatasetRecord]


class DatasetMetadataError(Exception):
    """The call did not produce a readable catalogue.

    `kind` is the stable token the citation step's warning carries. The message says no more
    than the kind: a record about this call may name counts and the tool, never a dataset.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


async def read_dataset_sources(
    *, tool: BaseTool, dataset_ids: Sequence[str]
) -> dict[str, DatasetSource]:
    """What the catalogue reports about each cited dataset, by URN.

    Every record whose `id` is cited is kept, whatever it carries: the pill is not the only thing
    that reads one, and the report's References section lists a cited dataset whether or not it can
    be opened. A dataset the answer omits is simply absent from the result, and its References row
    is built from its URN alone.

    Raises what `read_catalogue` raises.
    """
    return select_cited(await read_catalogue(tool=tool), dataset_ids=dataset_ids)


def select_cited(
    catalogue: Mapping[str, DatasetSource], *, dataset_ids: Sequence[str]
) -> dict[str, DatasetSource]:
    """The catalogue's records for the cited URNs, each matched character for character."""
    return {urn: catalogue[urn] for urn in dataset_ids if urn in catalogue}


async def read_catalogue(*, tool: BaseTool) -> dict[str, DatasetSource]:
    """Every dataset the catalogue reports, by URN.

    What a missing field costs is decided where that field is used — a record with no usable name
    is labelled from the URN, and one whose URL a browser cannot open carries no URL, so its
    citations keep the marker text the report writer wrote. A record with no usable `id` matches no
    cited URN and is skipped.

    The tool is invoked **tool-call-shaped** for the reason `share_documents` is: a
    plain-argument call returns no `ToolMessage`, and the structured result travels in that
    message's artifact.

    Raises:
        DatasetMetadataError: the tool reported an error, returned no structured result, or
            returned one carrying no readable `datasets` array.
        Exception: whatever the tool call itself raised.
    """
    result = await tool.ainvoke(
        {
            "name": tool.name,
            "args": {},
            "id": f"dataset-metadata-{uuid.uuid4().hex}",
            "type": "tool_call",
        }
    )
    # This tool stays in the research agent's tool list, so it keeps the agent's error handling:
    # an MCP error arrives as an error `ToolMessage` rather than as an exception. Reading the
    # status is what makes such a failure reach the caller.
    if isinstance(result, ToolMessage) and result.status == "error":
        raise DatasetMetadataError(KIND_DATASET_CALL_FAILED)
    artifact = result.artifact if isinstance(result, ToolMessage) else None
    if not isinstance(artifact, dict) or "structured_content" not in artifact:
        # No structured result: MCP sends one only for a tool that declares an output schema,
        # which the contract requires. The text copy of the catalogue MCP also carries is
        # deliberately not read — a second read path, for a case no server we can test against
        # produces, would decide silently which copy an answer came from.
        raise DatasetMetadataError(KIND_DATASET_NO_STRUCTURED_RESULT)
    structured = artifact["structured_content"]
    try:
        catalogue = _Catalogue.model_validate(structured)
    except ValidationError as error:
        raise DatasetMetadataError(KIND_DATASET_UNREADABLE_RESULT) from error

    raw_by_id = _raw_records_by_id(structured)
    sources: dict[str, DatasetSource] = {}
    for record in catalogue.datasets:
        if record.id is None:
            continue
        # A URL the client could not follow is normalized away here rather than carried inward: a
        # pill that opens nothing is worse than a marker that at least names its source, and every
        # later reader of this record would otherwise have to re-decide the same question.
        url = record.url if record.url is not None and is_web_url(record.url) else None
        sources[record.id] = DatasetSource(
            url=url,
            name=record.name,
            last_updated=record.last_updated,
            raw_fields=raw_by_id.get(record.id, {}),
        )
    return sources


def _raw_records_by_id(structured: Any) -> dict[str, dict[str, Any]]:
    """The reported records as they arrived, keyed by id, for the References rows to read.

    Read off the raw answer rather than off the validated catalogue, because validation declares
    the four fields the pill needs and a row may be configured to read any other field the channel
    reports. A record whose id is not a string is skipped: it matches no cited URN either.
    """
    if not isinstance(structured, dict):
        return {}
    records = structured.get("datasets")
    if not isinstance(records, list):
        return {}
    return {
        record["id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
