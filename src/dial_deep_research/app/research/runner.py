"""Runs the research graph and emits it to a DIAL `Choice`.

Drives the compiled graph with one `astream(subgraphs=True)` and routes its output:
research-agent tool calls become timed DIAL stages, each report review becomes a stage of its
own — as does a delivery the version budget left unreviewed — and the report the review loop
settles on is appended once as the assistant content.

Nothing is streamed token-by-token here. A report draft may still be revised and DIAL content is
append-only, so no draft may reach the choice while the loop runs — the report is appended after
the graph finishes, from its final state. Research-agent reasoning and both reviews' structured
output never become content.

Persistence is the caller's job — `run` returns the research message slice (the transcript plus
the delivered report as an `AIMessage`) for the coordinator to persist with the preparation slice.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aidial_sdk.chat_completion import Choice
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
)
from langgraph.types import StreamPart

from dial_deep_research.app.history import PrepState
from dial_deep_research.app.mcp_tools import load_mcp_tools
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.utils.dial_stages import (
    DialStageReportReviewFormatter,
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
)

from .graph import build_research_graph
from .nodes import ReportReviewOutcome, review_budget_exhausted
from .prompts import render_length_exemptions
from .report_length import count_report_words
from .state import build_initial_state
from .tools import build_finish_iteration_tool

if TYPE_CHECKING:
    # opik is an optional extra; only needed for the type annotation here.
    from opik.integrations.langchain import OpikTracer

logger = logging.getLogger(__name__)

_FINISH_TOOL = "finish_iteration"


class ResearchRunner:
    """Runs the research graph for one turn and emits it to DIAL."""

    def __init__(self, choice: Choice, *, content_already_streamed: bool = False) -> None:
        self._choice = choice
        self._pending_tool_calls: dict[str, PendingToolCall] = {}
        self._messages: list[BaseMessage] = []
        self._seen_ids: set[str] = set()
        self._report: str | None = None
        self._report_version = 0
        # Only separate the report from preparation text that actually reached the choice. With
        # the silent hand-off there usually is none, and then the report starts the message.
        self._content_already_streamed = content_already_streamed

    async def run(
        self,
        prep_state: PrepState,
        properties: ApplicationProperties,
        opik_tracer: OpikTracer | None = None,
        bearer_token: str | None = None,
    ) -> list[BaseMessage]:
        tools = await load_mcp_tools(mcp_servers=properties.mcp_servers, bearer_token=bearer_token)
        # The finish sentinel is research-specific: research-agent calls it to end an iteration.
        tools.append(build_finish_iteration_tool())
        graph = build_research_graph(
            tools=tools,
            today_date=datetime.now().date().isoformat(),
            max_research_iterations=properties.max_research_iterations,
            client_name=properties.prompts.client_name,
            report_structure=properties.default_report_structure,
            max_report_words=properties.max_report_words,
            max_report_versions=properties.max_report_versions,
            emit_report_review_stage=self._emit_report_review_stage,
        )
        # LangGraph applies this to each graph run separately, so the same value bounds the
        # research graph and every research-agent-subgraph run (see the property's description).
        config: dict[str, Any] = {"recursion_limit": properties.max_research_graph_steps}
        if opik_tracer is not None:
            config["callbacks"] = [opik_tracer]

        async for part in graph.astream(
            build_initial_state(prep_state),
            stream_mode=["updates", "values"],
            subgraphs=True,
            version="v2",
            config=config,
        ):
            self._handle_part(part)

        self._emit_unreviewed_delivery_stage(properties)
        self._deliver_report()
        return self._messages

    def _deliver_report(self) -> None:
        """Append the settled report to the choice, and add it to the slice to persist.

        The graph state carries no draft `AIMessage` — drafts stay out of the transcript so a
        rejected one is neither re-sent to a model nor persisted — so the assistant message is
        built here, from the draft the loop settled on.
        """
        if not self._report:
            return
        text = self._report
        if self._content_already_streamed:
            text = "\n\n" + text
        self._choice.append_content(text)
        self._messages = [*self._messages, AIMessage(content=self._report)]

    def _handle_part(self, part: StreamPart) -> None:
        """Route one stream part by mode.

        `version="v2"` gives every part the same `{type, ns, data}` shape, whatever the
        mode or namespace.

        `updates` drives the live output. Parts arrive per node, including from inside the
        research-agent subgraph — well before the parent re-emits them — which is what keeps the
        stages live. There is no `messages` mode: nothing is streamed token-by-token.

        `values` carries the whole root state after each super-step, so the last one is the
        turn's final transcript. Taking it wholesale is what lets an in-place edit reach the
        persisted slice: the image-budget middleware substitutes a tool result under its
        original id, and collecting `updates` instead would only ever see the superseded
        original. `ns` must be empty — a subgraph's state has no research-review or report messages.
        """
        if part["type"] == "updates":
            self._handle_updates(part["data"])
        elif part["type"] == "values" and not part["ns"]:
            self._messages = part["data"]["messages"]
            self._report = part["data"].get("report")
            self._report_version = part["data"].get("report_version", 0)

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
        # research-review event's job.
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

    def _emit_unreviewed_delivery_stage(self, properties: ApplicationProperties) -> None:
        """Announce a delivery whose draft the version budget left unreviewed.

        Distinguishes "review approved the draft" from "the budget ran out, so the previous
        review's findings may remain". Deterministic — no model call: the last permitted version
        exists only because the previous review demanded a rewrite. A budget of one emits
        nothing — review is off by configuration, not exhausted.
        """
        max_versions = properties.max_report_versions
        if not self._report or max_versions <= 1:
            return
        if not review_budget_exhausted(
            report_version=self._report_version, max_versions=max_versions
        ):
            return
        word_count = count_report_words(self._report, sections=properties.default_report_structure)
        logger.info(
            "Report delivered without review: draft=%d max_versions=%d words=%d",
            self._report_version,
            max_versions,
            word_count,
        )
        title = DialStageReportReviewFormatter.format_unreviewed_title(
            draft_number=self._report_version
        )
        body = DialStageReportReviewFormatter.format_unreviewed_body(
            draft_number=self._report_version,
            word_count=word_count,
            max_words=properties.max_report_words,
            length_exemptions=render_length_exemptions(properties.default_report_structure),
            max_versions=max_versions,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)

    def _emit_report_review_stage(self, outcome: ReportReviewOutcome) -> None:
        """Render one report review as a DIAL stage.

        The node decided what to report; this decides how it looks. The violation text belongs
        here and nowhere else — the logging-policy content allowlist keeps LLM response text out
        of log records, so the logs carry only the count.
        """
        title = DialStageReportReviewFormatter.format_title(
            draft_number=outcome.draft_number,
            revising=outcome.revision_instruction is not None,
            review_failed=outcome.error is not None,
            duration_seconds=outcome.duration_seconds,
        )
        body = DialStageReportReviewFormatter.format_body(
            draft_number=outcome.draft_number,
            word_count=outcome.word_count,
            max_words=outcome.max_words,
            length_exemptions=outcome.length_exemptions,
            violations=outcome.violations,
            error=outcome.error,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)
