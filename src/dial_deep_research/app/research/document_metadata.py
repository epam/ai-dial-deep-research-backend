"""Reading cited documents' metadata from the configured document-metadata MCP resource.

A citation pill names the publication the reader is about to open, and a References row names the
same publication and whatever else that row's columns ask for. The app holds none of it — the only
human-readable string it has per cited document is the file name inside the shared URL, which is a
storage path segment — so it reads one MCP resource for the documents it is about to cite. The
contract that resource must satisfy is stated by the report-citations capability; this module
depends on nothing else about it.

What comes back is each document's metadata object as the channel stores it, and the caller reads
out of it the keys it was configured with: the title key for a label, a table column's key for a
row's cell. Reading it once for both is what keeps a pill's title and its row's first cell the
same fact rather than two lookups that can disagree.

A resource rather than a tool, because application code picks the moment and the ids, the answer
is the same for every caller within a channel, and the read changes nothing on the server. It
also never appears in a tool listing, so nothing has to be filtered out of what the agent is
offered.

Every failure here is one exception carrying a `kind`, the token the citation step's warning
reports. Nothing in this module logs: the answer is a resource body, and the caller owns what may
be said about it (counts, never a title).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents.base import Blob
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import TypeAdapter, ValidationError

from dial_deep_research.app_properties import DOCUMENT_IDS_PLACEHOLDER, DocumentMetadataSource

# Failure kinds, as they appear in the citation step's warnings.
KIND_METADATA_READ_FAILED = "metadata_read_failed"
KIND_METADATA_UNREADABLE = "metadata_unreadable_result"

# The answer: each known document's metadata, keyed by document id. The mapping is the whole
# object with no wrapper key, so the type is validated directly rather than through a model
# wrapping it. Keys arrive as JSON strings — JSON has no integer keys — and are read back as the
# integer ids the report's citation markers carry. Values stay `Any`, because the channel owns
# what its metadata holds and only the keys the caller was configured with are read out of it.
_ID_TO_METADATA = TypeAdapter(dict[int, dict[str, Any]])


class DocumentMetadataError(Exception):
    """The read did not produce a readable id-to-metadata mapping.

    `kind` is the stable token the citation step's warning carries. The message says no more
    than the kind: a record about this read may name counts, never a title or an id.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def build_resource_uri(template: str, document_ids: Sequence[int]) -> str:
    """The concrete URI for these ids: the template with its one placeholder filled in.

    Substituted literally rather than through `str.format`, which would treat any other brace in
    the URI as a field of its own. Configuration has already checked that the placeholder appears
    exactly once (see `MCPClientSettings`).
    """
    return template.replace(DOCUMENT_IDS_PLACEHOLDER, ",".join(str(i) for i in document_ids))


async def read_document_metadata(
    *,
    client: MultiServerMCPClient,
    source: DocumentMetadataSource,
    document_ids: Sequence[int],
) -> dict[int, dict[str, Any]]:
    """Each requested document's stored metadata, by document id, exactly as the channel stores it.

    A document the answer omits is simply absent from the result, and one present with nothing
    usable under a key the caller reads costs that one value. Nothing is renamed, dropped or
    interpreted here: which keys mean what is the caller's configuration, and a key this app was
    not configured to read is none of its business.

    Raises:
        DocumentMetadataError: the read failed, or the answer is not an id-to-metadata mapping.
    """
    uri = build_resource_uri(source.resource_template, document_ids)
    try:
        blobs = await client.get_resources(source.server_name, uris=[uri])
    except Exception as error:
        raise DocumentMetadataError(KIND_METADATA_READ_FAILED) from error

    try:
        return _ID_TO_METADATA.validate_python(_parse_single_json_object(blobs))
    except (ValidationError, ValueError) as error:
        raise DocumentMetadataError(KIND_METADATA_UNREADABLE) from error


def read_titles(metadata: Mapping[int, Mapping[str, Any]], *, title_key: str) -> dict[int, str]:
    """The title of every document carrying a usable one under `title_key`, by document id.

    Only a non-empty string counts, so a null, a number or an empty value reads as no title rather
    than as a label the reader cannot use. A document with no usable title is simply absent, and
    its citations keep the label their marker carried.
    """
    titles: dict[int, str] = {}
    for document_id, fields in metadata.items():
        title = fields.get(title_key)
        if isinstance(title, str) and title.strip():
            titles[document_id] = title
    return titles


def _parse_single_json_object(blobs: Sequence[Blob]) -> Any:
    """The one JSON body the read answered with.

    A resource read may carry several contents; this one answers with a single JSON object, so
    anything else is a server not meeting the contract rather than a case to merge.
    """
    if len(blobs) != 1:
        raise ValueError(f"expected one resource content, got {len(blobs)}")
    data = blobs[0].data
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if not isinstance(data, str):
        raise ValueError(f"expected text content, got {type(data).__name__}")
    return json.loads(data)
