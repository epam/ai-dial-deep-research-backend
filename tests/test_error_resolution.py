"""Unit tests for the failure resolver (`app/error_resolution.py`).

Covers extraction from each supported exception shape, the resolution precedence, retryability
classification, and the no-leak guarantee.
"""

import httpx
import openai
import pytest
from aidial_sdk.exceptions import HTTPException as AiDialHTTPException
from langgraph.errors import GraphRecursionError

from dial_deep_research.app.error_resolution import (
    ApplicationNotConfiguredError,
    ResearchAlreadyHandedOffError,
    _extract_error_details,
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
