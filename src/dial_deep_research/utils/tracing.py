from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opik.integrations.langchain import OpikTracer

_log = logging.getLogger(__name__)

# opik is an optional extra (see pyproject `[project.optional-dependencies].tracing`); the
# production image omits it. Import it lazily so the app runs without it installed.
_OPIK_MISSING_MSG = (
    "Opik tracing is enabled but 'tracing' extra dependencies are not installed. "
    "Either disable tracing or install the 'tracing' extra (e.g. `poetry install -E tracing`)."
)


def configure_opik(tracing_enabled: bool, project_name: str) -> None:
    if not tracing_enabled:
        return
    try:
        import opik
    except ImportError as e:
        # Fail fast at startup (called from create_app): a misconfigured deploy should not
        # boot and silently run untraced. The uncaught error aborts the process before the
        # server starts; `from e` keeps the original ImportError as the cause.
        raise RuntimeError(_OPIK_MISSING_MSG) from e
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
    try:
        from opik.integrations.langchain import OpikTracer
    except ImportError:
        # Unreachable in a booted app — configure_opik raises at startup when tracing is
        # enabled without opik. Kept as a defensive fallback so a stray call never crashes.
        return None
    return OpikTracer(thread_id=thread_id)
