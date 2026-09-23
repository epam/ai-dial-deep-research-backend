"""Unit tests for `ToolFailureMiddleware`, the verdicts it gives and the message it relays.

The retry loop is driven with a scripted handler, so these tests pin the attempt counts, the three
verdicts and the log records without an agent or an MCP server. `test_tool_failure_harness.py`
covers the same behaviour end to end.
"""

import inspect
import logging
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from langchain.agents.middleware import ToolRetryMiddleware, tool_retry
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from dial_deep_research.app.tool_failures import (
    RetryVerdict,
    ToolFailureMiddleware,
    retry_verdict,
)

# Shaped like the address a real transport failure names: an internal host and a deployment id.
_INTERNAL_URL = "http://internal-core.cluster.local:8080/v1/deployments/acme-rag-mcp/mcp"
_REQUEST = httpx.Request("POST", _INTERNAL_URL)


def _http_status_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    response = httpx.Response(status, request=_REQUEST, headers=headers)
    return httpx.HTTPStatusError(
        f"Server error '{status}' for url '{_INTERNAL_URL}'", request=_REQUEST, response=response
    )


def _connect_error() -> httpx.ConnectError:
    return httpx.ConnectError(f"connection refused by {_INTERNAL_URL}", request=_REQUEST)


# --- Verdicts -------------------------------------------------------------------------------------


def test_a_transport_failure_may_help_to_retry() -> None:
    assert retry_verdict(_connect_error()) is RetryVerdict.RETRY_NOW


def test_a_wrapped_502_may_help_to_retry() -> None:
    assert retry_verdict(ExceptionGroup("tg", [_http_status_error(502)])) is RetryVerdict.RETRY_NOW


def test_a_rate_limit_is_retried_later() -> None:
    assert retry_verdict(_http_status_error(429)) is RetryVerdict.RETRY_LATER


def test_server_errors_the_retry_skips_are_retried_later() -> None:
    assert retry_verdict(_http_status_error(500)) is RetryVerdict.RETRY_LATER
    assert retry_verdict(_http_status_error(504)) is RetryVerdict.RETRY_LATER


def test_a_rejected_request_will_not_help_to_retry() -> None:
    assert retry_verdict(_http_status_error(403)) is RetryVerdict.WILL_NOT_HELP


def test_a_read_timeout_will_not_help_to_retry() -> None:
    silent = httpx.ReadTimeout("silent", request=_REQUEST)
    assert retry_verdict(silent) is RetryVerdict.WILL_NOT_HELP
    assert retry_verdict(ExceptionGroup("tg", [silent])) is RetryVerdict.WILL_NOT_HELP


@pytest.mark.parametrize(
    "error",
    [
        httpx.UnsupportedProtocol("unsupported scheme", request=_REQUEST),
        httpx.LocalProtocolError("illegal header", request=_REQUEST),
        httpx.ProxyError("proxy refused the tunnel", request=_REQUEST),
    ],
)
def test_a_permanent_transport_error_will_not_help_to_retry(error: Exception) -> None:
    assert retry_verdict(error) is RetryVerdict.WILL_NOT_HELP


def test_an_unexpected_exception_will_not_help_to_retry() -> None:
    assert retry_verdict(KeyError("x")) is RetryVerdict.WILL_NOT_HELP


def test_one_permanent_cause_in_a_group_decides_the_verdict() -> None:
    mixed = ExceptionGroup("tg", [_connect_error(), _http_status_error(403)])
    assert retry_verdict(mixed) is RetryVerdict.WILL_NOT_HELP


# --- Driving the middleware -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_retry, "calculate_delay", lambda *args, **kwargs: 0.0)


def _request(tool_name: str = "rag_search") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_name, "args": {"query": "q"}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


class _ScriptedHandler:
    """Raises the scripted failures in order, then succeeds; counts every attempt."""

    def __init__(self, failures: list[Exception]) -> None:
        self._failures: Iterator[Exception] = iter(failures)
        self.attempts = 0

    async def __call__(self, request: ToolCallRequest) -> ToolMessage:
        self.attempts += 1
        failure = next(self._failures, None)
        if failure is not None:
            raise failure
        return ToolMessage(content="ok", tool_call_id=request.tool_call["id"], name="rag_search")


