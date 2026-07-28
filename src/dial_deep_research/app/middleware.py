"""Shared agent middleware, used by every agent that talks to the MCP tools.

Agent-specific middleware (e.g. the researcher's forced tool choice) lives with its
agent; this module holds middleware any tool-calling agent may need.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ImageBudgetMiddleware(AgentMiddleware):
    """Substitute overflowing image tool results before each model call.

    Keeps the conversation within the image budget (see the image-budget spec) so no
    LLM request exceeds the provider's per-request image limit. Counts image content
    blocks across the state; while the total exceeds the budget, walks tool messages
    newest → oldest replacing each image-carrying one with an error `ToolMessage`
    (same id, so the `add_messages` reducer substitutes it in place — a persistent
    state update that downstream consumers of the state inherit). Tool-agnostic: only
    returned content is inspected, never tool names or arguments.

    Sync-only is deliberate: the hook is pure in-memory work, and langgraph's node
    wrapper falls back to the sync fn on async runs.
    """

    def __init__(self, *, limit: int) -> None:
        super().__init__()
        self._limit = limit

    @staticmethod
    def _count_image_blocks(message: BaseMessage) -> int:
        content = message.content
        if not isinstance(content, list):
            return 0
        return sum(1 for b in content if isinstance(b, dict) and b.get("type") == "image")

    def _render_drop_text(self, *, num_images: int, cum: int) -> str:
        """The error text for one dropped tool result.

        `cum` is the cumulative image total at this drop step (this result included).
        Exactly the drop that brings the total within the budget — the walk's last —
        also carries the remaining-allowance instruction.
        """
        before = cum - num_images
        text = (
            f"Tool result dropped: it contained {num_images} image(s), which brought the "
            f"conversation from {before} to {cum} images, exceeding the budget of "
            f"{self._limit}."
        )
        if before <= self._limit:
            remaining = self._limit - before
            if remaining > 0:
                text += (
                    f" {remaining} image slot(s) remain — "
                    f"fetch at most {remaining} more image(s)."
                )
            else:
                text += " The image budget is fully used — do not fetch more images."
        return text

    def before_model(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:
        messages = state["messages"]
        total = sum(self._count_image_blocks(m) for m in messages)
        if total <= self._limit:
            return None

        substituted: list[ToolMessage] = []
        cum = total
        for message in reversed(messages):
            if cum <= self._limit:
                break
            if not isinstance(message, ToolMessage):
                continue
            num_images = self._count_image_blocks(message)
            if num_images == 0:
                continue
            if message.id is None:
                # Substituting needs the id: `add_messages` assigns a fresh one to any
                # id-less message, so the substitute would be appended next to the original
                # instead of replacing it — the images would stay and the error text would
                # only add noise. Skip it; the shortfall is reported after the walk.
                logger.warning(
                    "Cannot substitute an image tool result with no message id: "
                    "tool=%s images=%d",
                    message.name,
                    num_images,
                )
                continue
            substituted.append(
                ToolMessage(
                    content=self._render_drop_text(num_images=num_images, cum=cum),
                    tool_call_id=message.tool_call_id,
                    id=message.id,
                    name=message.name,
                    status="error",
                )
            )
            cum -= num_images

        # Reachable only when some images sit outside a substitutable tool message (not in a
        # `ToolMessage`, or in one with no id). The for-loop above makes such a state degrade
        # to a log line, not a hang.
        if cum > self._limit:
            logger.warning(
                "Image budget still exceeded after substituting every eligible image tool "
                "message: kept=%d limit=%d",
                cum,
                self._limit,
            )
        logger.info(
            "Image budget exceeded: total=%d limit=%d dropped_messages=%d dropped_images=%d "
            "kept=%d",
            total,
            self._limit,
            len(substituted),
            total - cum,
            cum,
        )
        return {"messages": substituted} if substituted else None
