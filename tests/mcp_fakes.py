"""Test stand-ins for a channel's MCP side.

A `MultiServerMCPClient` the data-sources fetch can open sessions on, and the kinds of source a
channel with both a document server and a dataset server has.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.types import CallToolResult, TextContent

from dial_deep_research.app_properties import SourceKind

# The kinds of source a channel with both a document server and a dataset server has.
BOTH_SOURCE_KINDS: frozenset[SourceKind] = frozenset({"document", "dataset"})

# A handler receives one call's arguments and returns the result, raises, or never returns.
Handler = Callable[[dict[str, Any]], CallToolResult | Awaitable[CallToolResult]]


def structured(value: Any) -> CallToolResult:
    """A successful result carrying `value` as its structured content, as StatGPT sends one.

    Built without validation, because `mcp` refuses structured content that is not an object
    while parsing the response, and a test needs to hand the app such a value to check its own
    rule.
    """
    return CallToolResult.model_construct(
        content=[TextContent(type="text", text="as JSON")],
        structuredContent=value,
        isError=False,
    )


def mcp_error(text: str = "the server refused") -> CallToolResult:
    """A result the server marks as an error."""
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


class FakeMcpServer:
    """Answers each tool by its handler and records every call, session by session."""

    def __init__(self, handlers: dict[str, Handler]) -> None:
        self._handlers = handlers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sessions = 0

    def calls_of(self, tool_name: str) -> list[dict[str, Any]]:
        return [arguments for name, arguments in self.calls if name == tool_name]

    @asynccontextmanager
    async def session(self, server_name: str) -> AsyncIterator[FakeMcpServer]:
        self.sessions += 1
        yield self

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((name, arguments))
        result = self._handlers[name](arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    def client(self) -> MultiServerMCPClient:
        return cast(MultiServerMCPClient, self)


def failing_first(times: int, then: Handler, error: Exception | None = None) -> Handler:
    """A handler that raises for its first `times` calls, then answers as `then` does."""
    count = 0

    def handler(arguments: dict[str, Any]) -> CallToolResult | Awaitable[CallToolResult]:
        nonlocal count
        count += 1
        if count <= times:
            raise error or RuntimeError("HTTP 502 from the gateway")
        return then(arguments)

    return handler