async def _run(failures: list[Exception]) -> tuple[Any, int]:
    handler = _ScriptedHandler(failures)
    result = await ToolFailureMiddleware().awrap_tool_call(_request(), handler)
    return result, handler.attempts


# --- The relayed message --------------------------------------------------------------------------


async def _relayed(error: Exception, *, tool_name: str = "rag_search") -> str:
    """The text the agent receives when every attempt fails with `error`."""
    handler = _ScriptedHandler([error] * 3)
    result = await ToolFailureMiddleware().awrap_tool_call(_request(tool_name=tool_name), handler)
    assert isinstance(result, ToolMessage)
    assert isinstance(result.content, str)
    return result.content


async def test_the_message_names_the_tool_the_failure_and_the_status() -> None:
    text = await _relayed(_http_status_error(502))
    assert "`rag_search`" in text
    assert "HTTPStatusError" in text
    assert "HTTP status 502" in text
    assert "retrying may help" in text


async def test_a_wrapped_failure_is_named_by_what_the_group_holds() -> None:
    text = await _relayed(ExceptionGroup("tg", [_http_status_error(502)]))
    assert "HTTPStatusError (HTTP status 502)" in text
    assert "ExceptionGroup" not in text
    assert "TaskGroup" not in text


async def test_a_rate_limit_says_to_come_back_and_allows_a_direct_repeat() -> None:
    text = await _relayed(
        _http_status_error(429, headers={"Retry-After": "37"}), tool_name="query_datasets"
    )
    assert "retry later" in text
    assert "rate limited" in text
    assert "Gather other evidence first" in text
    assert "you may call it again now" in text
    assert "37" not in text


async def test_a_server_error_says_to_come_back_without_claiming_a_rate_limit() -> None:
    text = await _relayed(_http_status_error(504), tool_name="query_datasets")
    assert "retry later" in text
    assert "rate limited" not in text
    assert "you may call it again now" in text


async def test_a_group_holding_a_rate_limit_gets_the_rate_limit_advice() -> None:
    """The advice follows every cause, not the first one, which here carries no status."""
    mixed = ExceptionGroup("tg", [_connect_error(), _http_status_error(429)])
    text = await _relayed(mixed, tool_name="query_datasets")
    assert "retry later" in text
    assert "rate limited" in text
    assert "server failed" not in text


async def test_a_rejected_request_says_not_to_repeat_the_call() -> None:
    text = await _relayed(_http_status_error(403), tool_name="query_datasets")
    assert "retrying will not help" in text
    assert "Do not call this tool again" in text


async def test_a_failure_without_a_status_carries_none() -> None:
    text = await _relayed(_connect_error())
    assert "ConnectError" in text
    assert "HTTP status" not in text


@pytest.mark.parametrize(
    "error",
    [
        _http_status_error(502),
        _http_status_error(429),
        _http_status_error(403),
        _connect_error(),
        ExceptionGroup("tg", [_http_status_error(502)]),
        RuntimeError(f"unexpected failure calling {_INTERNAL_URL}"),
    ],
)
async def test_no_relayed_message_carries_an_endpoint(error: Exception) -> None:
    text = await _relayed(error)
    assert "://" not in text
    assert "internal-core" not in text
    assert "cluster.local" not in text
    assert "acme-rag-mcp" not in text
    assert "/v1/deployments" not in text


# --- The retry loop -------------------------------------------------------------------------------


async def test_a_502_is_attempted_three_times_then_relayed() -> None:
    result, attempts = await _run([_http_status_error(502)] * 3)

    assert attempts == 3
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert result.name == "rag_search"
    assert "retrying may help" in result.content


async def test_a_429_is_attempted_once_and_relayed() -> None:
    result, attempts = await _run([_http_status_error(429)])

    assert attempts == 1
    assert result.status == "error"
    assert "retry later" in result.content


async def test_a_permanent_transport_error_is_attempted_once_and_relayed() -> None:
    result, attempts = await _run([httpx.UnsupportedProtocol("no scheme", request=_REQUEST)])

    assert attempts == 1
    assert "retrying will not help" in result.content


async def test_a_403_is_attempted_once_and_relayed() -> None:
    result, attempts = await _run([_http_status_error(403)])

    assert attempts == 1
    assert "retrying will not help" in result.content


