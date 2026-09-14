"""Calling the configured dataset-metadata tool, and reading the catalogue it answers with.

A dataset citation needs three things the app does not hold: the dataset's human name, which
labels the pill and the card; the address of its page, which is what the pill's card opens; and
its last-update date, which that card carries when the server knows one. All three come from one
MCP tool. The contract that tool must satisfy — no arguments, a `datasets` array as its
structured result, `url` and `lastUpdated` optional per record — is stated by the
report-citations capability; this module depends on nothing else about it.

The tool answers with the channel's whole catalogue, so selecting the cited datasets happens
here. A cited URN is matched against a record's `id` character for character, as the
source-attribution capability requires.

Every failure here is one exception carrying a `kind`, the token the citation step's warning
reports. Nothing in this module logs: the answer is a tool response body, and the caller owns
what may be said about it (counts, never a name or a URL).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from dial_deep_research.app.research.citations import DatasetSource, is_web_url

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
    """What the catalogue reports about each cited dataset a pill can be drawn for.

    A dataset the answer omits, or reports without a URL a browser can open, is simply absent
    from the result; its citations keep the marker text the report writer wrote. A record with no
    usable name is kept, its citation labelled from the URN, because what makes a dataset citable
    is the page rather than the name.

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
    # status is what makes such a failure reach the caller (see the change's design, decision 6).
    if isinstance(result, ToolMessage) and result.status == "error":
        raise DatasetMetadataError(KIND_DATASET_CALL_FAILED)
    artifact = result.artifact if isinstance(result, ToolMessage) else None
    if not isinstance(artifact, dict) or "structured_content" not in artifact:
        # No structured result: MCP sends one only for a tool that declares an output schema,
        # which the contract requires. The text copy of the catalogue MCP also carries is
        # deliberately not read — a second read path, for a case no server we can test against
        # produces, would decide silently which copy an answer came from.
        raise DatasetMetadataError(KIND_DATASET_NO_STRUCTURED_RESULT)
    try:
        catalogue = _Catalogue.model_validate(artifact["structured_content"])
    except ValidationError as error:
        raise DatasetMetadataError(KIND_DATASET_UNREADABLE_RESULT) from error

    cited = set(dataset_ids)
    sources: dict[str, DatasetSource] = {}
    for record in catalogue.datasets:
        if record.id is None or record.id not in cited or record.url is None:
            continue
        if not is_web_url(record.url):
            continue
        sources[record.id] = DatasetSource(
            url=record.url, name=record.name, last_updated=record.last_updated
        )
    return sources
