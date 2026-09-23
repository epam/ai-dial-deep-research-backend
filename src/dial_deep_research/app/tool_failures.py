"""What a failing tool call turns into: a retry, then an error result the agent can act on.

A tool call that raises would otherwise escape the tool node and end the turn, discarding the
results of the calls issued beside it. `ToolFailureMiddleware` catches it below the node's
fan-out, retries the failures a fresh attempt can fix, and relays the rest to the agent as an
error `ToolMessage` whose text the app composes. The tool's own exception text is never relayed:
a transport failure's message names the internal address of the service that failed, and the
relayed text reaches the model, the persisted conversation and the DIAL stage body alike.

A result the MCP server itself marks as an error does not raise and never reaches this module:
the adapter's error handler turns it into an error `ToolMessage` carrying the server's content.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, NamedTuple

import httpx
from langchain.agents.middleware import ToolRetryMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from dial_deep_research.app.error_resolution import (
    exception_leaves,
    is_immediately_retryable,
    is_transient_transport_error,
)

logger = logging.getLogger(__name__)

# Two retries, so three attempts for one call the agent made. The backoff is the prebuilt's
# default: about one second before the first retry and two before the second, with jitter.
TOOL_CALL_MAX_RETRIES = 2


class RetryVerdict(StrEnum):
    """What retrying a relayed failure can achieve. Each value is the label the agent reads."""

    RETRY_NOW = "retrying may help"
    RETRY_LATER = "retry later"
    WILL_NOT_HELP = "retrying will not help"


_RETRY_NOW_ADVICE = "Call the tool again if you still need this evidence."
_RATE_LIMITED_ADVICE = (
    "The tool is rate limited. Gather other evidence first, and come back to this tool afterwards "
    "if you still need it. If there is no other evidence left to gather, you may call it again now."
)
_SERVER_ERROR_ADVICE = (
    "The tool's server failed, and repeating the call at once is unlikely to help. Gather other "
    "evidence first, and come back to this tool afterwards if you still need it. If there is no "
    "other evidence left to gather, you may call it again now."
)
_WILL_NOT_HELP_ADVICE = (
    "Do not call this tool again for this evidence. Get it from another tool, or continue "
    "without it."
)


def _http_status(e: Exception) -> int | None:
    return e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None


def _may_clear_later(e: Exception) -> bool:
    """A failure that can clear given time: a transient transport failure, a rate limit, a 5xx."""
    if is_transient_transport_error(e):
        return True
    status = _http_status(e)
    return status is not None and (status == 429 or status >= 500)


def retry_verdict(e: Exception) -> RetryVerdict:
    """The verdict for a failure that is being relayed, decided on every failure a group holds.

    "Retrying may help" goes to the failures the in-process retries cover, once those retries
    are spent. "Retry later" goes to a rate limit and to the server errors an immediate repeat
    cannot help, such as 500 and 504: the same reasoning that excludes them from a retry seconds
    later makes one tens of seconds later worth attempting.
    """
    if is_immediately_retryable(e):
        return RetryVerdict.RETRY_NOW
    if all(_may_clear_later(leaf) for leaf in exception_leaves(e)):
        return RetryVerdict.RETRY_LATER
    return RetryVerdict.WILL_NOT_HELP


class _FailureSummary(NamedTuple):
    """What the relayed message and the log record say about one failure."""

    kind: str  # the class name of the first failure a group holds
    status: int | None  # that failure's HTTP status, if it has one
    verdict: RetryVerdict
    rate_limited: bool  # any failure in the group is a 429


def _failure_kind(e: Exception) -> tuple[str, int | None]:
    """The failure's class name and HTTP status, read off the first failure a group holds."""
    leaf = exception_leaves(e)[0]
    return type(leaf).__name__, _http_status(leaf)


def _summarize(e: Exception) -> _FailureSummary:
    kind, status = _failure_kind(e)
    return _FailureSummary(
        kind=kind,
        status=status,
        verdict=retry_verdict(e),
        rate_limited=any(_http_status(leaf) == 429 for leaf in exception_leaves(e)),
    )


