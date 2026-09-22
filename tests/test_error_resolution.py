"""Unit tests for the failure resolver (`app/error_resolution.py`).

Covers extraction from each supported exception shape, the resolution precedence, retryability
classification, and the no-leak guarantee.
"""

import logging
import re
import time

import anyio
import httpx
import openai
import pytest
from aidial_sdk.exceptions import HTTPException as AiDialHTTPException
from langgraph.errors import GraphRecursionError

from dial_deep_research.app.error_resolution import (
    ApplicationNotConfiguredError,
    ResearchAlreadyHandedOffError,
    _extract_error_details,
    exception_leaves,
    is_immediately_retryable,
    raise_dial_error,
    resolve_exception,
)

_REQUEST = httpx.Request("POST", "https://core.example/openai")


def _openai_status_error(status: int, body: dict) -> openai.APIStatusError:
    response = httpx.Response(status, request=_REQUEST, json=body)
    return openai.BadRequestError("boom", response=response, body=body.get("error", body))


def _openai_midstream_error(body: dict | None) -> openai.APIError:
    # A plain APIError with no HTTP status — how the openai SDK surfaces a DIAL mid-stream error.
    return openai.APIError("stream died", request=_REQUEST, body=body)


# --- Extraction ---------------------------------------------------------------------------------


def test_extract_openai_unwraps_nested_error_body() -> None:
    err = _openai_status_error(
        400, {"error": {"code": "content_filter", "type": "invalid_request_error", "message": "no"}}
    )
    details = _extract_error_details(err)
    assert details.status_code == 400
    assert details.code == "content_filter"
    assert details.error_type == "invalid_request_error"


def test_extract_midstream_backfills_status_from_numeric_code() -> None:
    details = _extract_error_details(_openai_midstream_error({"code": "429", "message": "slow"}))
    # No HTTP status on a plain APIError; the numeric code backfills it.
    assert details.status_code == 429
    assert details.code == "429"


def test_extract_aidial_reads_native_attributes() -> None:
    err = AiDialHTTPException(
        message="internal", status_code=503, code="503", display_message="Service is down"
    )
    details = _extract_error_details(err)
    assert details.status_code == 503
    assert details.display_message == "Service is down"


def test_extract_is_total_on_garbage_body() -> None:
    # Best-effort: a non-dict body must not raise.
    details = _extract_error_details(_openai_midstream_error("not-a-dict"))  # type: ignore[arg-type]
    assert details.status_code is None
    assert details.code is None


# --- Precedence ---------------------------------------------------------------------------------


def test_display_message_wins_and_is_not_retry_suffixed() -> None:
    err = _openai_status_error(
        502, {"error": {"display_message": "Daily token budget exhausted for this key."}}
    )
    resolved = resolve_exception(err)
    assert resolved.message == "Daily token budget exhausted for this key."
    assert "try again later" not in resolved.message.lower()


def test_display_message_is_length_capped() -> None:
    long = "x" * 900
    resolved = resolve_exception(_openai_status_error(500, {"error": {"display_message": long}}))
    assert len(resolved.message) <= 500
    assert resolved.message.endswith("…")


def test_code_map_beats_status_ladder() -> None:
    err = _openai_status_error(400, {"error": {"code": "context_length_exceeded"}})
    resolved = resolve_exception(err)
    assert "context length" in resolved.message.lower()
    assert resolved.retryable is False


def test_content_filter_code_is_actionable() -> None:
    resolved = resolve_exception(_openai_status_error(400, {"error": {"code": "content_filter"}}))
    assert "content management policy" in resolved.message
    assert resolved.retryable is False


def test_midstream_without_usable_body_hits_stream_failure_rule() -> None:
    resolved = resolve_exception(_openai_midstream_error(None))
    assert "failed while responding" in resolved.message
    assert resolved.retryable is True
    assert resolved.message.endswith("Please try again later.")


def test_unknown_exception_falls_back() -> None:
    resolved = resolve_exception(RuntimeError("surprise"))
    assert "Something went wrong" in resolved.message
    assert resolved.retryable is False


# --- Retryability & source-specific wording -----------------------------------------------------


def test_rate_limit_is_retryable_with_single_suffix() -> None:
    resolved = resolve_exception(_openai_status_error(429, {"error": {"code": "429"}}))
    assert resolved.retryable is True
    assert resolved.message.count("Please try again later.") == 1


def test_openai_connection_error_is_non_retryable() -> None:
    resolved = resolve_exception(openai.APIConnectionError(request=_REQUEST))
    assert resolved.retryable is False
    assert "try again later" not in resolved.message.lower()


