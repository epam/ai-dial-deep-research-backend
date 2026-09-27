"""One MCP tool call of the data-sources fetch, and the attempts around it.

The fetch at the start of a turn calls tools by the names the configuration gives, so it reads the
MCP result itself rather than going through a LangChain tool: `MultiServerMCPClient.session()`
opens one initialized session, and `ClientSession.call_tool` returns the `CallToolResult`, whose
`isError` and `structuredContent` are all the fetch reads (see the data-sources-discovery
capability).

Every call opens a session of its own, so a failure that ends one session cannot fail another
call. The session open and the call run under one deadline of the app's own: the transport's read
timeout logs at DEBUG and leaves a call waiting (see `mcp_tools.py`), so without the deadline a
call that never returns would hold the turn before preparation starts.

`call_tool` validates a successful result against the tool's output schema, and on a fresh session
it first requests the tool list to learn that schema. That request is part of the call, under the
same deadline, and its failure is a failed attempt like any other.

Nothing here logs: the caller owns the one record per fetch, which carries counts and failure
kinds and never a tool's answer.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Mapping
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from dial_deep_research.app.error_resolution import exception_leaves

# How long one call may take, its session open included. A healthy call finishes within a few
# seconds, so this leaves a wide margin.
CALL_TIMEOUT_SECONDS = 20.0

# Attempts of one list call, or of one structure call: one call and two repeats.
MAX_ATTEMPTS = 3

# The failure kinds of a call that raised nothing. A call that raised is recorded by the class
# name of the first exception it holds, as the tool-call retry records it (`tool_failures.py`).
KIND_MCP_ERROR = "mcp_error"
KIND_TIMEOUT = "timeout"
KIND_INVALID_RESULT = "invalid_result"


class InvalidResultError(Exception):
    """Raised by a result reader for a structured result that lacks the shape the app reads."""


class CallFailedError(Exception):
    """One call that did not produce a usable result. `kind` is the token a log record carries."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class Attempts[T]:
    """The outcome of up to `MAX_ATTEMPTS` attempts of one call.

    `value` is the read result of the attempt that succeeded, or `None` when every attempt failed;
    `failure_kind` is then the kind of the last failure.
    """

    def __init__(self, *, value: T | None, attempts: int, failure_kind: str | None) -> None:
        self.value = value
        self.attempts = attempts
        self.failure_kind = failure_kind


def retry_delay(retry_number: int) -> float:
    """The delay before retry `retry_number` (0-based): about 1 s, then about 2 s, ±25% jitter.

    The same backoff the tool-call retry uses (`tool_failures.py`), so two attempts never test the
    same conditions a few milliseconds apart.
    """
    delay = 2.0**retry_number
    return max(0.0, delay + random.uniform(-delay * 0.25, delay * 0.25))  # noqa: S311


async def sleep(seconds: float) -> None:
    """The pause between attempts. A module function so a test can make it instant."""
    await asyncio.sleep(seconds)


async def pause_before_retry(retry_number: int) -> None:
    """Wait the `retry_delay` before retry `retry_number` (0-based)."""
    await sleep(retry_delay(retry_number))


async def call_once[T](
    client: MultiServerMCPClient,
    *,
    server_name: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    read: Callable[[Any], T],
) -> T:
    """Call the tool once in a session of its own and read its structured result.

    `read` receives `CallToolResult.structuredContent` and returns what the caller keeps; it raises
    `InvalidResultError` for a result without the shape the caller reads.

    Raises:
        CallFailedError: the call raised, returned an MCP error, did not finish by its deadline, or
            returned no structured result `read` accepts. `asyncio.CancelledError` is never
            caught, so a cancelled turn stops here.
    """
    try:
        async with asyncio.timeout(CALL_TIMEOUT_SECONDS):
            async with client.session(server_name) as session:
                result = await session.call_tool(tool_name, dict(arguments))
    except TimeoutError as error:
        raise CallFailedError(KIND_TIMEOUT) from error
    except Exception as error:
        raise CallFailedError(type(exception_leaves(error)[0]).__name__) from error
    if result.isError:
        raise CallFailedError(KIND_MCP_ERROR)
    if result.structuredContent is None:
        raise CallFailedError(KIND_INVALID_RESULT)
    try:
        return read(result.structuredContent)
    except InvalidResultError as error:
        raise CallFailedError(KIND_INVALID_RESULT) from error


async def call_with_attempts[T](
    client: MultiServerMCPClient,
    *,
    server_name: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    read: Callable[[Any], T],
) -> Attempts[T]:
    """Call the tool until one attempt succeeds, making at most `MAX_ATTEMPTS`.

    Every kind of failure is retried, with the `retry_delay` backoff between attempts. A
    cancellation is not a failure: it propagates at once and no further attempt is made.
    """
    failure_kind: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            await pause_before_retry(attempt - 2)
        try:
            value = await call_once(
                client, server_name=server_name, tool_name=tool_name, arguments=arguments, read=read
            )
        except CallFailedError as failure:
            failure_kind = failure.kind
            continue
        return Attempts(value=value, attempts=attempt, failure_kind=None)
    return Attempts(value=None, attempts=MAX_ATTEMPTS, failure_kind=failure_kind)