async def test_a_retry_that_succeeds_returns_the_tool_result() -> None:
    result, attempts = await _run([_connect_error()])

    assert attempts == 2
    assert result.status == "success"
    assert result.content == "ok"


async def test_a_retry_that_succeeds_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.tool_failures")

    await _run([_http_status_error(502)])

    records = [r.getMessage() for r in caplog.records]
    assert records == [
        "Retrying tool call: tool=rag_search failure=HTTPStatusError status=502 attempt=2"
    ]


async def test_a_relayed_failure_logs_every_retry_and_the_relay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.tool_failures")

    await _run([_connect_error()] * 3)

    assert [r.levelno for r in caplog.records] == [logging.WARNING] * 3
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0].endswith("failure=ConnectError status=None attempt=2")
    assert messages[1].endswith("failure=ConnectError status=None attempt=3")
    assert messages[2] == (
        "Tool call failed and was relayed to the agent: tool=rag_search failure=ConnectError "
        "status=None attempts_made=3 verdict=RETRY_NOW"
    )


async def test_log_records_carry_no_arguments_and_no_failure_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dial_deep_research.app.tool_failures")

    await _run([_http_status_error(502)] * 3)

    for record in caplog.records:
        text = record.getMessage()
        assert "internal-core" not in text
        assert "query" not in text
        assert "Server error" not in text


async def test_a_read_timeout_is_attempted_once_and_relayed() -> None:
    result, attempts = await _run([httpx.ReadTimeout("silent", request=_REQUEST)])

    assert attempts == 1
    assert "ReadTimeout" in result.content
    assert "retrying will not help" in result.content


# --- Agreement with the prebuilt's retry loop -----------------------------------------------------


@pytest.mark.parametrize(
    ("failures", "expected_attempts", "relayed"),
    [
        ([_http_status_error(502)], 2, False),
        ([_http_status_error(502)] * 3, 3, True),
        ([_http_status_error(429)], 1, True),
        ([_http_status_error(403)], 1, True),
        ([_connect_error()] * 2, 3, False),
    ],
)
async def test_the_log_records_agree_with_the_attempts_the_prebuilt_made(
    caplog: pytest.LogCaptureFixture,
    failures: list[Exception],
    expected_attempts: int,
    relayed: bool,
) -> None:
    """The retry records count the prebuilt's attempts, and the relay record carries its count.

    The prebuilt runs the retry loop and the subclass only observes it, so the attempts the
    handler saw, the attempt numbers the retry records carry, and the relay record's
    `attempts_made` must all agree. A change in how the prebuilt calls the handler fails here.
    """
    caplog.set_level(logging.WARNING, logger="dial_deep_research.app.tool_failures")

    _, attempts = await _run(failures)

    messages = [r.getMessage() for r in caplog.records]
    retry_records = [m for m in messages if m.startswith("Retrying tool call:")]
    relay_records = [m for m in messages if m.startswith("Tool call failed and was relayed")]
    assert attempts == expected_attempts
    # Each retry record names the attempt it starts: the second, then the third.
    retry_numbers = [int(re.findall(r"attempt=(\d+)", m)[-1]) for m in retry_records]
    assert retry_numbers == list(range(2, attempts + 1))
    if relayed:
        assert len(relay_records) == 1
        match = re.search(r"attempts_made=(\d+)", relay_records[0])
        assert match is not None
        assert int(match.group(1)) == attempts
    else:
        assert relay_records == []


def test_the_prebuilt_still_offers_the_failure_hook_the_subclass_overrides() -> None:
    """`_handle_failure` is private API of `ToolRetryMiddleware`; an upgrade may change it."""
    parameters = list(inspect.signature(ToolRetryMiddleware._handle_failure).parameters)
    assert parameters == ["self", "tool_name", "tool_call_id", "exc", "attempts_made"]


def test_the_sync_path_retries_and_relays_too() -> None:
    attempts = 0

    def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal attempts
        attempts += 1
        raise _http_status_error(503)

    result = ToolFailureMiddleware().wrap_tool_call(_request(), handler)

    assert attempts == 3
    assert isinstance(result, ToolMessage)
    assert "retrying may help" in result.content
