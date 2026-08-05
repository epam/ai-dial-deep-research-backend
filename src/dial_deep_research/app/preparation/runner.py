"""Streams the preparation agent into a DIAL `Choice`.

Stateless per turn: the caller reconstructs `PrepState` and the transcript from the
DIAL request and passes them in; this runner builds the agent over that state, runs
it, and streams its output. It does not load, refuse, or persist — the turn
coordinator (`app/completion.py`) owns those so a single combined `DialState` is
persisted once, even when research runs in the same turn.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Choice, Request
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
)

from dial_deep_research.app.history import PrepState, reconstruct_history
from dial_deep_research.app_properties import Prompts
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.dial_stages import (
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
)

from .agent import build_prep_agent

if TYPE_CHECKING:
    # opik is an optional extra; only needed for the type annotation here.
    from opik.integrations.langchain import OpikTracer

logger = logging.getLogger(__name__)

# The create_agent graph runs the main model in a node named "model"; tools run in
# "tools". The nested structured-output calls inside the tools (the clarity/approval
# checks) therefore stream under "tools" — we exclude those from user-facing text.
_MODEL_NODE = "model"


class PrepAgentRunner:
    """Drives one preparation agent run and emits it to DIAL (no persistence)."""

    @property
    def appended_content(self) -> bool:
        """Whether any preparation text reached the choice this turn.

        The research runner needs it: the report is separated from preparation text by a blank
        line, and with the silent hand-off there usually is none to separate from. It also drives
        the separator between preparation's own text segments — the first segment of a turn takes
        no leading blank line.
        """
        return self._appended_content

    def __init__(self, choice: Choice) -> None:
        self._choice = choice
        self._pending_tool_calls: dict[str, PendingToolCall] = {}
        self._messages: list[BaseMessage] = []
        self._appended_content = False
        self._streamed_message_id: str | None = None

    async def run(
        self,
        request: Request,
        dial: AsyncDial,
        prep_state: PrepState,
        prompts: Prompts,
        opik_tracer: OpikTracer | None = None,
    ) -> list[BaseMessage]:
        """Run the preparation agent over `prep_state`, streaming output; return its messages.

        `prep_state` is the live holder the tools mutate, so after this returns it
        reflects the turn (including `research_started` if `start_research` fired).
        """
        history = await reconstruct_history(request, dial)
        agent = build_prep_agent(
            state=prep_state,
            today_date=datetime.now().date().isoformat(),
            prompts=prompts,
        )
        config: dict[str, Any] = {"callbacks": [opik_tracer]} if opik_tracer is not None else {}

        async for mode, payload in agent.astream(
            {"messages": history}, stream_mode=["updates", "messages"], config=config
        ):
            if mode == "updates":
                for node_update in payload.values():
                    if node_update is None:
                        continue
                    for msg in node_update.get("messages") or []:
                        if isinstance(msg, AIMessage):
                            self._handle_ai_message(msg)
                        elif isinstance(msg, ToolMessage):
                            self._handle_tool_message(msg)
            elif mode == "messages":
                chunk, metadata = payload
                self._handle_message_chunk(chunk, metadata)

        return self._messages

    def _handle_ai_message(self, msg: AIMessage) -> None:
        self._messages.append(msg)
        if msg.tool_calls:
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
        self._messages.append(msg)
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
        # Only stream the main model node's tokens. The nested structured-output
        # calls inside the tools (clarity/approval checks) also reach this stream,
        # under the "tools" node — skip them so their raw JSON never leaks into the
        # assistant content.
        if metadata.get("langgraph_node") != _MODEL_NODE:
            return
        if not isinstance(chunk, AIMessageChunk):
            return
        text = extract_text_from_content(chunk.content)
        if not text:
            return
        # A blank line goes between text segments, not between tokens. Every chunk of one
        # assistant message shares an id — the provider's response id, or one langchain_core
        # stamps per LLM run (`chat_models.py`, `chunk.message.id = run_id` when the provider
        # sent none) — so a change of id means a new message: the next model call, or the same
        # call re-streamed after a transient failure.
        if self._appended_content and chunk.id != self._streamed_message_id:
            text = "\n\n" + text
        self._streamed_message_id = chunk.id
        self._choice.append_content(text)
        self._appended_content = True
