"""Middleware that forces the researcher to call a tool on every step.

`create_agent` always calls the model with `tool_choice=None`. We override that to
`"any"` so the researcher can never emit a free-form assistant message — every step
is either an MCP tool call or `finish_iteration`. This removes any path for the model
to write a premature summary or report; the report is a separate node.

Shared middleware (the image budget) lives in `app/middleware.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse


class ForceToolChoiceMiddleware(AgentMiddleware):
    """Re-issue every model call with `tool_choice="any"`."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        return await handler(request.override(tool_choice="any"))
