"""Streams the research graph into a DIAL `Choice`.

Drives the compiled graph with one `astream(subgraphs=True)` and routes its output:
researcher tool calls become timed DIAL stages, and only the report node's tokens
become the user-visible assistant content. Researcher reasoning and reviewer
structured output are not streamed to content. Persistence is the caller's job —
`run` returns the research message slice for the coordinator to persist with the
preparation slice.

The two stream modes have distinct jobs: `updates` and `messages` drive the live
output, `values` supplies the slice to persist. See `_handle_part`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aidial_sdk.chat_completion import Choice
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
)
from langgraph.types import StreamPart

from dial_deep_research.app.history import PrepState
from dial_deep_research.app.mcp_tools import load_mcp_tools
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.dial_stages import (
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
)

from .graph import build_research_graph
from .state import build_initial_state
from .tools import build_finish_iteration_tool

if TYPE_CHECKING:
    # opik is an optional extra; only needed for the type annotation here.
    from opik.integrations.langchain import OpikTracer

logger = logging.getLogger(__name__)

# The report node is the only one whose streamed tokens become assistant content.
_REPORT_NODE = "report"
_FINISH_TOOL = "finish_iteration"
# Super-step ceiling for one research turn (many tool calls across several iterations).
_RECURSION_LIMIT = 200


class ResearchRunner:
    """Runs the research graph for one turn and emits it to DIAL."""

    def __init__(self, choice: Choice) -> None:
        self._choice = choice
        self._pending_tool_calls: dict[str, PendingToolCall] = {}
        self._messages: list[BaseMessage] = []
        self._seen_ids: set[str] = set()
        # Separate the report from any preparation text already streamed this turn.
        self._separator_pending = True

    async def run(
        self,
        prep_state: PrepState,
        properties: ApplicationProperties,
        opik_tracer: OpikTracer | None = None,
        bearer_token: str | None = None,
    ) -> list[BaseMessage]:
        tools = await load_mcp_tools(mcp_servers=properties.mcp_servers, bearer_token=bearer_token)
        # The finish sentinel is research-specific: the researcher calls it to end an iteration.
        tools.append(build_finish_iteration_tool())
        graph = build_research_graph(
            tools=tools,
            today_date=datetime.now().date().isoformat(),
            max_iterations=properties.max_research_iterations,
            client_name=properties.prompts.client_name,
        )
        config: dict[str, Any] = {"recursion_limit": _RECURSION_LIMIT}
        if opik_tracer is not None:
            config["callbacks"] = [opik_tracer]

        async for part in graph.astream(
            build_initial_state(prep_state),
            stream_mode=["updates", "messages", "values"],
            subgraphs=True,
            version="v2",
            config=config,
        ):
            self._handle_part(part)
        return self._messages

    def _handle_part(self, part: StreamPart) -> None:
        """Route one stream part by mode.

        `version="v2"` gives every part the same `{type, ns, data}` shape, whatever the
        mode or namespace.

        `updates` and `messages` drive the live output. They arrive per node, including
        from inside the researcher subgraph — well before the parent re-emits them — which
        is what keeps the stages live.

        `values` carries the whole root state after each super-step, so the last one is the
        turn's final transcript. Taking it wholesale is what lets an in-place edit reach the
        persisted slice: the image-budget middleware substitutes a tool result under its
        original id, and collecting `updates` instead would only ever see the superseded
        original. `ns` must be empty — a subgraph's state has no reviewer or report messages.
        """
        if part["type"] == "updates":
            self._handle_updates(part["data"])
        elif part["type"] == "messages":
            chunk, metadata = part["data"]
            self._handle_message_chunk(chunk, metadata)
        elif part["type"] == "values" and not part["ns"]:
            self._messages = part["data"]["messages"]

    def _handle_updates(self, data: dict[str, Any]) -> None:
        for node_update in data.values():
            if not node_update:
                continue
            for msg in node_update.get("messages") or []:
                if self._already_seen(msg):
                    continue
                if isinstance(msg, AIMessage):
                    self._handle_ai_message(msg)
                elif isinstance(msg, ToolMessage):
                    self._handle_tool_message(msg)

    def _already_seen(self, msg: BaseMessage) -> bool:
        """Dedupe the live output for messages arriving from both the subgraph and the
        parent aggregate. Persistence does not go through here — it reads the final state."""
        key = msg.id or f"{id(msg)}"
        if key in self._seen_ids:
            return True
        self._seen_ids.add(key)
        return False

    def _handle_ai_message(self, msg: AIMessage) -> None:
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
        tool_call = self._pending_tool_calls.pop(msg.tool_call_id, None)
        if tool_call is None:
            # No matching pending call (e.g. a duplicated emission already staged); skip.
            return
        end = datetime.now()
        is_error = msg.status == "error"
        # The finish sentinel is an internal completion signal — not a research action
        # worth a stage or an INFO skeleton event; iteration boundaries are the
        # reviewer event's job.
        is_finish = tool_call.tool_name == _FINISH_TOOL
        log_tool_call_completed(
            logger,
            tool_call=tool_call,
            tool_call_id=msg.tool_call_id,
            end=end,
            is_error=is_error,
            level=logging.DEBUG if is_finish else logging.INFO,
        )
        if is_finish:
            return
        title = DialStageToolCallFormatter.format_title(
            tool_call.tool_name, tool_call.start, end, is_error=is_error
        )
        body = DialStageToolCallFormatter.format_body(
            args_json=tool_call.args_json, content=msg.content, is_error=is_error
        )
        with self._choice.create_stage(title) as result_stage:
            result_stage.append_content(body)

    def _handle_message_chunk(self, chunk: BaseMessage, metadata: dict) -> None:
        # Only the report node's tokens are the answer; researcher/reviewer tokens are not.
        if metadata.get("langgraph_node") != _REPORT_NODE:
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
