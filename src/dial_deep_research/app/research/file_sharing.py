"""Calling the configured file-sharing tool, and reading the URLs it answers with.

A cited document lives in the retrieval server's own DIAL storage, which the person reading the
report cannot read. The file-sharing tool copies it into that person's own storage and answers
with the URL of the copy, which is what a citation can point at. The contract the tool must
satisfy — one `document_ids` argument, a top-level id-to-URL object as its structured result,
absent ids allowed — is stated by the report-citations capability; this module depends on
nothing else about it.

Every failure here is one exception carrying a `kind`, the token the citation step's warning
reports. Nothing in this module logs: the response is a tool response body, and the caller owns
what may be said about it (counts, never a URL).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic import TypeAdapter, ValidationError

# The one argument the contract fixes, so the app needs no per-server mapping.
DOCUMENT_IDS_ARGUMENT = "document_ids"

# Failure kinds, as they appear in the citation step's warnings.
KIND_NO_STRUCTURED_RESULT = "no_structured_result"
KIND_UNREADABLE_RESULT = "unreadable_result"


# The tool's answer: the DIAL file URL of the copy of each document it shared. The mapping is
# the whole response object, with no wrapper key, so the type is validated directly rather than
# through a model wrapping it. Keys arrive as JSON strings — JSON has no integer keys — and are
# read back as the integer document ids the report's citation markers carry. The validation is
# what turns a response of some other shape into the specified failure path instead of a URL
# the app would carry into an annotation.
_ID_TO_URL = TypeAdapter(dict[int, str])


class FileSharingError(Exception):
    """The call did not produce a readable id-to-URL mapping.

    `kind` is the stable token the citation step's warning carries. The message says no more
    than the kind: a record about this call may name counts and the tool, never a URL.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


async def share_documents(*, tool: BaseTool, document_ids: Sequence[int]) -> dict[int, str]:
    """Ask the tool to share every one of these documents, and return the URLs it reported.

    An id the tool could not resolve is simply absent from the result; the caller decides what
    that costs. Ids go out as integers, the type the contract's `document_ids` array takes.

    The tool is invoked **tool-call-shaped** rather than with plain arguments, and that shape is
    load-bearing: `langchain_core.tools.base._format_output` builds no `ToolMessage` when the
    input carries no tool-call id, so a plain-argument call returns the content alone and the
    structured result — which travels in the `ToolMessage`'s artifact — becomes unreachable.

    Raises:
        FileSharingError: the call returned no structured result, or one that is not an
            id-to-URL mapping.
        Exception: whatever the tool call itself raised. Error handling is disabled on this
            tool (see `load_mcp_tools`), so an MCP error reaches the caller as an exception
            instead of being delivered as ordinary result content.
    """
    result = await tool.ainvoke(
        {
            "name": tool.name,
            "args": {DOCUMENT_IDS_ARGUMENT: [int(document_id) for document_id in document_ids]},
            "id": f"file-sharing-{uuid.uuid4().hex}",
            "type": "tool_call",
        }
    )
    artifact = result.artifact if isinstance(result, ToolMessage) else None
    if not isinstance(artifact, dict) or "structured_content" not in artifact:
        # No structured result: MCP sends one only for a tool that declares an output schema,
        # which the contract requires. The text copy of the mapping MCP also carries is
        # deliberately not read — a second read path, for a case no server we can test against
        # produces, would decide silently which copy an answer came from.
        raise FileSharingError(KIND_NO_STRUCTURED_RESULT)
    try:
        return _ID_TO_URL.validate_python(artifact["structured_content"])
    except ValidationError as error:
        raise FileSharingError(KIND_UNREADABLE_RESULT) from error