def _render_failure_message(*, tool_name: str, summary: _FailureSummary) -> str:
    """The error result the agent receives: the tool, the failure kind, the status, a verdict.

    Composed only from those parts, never from the failure's own text, which can carry an
    internal endpoint or a deployment identifier.
    """
    if summary.verdict is RetryVerdict.RETRY_NOW:
        advice = _RETRY_NOW_ADVICE
    elif summary.verdict is RetryVerdict.RETRY_LATER:
        advice = _RATE_LIMITED_ADVICE if summary.rate_limited else _SERVER_ERROR_ADVICE
    else:
        advice = _WILL_NOT_HELP_ADVICE
    cause = (
        f"{summary.kind} (HTTP status {summary.status})"
        if summary.status is not None
        else summary.kind
    )
    return f"Tool `{tool_name}` failed: {cause}.\nVerdict: {summary.verdict}. {advice}"


class ToolFailureMiddleware(ToolRetryMiddleware):
    """Retry a failed tool call where a fresh attempt can fix it, then relay it to the agent.

    The prebuilt supplies the retry loop, the backoff and the pass-through of LangGraph's
    control-flow signals. This subclass adds what the prebuilt lacks: a relayed message that
    carries no internal detail, and a WARNING for every retry and every relayed failure — the
    only trace of either, since a retried call renders as one stage and one tool result.
    """

    def __init__(self) -> None:
        # `retry_on` is a callable because the failure arrives wrapped in an `ExceptionGroup`:
        # a tuple of types is matched with `isinstance` against the wrapper, which matches
        # nothing, and the retry would silently never happen.
        super().__init__(
            max_retries=TOOL_CALL_MAX_RETRIES,
            retry_on=is_immediately_retryable,
            on_failure="continue",
        )

    def _handle_failure(
        self, tool_name: str, tool_call_id: str | None, exc: Exception, attempts_made: int
    ) -> ToolMessage:
        summary = _summarize(exc)
        logger.warning(
            "Tool call failed and was relayed to the agent: tool=%s failure=%s status=%s "
            "attempts_made=%d verdict=%s",
            tool_name,
            summary.kind,
            summary.status,
            attempts_made,
            summary.verdict.name,
        )
        return ToolMessage(
            content=_render_failure_message(tool_name=tool_name, summary=summary),
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

    # Only the async hook is overridden, because every agent this middleware serves runs
    # asynchronously. A synchronous run falls back to the prebuilt's `wrap_tool_call`, which still
    # retries and relays through `_handle_failure` but writes no retry record.
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tracker = _AttemptTracker(tool_name=_tool_name(request))

        async def attempt(req: ToolCallRequest) -> ToolMessage | Command[Any]:
            tracker.start()
            try:
                return await handler(req)
            except Exception as exc:
                tracker.failed(exc)
                raise

        return await super().awrap_tool_call(request, attempt)


def _tool_name(request: ToolCallRequest) -> str:
    return request.tool.name if request.tool else request.tool_call["name"]


class _AttemptTracker:
    """Counts one tool call's attempts, logging each retry with the failure that caused it.

    The prebuilt's loop calls the handler once per attempt, so an attempt that starts after a
    failure is a retry. That holds whether the retry then succeeds or not, which is why the
    record is written here: a retry that succeeds never reaches `_handle_failure`.
    """

    def __init__(self, *, tool_name: str) -> None:
        self._tool_name = tool_name
        self._attempts = 0
        self._last_failure: tuple[str, int | None] | None = None

    def start(self) -> None:
        self._attempts += 1
        if self._last_failure is not None:
            kind, status = self._last_failure
            logger.warning(
                "Retrying tool call: tool=%s failure=%s status=%s attempt=%d",
                self._tool_name,
                kind,
                status,
                self._attempts,
            )

    def failed(self, exc: Exception) -> None:
        self._last_failure = _failure_kind(exc)
