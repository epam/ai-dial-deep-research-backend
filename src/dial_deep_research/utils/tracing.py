import logging
from typing import Any

import opik
from opik.integrations.langchain import OpikTracer

_log = logging.getLogger(__name__)


def configure_opik(tracing_enabled: bool, project_name: str | None) -> None:
    if not tracing_enabled:
        return
    if not project_name:
        raise ValueError("project_name is required when opik tracing is enabled")
    opik.configure(use_local=True, project_name=project_name)
    _log.info("Opik tracing configured (project_name=%s)", project_name)


def extract_thread_id(request: Any) -> str | None:
    """Best-effort thread id for grouping Opik traces by conversation.

    Generically named on purpose: today the body only knows how to read DIAL's
    `X-CONVERSATION-ID` header, but the call site reads as a concept so a future
    second source can slot in without renaming. Returns `None` on any failure
    path (header absent, empty, unexpected request shape) so tracing falls back
    to today's per-turn behaviour instead of breaking the chat completion.
    """
    try:
        value = request.headers.get("x-conversation-id")
        if value is None:
            return None
        value = str(value).strip()
        return value or None
    except Exception:
        return None


def build_opik_tracer(tracing_enabled: bool, thread_id: str | None = None) -> OpikTracer | None:
    if not tracing_enabled:
        return None
    return OpikTracer(thread_id=thread_id)