def test_aidial_error_uses_service_wording() -> None:
    err = AiDialHTTPException(message="core down", status_code=503, code="503")
    resolved = resolve_exception(err)
    assert "required service" in resolved.message
    assert resolved.retryable is True


def test_httpx_network_error_is_service_retryable() -> None:
    resolved = resolve_exception(httpx.ConnectError("no route", request=_REQUEST))
    assert "network error" in resolved.message.lower()
    assert resolved.retryable is True


def test_httpx_remote_protocol_error_is_service_retryable() -> None:
    # A connection dropped mid-stream (incomplete chunked read) is transient.
    resolved = resolve_exception(
        httpx.RemoteProtocolError("peer closed connection", request=_REQUEST)
    )
    assert "network error" in resolved.message.lower()
    assert resolved.retryable is True


def test_httpx_read_error_is_service_retryable() -> None:
    # The reset flavor of a mid-stream drop; a NetworkError subclass.
    resolved = resolve_exception(httpx.ReadError("connection reset", request=_REQUEST))
    assert "network error" in resolved.message.lower()
    assert resolved.retryable is True


def test_httpx_local_protocol_error_stays_non_retryable() -> None:
    # A client-side protocol bug — retrying will not change the outcome.
    resolved = resolve_exception(httpx.LocalProtocolError("bad framing", request=_REQUEST))
    assert resolved.retryable is False


# --- Internal conditions ------------------------------------------------------------------------


def test_application_not_configured_maps_to_no_status() -> None:
    resolved = resolve_exception(ApplicationNotConfiguredError())
    assert "not configured" in resolved.message
    assert resolved.retryable is False
    assert resolved.details.status_code is None


def test_research_already_handed_off_carries_409() -> None:
    resolved = resolve_exception(ResearchAlreadyHandedOffError())
    assert "new conversation" in resolved.message
    assert resolved.retryable is False
    assert resolved.details.status_code == 409


def test_graph_recursion_error_maps_to_step_budget() -> None:
    resolved = resolve_exception(GraphRecursionError("limit"))
    assert "step budget" in resolved.message
    assert resolved.retryable is False


# --- No-leak guarantee --------------------------------------------------------------------------


def test_internal_message_never_leaks_into_user_text() -> None:
    secret = "Traceback: connect to https://internal.host:5432 failed"
    err = _openai_status_error(500, {"error": {"message": secret, "code": "500"}})
    resolved = resolve_exception(err)
    assert secret not in resolved.message
    assert "internal.host" not in resolved.message
    # The internal message is retained on details for the log record only.
    assert resolved.details.message == secret


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_retriable_statuses_stay_retryable_but_are_downgraded_by_the_handler(status: int) -> None:
    # The resolver classifies these retryable; the *outgoing status* downgrade to 500 is the
    # handler's job (see test_error_delivery). Here we only assert the classification + code.
    resolved = resolve_exception(_openai_status_error(status, {"error": {"code": str(status)}}))
    assert resolved.retryable is True
    assert resolved.details.code == str(status)


# --- The failure records (logging-policy: single ERROR + skeleton completion event) --------------


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    response = httpx.Response(status, request=_REQUEST)
    return httpx.HTTPStatusError(
        f"Server error for url '{_REQUEST.url}'", request=_REQUEST, response=response
    )


async def _raised_by_a_task_group(error: Exception) -> Exception:
    """The exception a real anyio task group raises when its one task fails with `error`."""

    async def fail() -> None:
        raise error

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(fail)
    except Exception as wrapped:
        return wrapped
    raise AssertionError("the task group did not raise")


# --- Wrapped failures ---------------------------------------------------------------------------


async def test_a_task_group_wrapped_502_resolves_to_the_retryable_service_message() -> None:
    wrapped = await _raised_by_a_task_group(_http_status_error(502))
    assert isinstance(wrapped, ExceptionGroup)

    resolved = resolve_exception(wrapped)

    assert resolved.message == resolve_exception(_http_status_error(502)).message
    assert "internal error" in resolved.message
    assert resolved.retryable is True
    assert resolved.details.status_code == 502


def test_a_wrapped_transport_failure_is_matched_by_its_own_type() -> None:
    wrapped = ExceptionGroup("tg", [httpx.ConnectTimeout("slow", request=_REQUEST)])
    resolved = resolve_exception(wrapped)
    assert "timed out" in resolved.message
    assert resolved.retryable is True


