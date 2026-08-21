"""Agent middlewares implementing the logging-policy spec for model calls.

Two records per model call, both emitted after prompt assembly:

- `ModelCallLoggingMiddleware` — the INFO skeleton event: metadata only (agent name,
  duration, finish kind, requested tool names, content length, token usage).
- `PromptLoggingMiddleware` — the payload record: the assembled LLM request (system
  message, message history, tool names) at DEBUG, each string truncated. Useful for
  debugging content-block formatting issues (e.g. images returned by a tool not
  being recognized by the model).

`agent_logging_middleware` is the one wiring point — see its docstring for gating
and ordering.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, messages_to_dict

from dial_deep_research.settings import settings
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.llm import format_token_usage

logger = logging.getLogger(__name__)


class ModelCallLoggingMiddleware(AgentMiddleware):
    """Log the INFO model-call event of the request skeleton (metadata only)."""

    def __init__(self, *, agent_name: str) -> None:
        super().__init__()
        self._agent_name = agent_name

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        message_count = len(request.messages) + (1 if request.system_message else 0)
        start = time.monotonic()
        response = await handler(request)
        duration = time.monotonic() - start

        message = next((m for m in response.result if isinstance(m, AIMessage)), None)
        tool_names = [tc["name"] for tc in message.tool_calls] if message else []
        usage = message.usage_metadata if message else None
        logger.info(
            "Model call completed: agent=%s duration=%.1fs messages=%d finish=%s tools=%s "
            "content_length=%d tokens=%s",
            self._agent_name,
            duration,
            message_count,
            "tool_calls" if tool_names else "final_answer",
            tool_names,
            len(extract_text_from_content(message.content)) if message else 0,
            format_token_usage(usage),
        )
        return response


class PromptLoggingMiddleware(AgentMiddleware):
    """Log the assembled LLM request at DEBUG, every string truncated.

    Emits full prompt content (system message, user conversation, tool payloads) —
    wire it only through `agent_logging_middleware`.
    """

    def __init__(self, *, max_chars: int) -> None:
        super().__init__()
        self._max_chars = max_chars

    def _truncate_strings(self, obj: Any) -> Any:
        if isinstance(obj, str):
            if len(obj) > self._max_chars:
                return f"{obj[: self._max_chars]}... <truncated, total {len(obj)} chars>"
            return obj
        if isinstance(obj, list):
            return [self._truncate_strings(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._truncate_strings(v) for k, v in obj.items()}
        return obj

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # Serializing the whole message history is heavy; skip it when DEBUG is
        # filtered (%-args are evaluated eagerly, so laziness must be explicit).
        if not logger.isEnabledFor(logging.DEBUG):
            return await handler(request)
        payload = {
            "system_message": self._truncate_strings(
                request.system_message.text if request.system_message else None
            ),
            "messages": [
                self._truncate_strings(messages_to_dict([m])[0]) for m in request.messages
            ],
            "tools": [getattr(t, "name", str(t)) for t in (request.tools or [])],
        }
        logger.debug(
            "LLM request:\n%s",
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return await handler(request)


def agent_logging_middleware(agent_name: str) -> list[AgentMiddleware]:
    """The logging middlewares every `create_agent` graph gets.

    Splice first into the agent's middleware list (before the retry middleware —
    first is outermost, so the skeleton event's duration includes retries).
    `PromptLoggingMiddleware` is included only behind the `LOG_PAYLOADS` opt-in —
    zero overhead otherwise.
    """
    middlewares: list[AgentMiddleware] = [ModelCallLoggingMiddleware(agent_name=agent_name)]
    if settings.log_payloads:
        middlewares.append(PromptLoggingMiddleware(max_chars=settings.log_payloads_max_length))
    return middlewares
