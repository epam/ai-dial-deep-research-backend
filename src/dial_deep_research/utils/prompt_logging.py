"""Middleware that logs the exact prompt being sent to the LLM.

Useful for debugging content-block formatting issues (e.g. images returned by
`get_page` not being recognized by the model). `wrap_model_call` runs after all
prompt assembly — system message, message history, and tool schemas as they will
actually be passed to the chat model — so what you see in the log is what the
model receives.

Long strings (notably base64-encoded image payloads) are truncated to keep the
log readable; the original length is recorded so you can confirm the data is
present.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, messages_to_dict

logger = logging.getLogger(__name__)

_MAX_STRING_CHARS = 500


def _truncate_strings(obj: Any, max_chars: int = _MAX_STRING_CHARS) -> Any:
    if isinstance(obj, str):
        if len(obj) > max_chars:
            return f"{obj[:max_chars]}... <truncated, total {len(obj)} chars>"
        return obj
    if isinstance(obj, list):
        return [_truncate_strings(x, max_chars) for x in obj]
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, max_chars) for k, v in obj.items()}
    return obj


def _serialize_message(msg: BaseMessage) -> dict:
    dumped = messages_to_dict([msg])[0]
    return _truncate_strings(dumped)


class PromptLoggingMiddleware(AgentMiddleware):
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        payload = {
            "system_message": _truncate_strings(
                request.system_message.text if request.system_message else None
            ),
            "messages": [_serialize_message(m) for m in request.messages],
            "tools": [getattr(t, "name", str(t)) for t in (request.tools or [])],
        }
        logger.info(
            "LLM request:\n%s",
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return await handler(request)