def test_a_wrapped_midstream_llm_failure_reaches_the_stream_failure_rule() -> None:
    wrapped = ExceptionGroup("tg", [_openai_midstream_error(None)])
    resolved = resolve_exception(wrapped)
    assert "failed while responding" in resolved.message
    assert resolved.retryable is True


def test_nested_groups_resolve_to_the_innermost_failure() -> None:
    wrapped = ExceptionGroup("outer", [ExceptionGroup("inner", [_http_status_error(403)])])
    resolved = resolve_exception(wrapped)
    assert "permission" in resolved.message
    assert resolved.retryable is False


def test_a_group_of_several_is_resolved_by_its_first_failure() -> None:
    wrapped = ExceptionGroup("tg", [_http_status_error(403), _http_status_error(502)])
    resolved = resolve_exception(wrapped)
    assert resolved.details.status_code == 403
    assert resolved.retryable is False


def test_exception_leaves_flattens_nested_groups_in_order() -> None:
    first, second, third = ValueError("a"), KeyError("b"), TypeError("c")
    wrapped = ExceptionGroup("outer", [first, ExceptionGroup("inner", [second, third])])
    assert exception_leaves(wrapped) == [first, second, third]


def test_exception_leaves_returns_a_plain_failure_unchanged() -> None:
    error = ValueError("a")
    assert exception_leaves(error) == [error]


# --- Immediate-retry predicate ------------------------------------------------------------------


async def test_a_task_group_wrapped_502_is_immediately_retryable() -> None:
    assert is_immediately_retryable(await _raised_by_a_task_group(_http_status_error(502))) is True


def test_a_503_is_immediately_retryable() -> None:
    assert is_immediately_retryable(_http_status_error(503)) is True


def test_transport_failures_are_immediately_retryable() -> None:
    assert is_immediately_retryable(httpx.ConnectError("refused", request=_REQUEST)) is True
    assert is_immediately_retryable(httpx.ConnectTimeout("slow", request=_REQUEST)) is True
    assert is_immediately_retryable(httpx.ReadError("reset", request=_REQUEST)) is True
    assert is_immediately_retryable(httpx.RemoteProtocolError("closed", request=_REQUEST)) is True


def test_permanent_transport_errors_are_not_immediately_retryable() -> None:
    assert is_immediately_retryable(httpx.UnsupportedProtocol("scheme", request=_REQUEST)) is False
    assert is_immediately_retryable(httpx.LocalProtocolError("header", request=_REQUEST)) is False
    assert is_immediately_retryable(httpx.ProxyError("tunnel", request=_REQUEST)) is False


def test_a_read_timeout_is_not_immediately_retryable() -> None:
    """Nothing arrived for the whole read bound: a repeat would wait it out again."""
    assert is_immediately_retryable(httpx.ReadTimeout("silent", request=_REQUEST)) is False
    wrapped = ExceptionGroup("tg", [httpx.ReadTimeout("silent", request=_REQUEST)])
    assert is_immediately_retryable(wrapped) is False


def test_a_429_is_not_immediately_retryable_though_it_resolves_retryable() -> None:
    """The two questions differ: "retry now" is no, "try again later" is yes."""
    assert is_immediately_retryable(_http_status_error(429)) is False
    assert resolve_exception(_http_status_error(429)).retryable is True


def test_500_and_504_are_not_immediately_retryable() -> None:
    assert is_immediately_retryable(_http_status_error(500)) is False
    assert is_immediately_retryable(_http_status_error(504)) is False


def test_a_rejected_request_is_not_immediately_retryable() -> None:
    assert is_immediately_retryable(_http_status_error(403)) is False


def test_a_non_http_failure_is_not_immediately_retryable() -> None:
    assert is_immediately_retryable(KeyError("x")) is False


def test_a_group_is_immediately_retryable_only_when_every_failure_is() -> None:
    connect_error = httpx.ConnectError("refused", request=_REQUEST)
    mixed = ExceptionGroup("tg", [connect_error, _http_status_error(403)])
    uniform = ExceptionGroup("tg", [connect_error, _http_status_error(502)])
    assert is_immediately_retryable(mixed) is False
    assert is_immediately_retryable(uniform) is True


def test_raise_dial_error_closes_skeleton_with_matching_reference(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="dial_deep_research.app.error_resolution")
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        with pytest.raises(AiDialHTTPException):
            raise_dial_error(e, started_at=time.monotonic())

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(errors) == 1
    assert len(infos) == 1
    match = re.search(r"error_reference=(\w{8})", errors[0].getMessage())
    assert match is not None
    completion = infos[0].getMessage()
    assert "Request completed: outcome=failed" in completion
    assert f"error_reference={match.group(1)}" in completion
