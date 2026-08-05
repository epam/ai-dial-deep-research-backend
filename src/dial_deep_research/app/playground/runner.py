"""Streams the playground agent into a DIAL `Choice`.

A single tool-calling agent over the configured MCP servers — no clarification, no
research/review loop, no report node. Tool calls become timed DIAL stages; the
agent's own text becomes the assistant content. Stateless: nothing is persisted, so
prior turns reach the agent as visible text only (see `reconstruct_plain_history`).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aidial_sdk.chat_completion import Choice, Request, Role
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from dial_deep_research.app.mcp_tools import load_mcp_tools
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.dial_stages import (
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
)

from .agent import build_playground_agent

if TYPE_CHECKING:
    # opik is an optional extra; only needed for the type annotation here.
    from opik.integrations.langchain import OpikTracer

logger = logging.getLogger(__name__)

# create_agent runs the main model in a node named "model"; the playground tools are plain
# MCP tools (no nested LLM calls), so only this node's tokens are the assistant's answer.
_MODEL_NODE = "model"


def reconstruct_plain_history(request: Request) -> list[BaseMessage]:
    """Rebuild history for the stateless playground from the visible messages alone.

    Reads no persisted `custom_content.state`: each USER message becomes a `HumanMessage`
    and each ASSISTANT message a single `AIMessage(content=…)` from its visible text. Prior
    tool calls/outputs are not replayed (they were never persisted), and no `dial` client is
    needed.
    """
    history: list[BaseMessage] = []
    for message in request.messages:
        if message.role == Role.USER:
            history.append(HumanMessage(content=extract_text_from_content(message.content)))
        elif message.role == Role.ASSISTANT:
            history.append(AIMessage(content=extract_text_from_content(message.content)))
    return history


class PlaygroundRunner:
    """Drives one playground agent run and emits it to DIAL (no persistence)."""

    def __init__(self, choice: Choice) -> None:
        self._choice = choice
        self._pending_tool_calls: dict[str, PendingToolCall] = {}
        self._separator_pending = False

    async def run(
        self,
        request: Request,
        properties: ApplicationProperties,
        bearer_token: str | None = None,
        opik_tracer: OpikTracer | None = None,
    ) -> None:
        """Run the playground agent over the reconstructed history, streaming to the choice.

        The per-request bearer token (when present) is forwarded to the MCP servers for
        per-user access; the api-key is handled by header propagation.
        """
        history = reconstruct_plain_history(request)
        tools = await load_mcp_tools(mcp_servers=properties.mcp_servers, bearer_token=bearer_token)
        agent = build_playground_agent(
            tools=tools,
            prompts=properties.prompts,
            today_date=datetime.now().date().isoformat(),
        )
        config: dict[str, Any] = {"callbacks": [opik_tracer]} if opik_tracer is not None else {}

        # `version="v2"` gives every part the same `{type, ns, data}` shape. The agent is
        # streamed directly rather than as a subgraph, so `ns` is always empty here.
        async for part in agent.astream(
            {"messages": history},
            stream_mode=["updates", "messages"],
            version="v2",
            config=config,
        ):
            if part["type"] == "updates":
                for node_update in part["data"].values():
                    if node_update is None:
                        continue
                    for msg in node_update.get("messages") or []:
                        if isinstance(msg, AIMessage):
                            self._handle_ai_message(msg)
                        elif isinstance(msg, ToolMessage):
                            self._handle_tool_message(msg)
            elif part["type"] == "messages":
                chunk, metadata = part["data"]
                self._handle_message_chunk(chunk, metadata)

    def _handle_ai_message(self, msg: AIMessage) -> None:
        if not msg.tool_calls:
            return
        start = datetime.now()
        for tc in msg.tool_calls:
            tc_id = tc["id"]
            if not tc_id:
                continue
            args_json = json.dumps(tc["args"], default=str, indent=2)
            self._pending_tool_calls[tc_id] = PendingToolCall(
                start=start, tool_name=tc["name"], args_json=args_json
            )

    def _handle_tool_message(self, msg: ToolMessage) -> None:
        self._separator_pending = True
        tool_call = self._pending_tool_calls.pop(msg.tool_call_id, None)
        if tool_call is None:
            raise ValueError(
                f"ToolMessage has tool_call_id={msg.tool_call_id!r} with no matching "
                "pending tool call; agent dispatch invariant violated"
            )
        end = datetime.now()
        is_error = msg.status == "error"
        log_tool_call_completed(
            logger, tool_call=tool_call, tool_call_id=msg.tool_call_id, end=end, is_error=is_error
        )
        title = DialStageToolCallFormatter.format_title(
            tool_call.tool_name, tool_call.start, end, is_error=is_error
        )
        body = DialStageToolCallFormatter.format_body(
            args_json=tool_call.args_json, content=msg.content, is_error=is_error
        )
        with self._choice.create_stage(title) as result_stage:
            result_stage.append_content(body)

    def _handle_message_chunk(self, chunk: BaseMessage, metadata: dict) -> None:
        if metadata.get("langgraph_node") != _MODEL_NODE:
            return
        if not isinstance(chunk, AIMessageChunk):
            return
        text = extract_text_from_content(chunk.content)
        if not text:
            return
        if self._separator_pending:
            text = "\n\n" + text
            self._separator_pending = False
        self._choice.append_content(text)
