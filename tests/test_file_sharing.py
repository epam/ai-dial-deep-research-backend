"""Calling the file-sharing tool and reading the URLs it answers with.

The tools here are real LangChain `StructuredTool`s built the way `langchain-mcp-adapters`
builds them — `response_format="content_and_artifact"`, the structured result in the artifact —
so these tests exercise how a mapping actually reaches the app rather than a stand-in for it.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from dial_deep_research.app.research.file_sharing import (
    KIND_NO_STRUCTURED_RESULT,
    KIND_UNREADABLE_RESULT,
    FileSharingError,
    share_documents,
)

_URL = "files/bucket/appdata/deep-research/docs/outlook.pdf"


def _sharing_tool(
    *,
    artifact: Any = None,
    raises: Exception | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> BaseTool:
    async def share(document_ids: list[int]) -> tuple[str, Any]:
        if calls is not None:
            calls.append({"document_ids": document_ids})
        if raises is not None:
            raise raises
        return "the mapping, serialized as text", artifact

    return StructuredTool.from_function(
        coroutine=share,
        name="share_documents",
        description="Copy each document into the caller's storage and return its URL.",
        response_format="content_and_artifact",
    )


async def test_the_reported_urls_are_read_off_the_structured_result() -> None:
    tool = _sharing_tool(artifact={"structured_content": {"442": _URL}})

    assert await share_documents(tool=tool, document_ids=[442]) == {442: _URL}


async def test_the_ids_go_out_as_integers_under_the_contracted_argument() -> None:
    calls: list[dict[str, Any]] = []
    tool = _sharing_tool(artifact={"structured_content": {}}, calls=calls)

    await share_documents(tool=tool, document_ids=[442, 12])

    assert calls == [{"document_ids": [442, 12]}]


async def test_a_plain_argument_call_would_lose_the_structured_result() -> None:
    """Why the call is tool-call-shaped: no tool-call id, no `ToolMessage`, no artifact."""
    tool = _sharing_tool(artifact={"structured_content": {"442": _URL}})

    plain = await tool.ainvoke({"document_ids": [442]})
    tool_call_shaped = await tool.ainvoke(
        {"name": tool.name, "args": {"document_ids": [442]}, "id": "c1", "type": "tool_call"}
    )

    assert not isinstance(plain, ToolMessage)
    assert isinstance(tool_call_shaped, ToolMessage)
    assert tool_call_shaped.artifact == {"structured_content": {"442": _URL}}


async def test_a_partial_response_reports_only_the_ids_it_resolved() -> None:
    """An id the server cannot resolve is absent, and the call still succeeds."""
    tool = _sharing_tool(artifact={"structured_content": {"442": _URL}})

    assert await share_documents(tool=tool, document_ids=[442, 9]) == {442: _URL}


async def test_no_structured_result_is_a_failed_call() -> None:
    """MCP sends one only for a tool that declares an output schema, as the contract requires."""
    tool = _sharing_tool(artifact=None)

    with pytest.raises(FileSharingError) as excinfo:
        await share_documents(tool=tool, document_ids=[442])

    assert excinfo.value.kind == KIND_NO_STRUCTURED_RESULT


async def test_a_structured_result_that_is_not_a_mapping_is_a_failed_call() -> None:
    tool = _sharing_tool(artifact={"structured_content": {"documents": ["a list, not a map"]}})

    with pytest.raises(FileSharingError) as excinfo:
        await share_documents(tool=tool, document_ids=[442])

    assert excinfo.value.kind == KIND_UNREADABLE_RESULT


async def test_a_raising_tool_raises() -> None:
    """Error handling is off on this tool, so the failure reaches the caller."""
    tool = _sharing_tool(raises=RuntimeError("the server said no"))

    with pytest.raises(RuntimeError):
        await share_documents(tool=tool, document_ids=[442])


async def test_either_key_form_is_read_as_the_integer_ids_the_report_cites() -> None:
    """JSON has no integer keys, so the contract accepts either form."""
    tool = _sharing_tool(artifact={"structured_content": {"442": _URL, 12: _URL}})

    assert await share_documents(tool=tool, document_ids=[442, 12]) == {442: _URL, 12: _URL}
