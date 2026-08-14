"""Unit tests for the in-app retry of transient LLM stream drops.

Covers the shared retry helpers in `utils/llm.py` and the report node, which retries its
one long call through `with_stream_drop_retry`.
"""

from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableLambda

from dial_deep_research.app.research import nodes
from dial_deep_research.app_properties import DEFAULT_REPORT_STRUCTURE
from dial_deep_research.utils import llm as llm_module
from dial_deep_research.utils.llm import (
    STREAM_DROP_MAX_ATTEMPTS,
    STREAM_DROP_MAX_RETRIES,
    TRANSIENT_STREAM_DROP_ERRORS,
    stream_drop_retry_middleware,
    with_stream_drop_retry,
)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "_STREAM_DROP_INITIAL_DELAY", 0.01)


# --- with_stream_drop_retry ---------------------------------------------------------------------


async def test_recovers_from_a_single_stream_drop() -> None:
    calls: list[int] = []

    async def flaky(_: str) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("peer closed connection")
        return "ok"

    runnable = with_stream_drop_retry(RunnableLambda(flaky))
    assert await runnable.ainvoke("x") == "ok"
    assert len(calls) == 2


async def test_reraises_after_budget_exhausted() -> None:
    calls: list[int] = []

    async def always_dropping(_: str) -> str:
        calls.append(1)
        raise httpx.RemoteProtocolError("peer closed connection")

    runnable = with_stream_drop_retry(RunnableLambda(always_dropping))
    with pytest.raises(httpx.RemoteProtocolError):
        await runnable.ainvoke("x")
    assert len(calls) == STREAM_DROP_MAX_ATTEMPTS


async def test_non_transient_errors_are_not_retried() -> None:
    calls: list[int] = []

    async def failing(_: str) -> str:
        calls.append(1)
        raise ValueError("bad")

    runnable = with_stream_drop_retry(RunnableLambda(failing))
    with pytest.raises(ValueError):
        await runnable.ainvoke("x")
    assert len(calls) == 1


# --- agent middleware factory -------------------------------------------------------------------


def test_middleware_reraises_on_exhaustion_and_uses_shared_budget() -> None:
    middleware = stream_drop_retry_middleware()
    assert middleware.max_retries == STREAM_DROP_MAX_RETRIES
    assert middleware.retry_on == TRANSIENT_STREAM_DROP_ERRORS
    # "error" re-raises the exhausted failure so it reaches the DIAL error protocol
    # instead of being injected as synthetic model output.
    assert middleware.on_failure == "error"


# --- report node ---------------------------------------------------------------------------------


def _report_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "plans": [["step one"]],
        "messages": [],
        "original_query": "q",
        "research_iteration": 1,
        "report": None,
        "report_revision_instruction": None,
        "report_version": 0,
        "report_revision_failed": False,
    }
    return {**state, **overrides}


def _make_report_node() -> Any:
    return nodes.make_report_node(
        "2026-07-16", DEFAULT_REPORT_STRUCTURE, 2750, emit_activity=lambda _title: None
    )


class _FlakyReportLLM:
    """Drops the connection on the first attempt; returns the report on every attempt after."""

    def __init__(self, *, always_drops: bool = False) -> None:
        self.attempts = 0
        self._always_drops = always_drops

    async def __call__(self, messages: list[BaseMessage]) -> AIMessage:
        self.attempts += 1
        if self._always_drops or self.attempts == 1:
            raise httpx.RemoteProtocolError("peer closed connection")
        return AIMessage(content="full report")


def _patch_report_llm(monkeypatch: pytest.MonkeyPatch, llm: _FlakyReportLLM) -> None:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: RunnableLambda(llm))


async def test_report_node_retries_a_dropped_call(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _FlakyReportLLM()
    _patch_report_llm(monkeypatch, llm)

    report = _make_report_node()
    result = await report(_report_state())  # type: ignore[arg-type]

    assert llm.attempts == 2
    assert result["report"] == "full report"
    # Drafts stay out of the transcript; the runner builds the assistant message.
    assert "messages" not in result


async def test_report_node_reraises_after_budget_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FlakyReportLLM(always_drops=True)
    _patch_report_llm(monkeypatch, llm)

    report = _make_report_node()
    with pytest.raises(httpx.RemoteProtocolError):
        await report(_report_state())  # type: ignore[arg-type]
    assert llm.attempts == STREAM_DROP_MAX_ATTEMPTS
