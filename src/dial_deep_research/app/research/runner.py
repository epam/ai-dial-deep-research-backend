"""Runs the research graph and emits it to a DIAL `Choice`.

Drives the compiled graph with one `astream(subgraphs=True)` and routes its output:
research-agent tool calls become timed DIAL stages, each research review and each report review
becomes a stage of its own — as does a delivery the version budget left unreviewed — and the report
the review loop settles on is appended once as the assistant content.

Nothing is streamed token-by-token here. A report draft may still be revised and DIAL content is
append-only, so no draft may reach the choice while the loop runs — the report is appended after
the graph finishes, from its final state. Research-agent reasoning and both reviews' structured
output never become content.

Between the graph finishing and the report being appended, the runner runs the citation step:
the hyperlinks a report may not carry are removed, each convertible citation marker becomes a
marker tag, and the annotations claiming those tags are emitted once the text is appended (see
`citations.py` and the report-citations capability). Nothing about it can fail the turn.

Persistence is the caller's job — `run` returns the research message slice (the transcript plus
the delivered report as an `AIMessage`) for the coordinator to persist with the preparation slice.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aidial_sdk.chat_completion import Choice, Stage, Status
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.types import StreamPart
from pydantic import BaseModel, Field

from dial_deep_research.app.history import PrepState
from dial_deep_research.app.mcp_tools import load_mcp_tools
from dial_deep_research.app_properties import ApplicationProperties
from dial_deep_research.utils.dial_annotations import send_annotations
from dial_deep_research.utils.dial_stages import (
    DialStageReportFormatter,
    DialStageReportReviewFormatter,
    DialStageResearchReviewFormatter,
    DialStageToolCallFormatter,
    PendingToolCall,
    log_tool_call_completed,
)

from .citations import (
    Annotation,
    cited_document_ids,
    convert_citations,
    find_citation_markers,
    log_citations_resolved,
    remove_hyperlinks,
)
from .file_sharing import FileSharingError, share_documents
from .graph import build_research_graph
from .nodes import (
    ReportBudgetExhausted,
    ReportReviewOutcome,
    ReportRevisionFailure,
    ResearchBudgetExhausted,
    ResearchReviewOutcome,
)
from .state import build_initial_state
from .tools import (
    FINISH_TOOL_NAME,
    UPDATE_STATUS_TOOL_NAME,
    build_finish_iteration_tool,
    build_update_status_tool,
)

if TYPE_CHECKING:
    # opik is an optional extra; only needed for the type annotation here.
    from opik.integrations.langchain import OpikTracer

logger = logging.getLogger(__name__)

_FINISH_TOOL = FINISH_TOOL_NAME

# The activity stage the runner opens before the graph runs. Every later title comes from
# research-agent's `update_status` calls or from a node announcing itself on entry.
_INITIAL_ACTIVITY = "Starting research"

# The activity stage of the citation step, opened only once that step has work: the file-sharing
# call copies a document per cited id, which takes long enough that the turn would otherwise
# look finished while it runs.
CITATIONS_ACTIVITY = "Preparing the report's citations"

# The citation step's failure kinds, as its warnings report them. Two more are decided by the
# file-sharing call itself and named in `file_sharing.py`.
_KIND_TOOL_NOT_ADVERTISED = "tool_not_advertised"
_KIND_CALL_FAILED = "call_failed"
_KIND_IDS_UNRESOLVED = "ids_unresolved"
_KIND_LINK_PASS_FAILED = "link_pass_failed"
_KIND_CONVERSION_FAILED = "conversion_failed"
_KIND_EMISSION_FAILED = "emission_failed"

# Joins the statuses of one assistant message into a single title. The model is told to send
# one status per turn; this keeps the extras visible without opening a stage that would close
# an instant later and so read as a finished step.
_STATUS_JOIN = "; "


class _ReportDelivery(BaseModel):
    """The report as it will be delivered, and what the citation step counted on the way.

    Filled in as the step gets through its passes, so a failure keeps the text the last
    finished pass produced and every count already learned.
    """

    text: str
    annotations: list[Annotation] = Field(default_factory=list)
    documents_requested: int = 0
    documents_resolved: int = 0
    markers_left: int = 0
    hyperlinks_removed: int = 0


def _count_markers(text: str) -> int:
    """How many citation markers the text still carries, for the step's own log event.

    Guarded, because the only path that reaches it is one where the marker parsing already
    failed once, and a count in a log record is not worth failing a delivered report over.
    """
    try:
        return len(find_citation_markers(text))
    except Exception:
        return 0


class ResearchRunner:
    """Runs the research graph for one turn and emits it to DIAL."""

    def __init__(self, choice: Choice, *, content_already_streamed: bool = False) -> None:
        self._choice = choice
        self._pending_tool_calls: dict[str, PendingToolCall] = {}
        self._messages: list[BaseMessage] = []
        self._seen_ids: set[str] = set()
        self._report: str | None = None
        # The one open activity stage. A DIAL stage name can only be appended to, so changing
        # what it says means replacing the stage; `None` means none is open right now.
        self._activity_stage: Stage | None = None
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
        loaded = await load_mcp_tools(mcp_servers=properties.mcp_servers, bearer_token=bearer_token)
        # Both are research-specific and app-owned: the sentinel ends an iteration, the status
        # tool tells the user what the agent is doing. Neither reaches an MCP server.
        tools = [
            *loaded.agent_tools,
            build_finish_iteration_tool(),
            build_update_status_tool(),
        ]
        graph = build_research_graph(
            tools=tools,
            today_date=datetime.now().date().isoformat(),
            max_research_iterations=properties.max_research_iterations,
            client_name=properties.prompts.client_name,
            report_structure=properties.default_report_structure,
            max_report_words=properties.max_report_words,
            max_report_versions=properties.max_report_versions,
            emit_research_review_result_stage=self._emit_research_review_result_stage,
            emit_research_budget_exhausted=self._emit_research_budget_exhausted_stage,
            emit_report_review_result_stage=self._emit_report_review_result_stage,
            emit_report_revision_failed=self._emit_report_revision_failed_stage,
            emit_report_budget_exhausted=self._emit_report_budget_exhausted_stage,
            emit_activity=self._set_activity,
        )
        # LangGraph applies this to each graph run separately, so the same value bounds the
        # research graph and every research-agent-subgraph run (see the property's description).
        config: dict[str, Any] = {"recursion_limit": properties.max_research_graph_steps}
        if opik_tracer is not None:
            config["callbacks"] = [opik_tracer]

        # Opened before the graph so the first model call is not silent. From here on some
        # activity stage is always open until the report is delivered, and every exit from here
        # — the graph raising, the delivery raising, the delivery finishing — closes the open
        # one: an unclosed stage reaches the client with no status and spins there for good.
        self._set_activity(_INITIAL_ACTIVITY)
        try:
            async for part in graph.astream(
                build_initial_state(prep_state),
                stream_mode=["updates", "values"],
                subgraphs=True,
                version="v2",
                config=config,
            ):
                self._handle_part(part)
        except BaseException:
            self._close_activity(Status.FAILED)
            raise

        # The graph's last activity stage stays open into the citation step, which replaces it
        # when it has work to announce and closes it before the report reaches the content.
        await self._deliver_report(
            file_sharing_tool=loaded.file_sharing_tool,
            configured_tool_name=properties.file_sharing_tool,
        )
        return self._messages

    async def _deliver_report(
        self, *, file_sharing_tool: BaseTool | None, configured_tool_name: str | None
    ) -> None:
        """Post-process the settled report, append it to the choice, and emit its annotations.

        The graph state carries no draft `AIMessage` — drafts stay out of the transcript so a
        rejected one is neither re-sent to a model nor persisted — so the assistant message is
        built here, from the draft the loop settled on.

        What is appended is that draft after the citation step, and the same text is what the
        persisted message carries, so a later turn reads back what the user saw. The
        annotations follow the content: the client reads them off a finished message, and a
        marker tag no annotation claims is shown to the reader as text.
        """
        if not self._report:
            self._close_activity(Status.COMPLETED)
            return

        started_at = time.monotonic()
        try:
            delivery = await self._run_citation_step(
                self._report,
                file_sharing_tool=file_sharing_tool,
                configured_tool_name=configured_tool_name,
            )
        except BaseException:
            # The step catches its own failures, so only something outside them reaches here —
            # a cancelled turn, say. The stage closes as failed, as the graph's does.
            self._close_activity(Status.FAILED)
            raise
        # Closed before the content, so the report never arrives under an open stage.
        self._close_activity(Status.COMPLETED)

        text = delivery.text
        self._choice.append_content(f"\n\n{text}" if self._content_already_streamed else text)
        self._messages = [*self._messages, AIMessage(content=text)]
        self._send_annotations(delivery.annotations)
        log_citations_resolved(
            logger,
            documents_requested=delivery.documents_requested,
            documents_resolved=delivery.documents_resolved,
            annotations=len(delivery.annotations),
            markers_left=delivery.markers_left,
            hyperlinks_removed=delivery.hyperlinks_removed,
            duration_seconds=time.monotonic() - started_at,
        )

    async def _run_citation_step(
        self,
        draft: str,
        *,
        file_sharing_tool: BaseTool | None,
        configured_tool_name: str | None,
    ) -> _ReportDelivery:
        """The two deterministic alterations of the settled draft, in their fixed order.

        Link removal first, then the citation conversion over the text that pass produced. The
        two fail independently, and each failure keeps what the pass before it finished: a
        failed link pass delivers the draft exactly as the review settled it, and a failed
        conversion delivers the link-free text with every citation marker in place.
        """
        try:
            removal = remove_hyperlinks(draft)
        except Exception as error:
            self._warn_citation_failure(kind=_KIND_LINK_PASS_FAILED, error=error)
            return _ReportDelivery(text=draft, markers_left=_count_markers(draft))

        delivery = _ReportDelivery(text=removal.text, hyperlinks_removed=removal.removed)
        try:
            document_ids = cited_document_ids(removal.text)
            delivery.documents_requested = len(document_ids)
            # A file-sharing call to make, or edits already applied: either is work worth
            # announcing. A draft that cites nothing and carried no link leaves the step with
            # nothing to say, and a stage there would open and close in the same instant.
            if removal.removed or (file_sharing_tool is not None and document_ids):
                self._set_activity(CITATIONS_ACTIVITY)
            document_urls = await self._share_cited_documents(
                tool=file_sharing_tool,
                configured_tool_name=configured_tool_name,
                document_ids=document_ids,
            )
            delivery.documents_resolved = len(document_urls)
            converted = convert_citations(removal.text, document_urls=document_urls)
        except Exception as error:
            self._warn_citation_failure(kind=_KIND_CONVERSION_FAILED, error=error)
            delivery.markers_left = _count_markers(delivery.text)
            return delivery

        delivery.text = converted.text
        delivery.annotations = converted.annotations
        delivery.markers_left = converted.markers_left
        return delivery

    async def _share_cited_documents(
        self,
        *,
        tool: BaseTool | None,
        configured_tool_name: str | None,
        document_ids: Sequence[int],
    ) -> dict[int, str]:
        """The URL of every cited document the file-sharing tool managed to share.

        Empty whenever no URL can be obtained — no server names a tool, the named tool is not
        advertised, the call failed, the answer could not be read — and every citation then
        keeps its marker text. Only the first of those is routine rather than a fault: an
        instance naming no tool has inline citations switched off, so it would otherwise warn
        on every report it delivers.
        """
        if configured_tool_name is None:
            logger.debug(
                "Report citations: no MCP server names a file-sharing tool, so every citation"
                " marker is delivered as the report writer wrote it"
            )
            return {}
        if tool is None:
            self._warn_citation_failure(
                kind=_KIND_TOOL_NOT_ADVERTISED, tool_name=configured_tool_name
            )
            return {}
        if not document_ids:
            return {}
        try:
            document_urls = await share_documents(tool=tool, document_ids=document_ids)
        except FileSharingError as failure:
            self._warn_citation_failure(kind=failure.kind, tool_name=configured_tool_name)
            return {}
        except Exception as error:
            self._warn_citation_failure(
                kind=_KIND_CALL_FAILED, tool_name=configured_tool_name, error=error
            )
            return {}
        unresolved = sum(1 for document_id in document_ids if document_id not in document_urls)
        if unresolved:
            # Warned even though the other documents got their pills: the report was written to
            # offer this one's, and the counts alone would read as a report that cited less.
            self._warn_citation_failure(
                kind=_KIND_IDS_UNRESOLVED,
                tool_name=configured_tool_name,
                unresolved=unresolved,
            )
        return document_urls

    def _send_annotations(self, annotations: Sequence[Annotation]) -> None:
        """Emit the annotations claiming the marker tags of the text just appended.

        A failure leaves those tags unclaimed, and the client shows an unclaimed tag to the
        reader as text. The array is not re-sent and the appended content is not edited —
        DIAL content is append-only, so neither is possible.
        """
        if not annotations:
            return
        try:
            send_annotations(choice=self._choice, annotations=annotations)
        except Exception as error:
            self._warn_citation_failure(kind=_KIND_EMISSION_FAILED, error=error)

    def _warn_citation_failure(
        self,
        *,
        kind: str,
        tool_name: str | None = None,
        unresolved: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        """One WARNING per citation failure, naming the kind and nothing about a document.

        What a record of this step may carry is the failure kind, counts, the configured tool's
        name and the exception's class. A returned URL, any part of one, a file name taken from
        one and a cited document's id never appear at any level: the mapping is a tool response
        body, which the content allowlist keeps out of every record.
        """
        fields = [f"kind={kind}"]
        if tool_name is not None:
            fields.append(f"tool={tool_name}")
        if unresolved is not None:
            fields.append(f"ids_unresolved={unresolved}")
        if error is not None:
            fields.append(f"error={type(error).__name__}")
        logger.warning("Report citations failed: %s", " ".join(fields))

    def _set_activity(self, title: str) -> None:
        """Replace the open activity stage with a new one titled `title`.

        Replacement rather than renaming, because the SDK merges stage-name deltas by
        concatenation — a name can only grow. Closing appends no elapsed time: the stage ends
        because a new step started, not because the announced work finished, and a duration
        would claim the opposite.
        """
        self._close_activity(Status.COMPLETED)
        stage = self._choice.create_stage(title)
        stage.open()
        self._activity_stage = stage

    def _close_activity(self, status: Status) -> None:
        """Close the open activity stage if there is one. Doing this twice is harmless.

        Deliberately not a `with` block: `Stage.__exit__` closes unconditionally on the
        exception path, and closing an already-closed stage raises — which would replace the
        exception being handled with a misleading one.
        """
        stage = self._activity_stage
        if stage is None:
            return
        self._activity_stage = None
        stage.close(status)

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
        if not msg.tool_calls:
            return
        self._handle_status_calls(msg.tool_calls)
        start = datetime.now()
        for tc in msg.tool_calls:
            tc_id = tc["id"]
            # A status call gets no pending entry, so it produces neither a `[TOOL]` result
            # stage nor an INFO tool-call event: it is an announcement, not a research action.
            if not tc_id or tc["name"] == UPDATE_STATUS_TOOL_NAME:
                continue
            args_json = json.dumps(tc["args"], default=str, indent=2)
            self._pending_tool_calls[tc_id] = PendingToolCall(
                start=start, tool_name=tc["name"], args_json=args_json
            )

    def _handle_status_calls(self, tool_calls: list[ToolCall]) -> None:
        """Turn one assistant message's status calls into at most one activity stage.

        Several statuses are joined into one title rather than applied in turn: applying them
        would close each stage an instant after opening it, and a stage that opens and closes
        together renders as a step that finished — the impression this stage exists to avoid.
        A status sent alongside the finish sentinel is dropped, since the iteration is ending
        and there is no new step to announce.
        """
        statuses = [
            str(tc["args"].get("status", ""))
            for tc in tool_calls
            if tc["name"] == UPDATE_STATUS_TOOL_NAME
        ]
        if not statuses:
            return
        self._log_status_misuse(status_count=len(statuses), tool_call_count=len(tool_calls))
        if any(tc["name"] == _FINISH_TOOL for tc in tool_calls):
            return
        title = _STATUS_JOIN.join(text for text in (s.strip() for s in statuses) if text)
        if title:
            self._set_activity(title)

    def _log_status_misuse(self, *, status_count: int, tool_call_count: int) -> None:
        """Report the two ways of misusing the status tool, once per assistant message.

        Once per message rather than once per call, so three bad calls do not read as three
        separate incidents. The status text stays out: it is a tool-call argument value, which
        the logging policy keeps out of every record at every level.
        """
        if status_count > 1:
            logger.warning(
                "Status tool called more than once in one message: statuses=%d tool_calls=%d",
                status_count,
                tool_call_count,
            )
        if status_count == tool_call_count:
            logger.warning(
                "Status tool was a message's only tool call: tool_calls=%d",
                tool_call_count,
            )

    def _handle_tool_message(self, msg: ToolMessage) -> None:
        if msg.name == UPDATE_STATUS_TOOL_NAME:
            # The stage was set when the call appeared. What comes back is the acknowledgement
            # the model reads, including any correction — none of it is the user's to see.
            return
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

    def _emit_research_review_result_stage(self, outcome: ResearchReviewOutcome) -> None:
        """Render one research review as a DIAL stage.

        Emitted while the activity stage the same node opened is still open: this stage records a
        decision already taken, the activity stage names what is happening now. The assessment and
        the next steps belong here and nowhere else — the logging-policy content allowlist keeps LLM
        response text out of log records, so the logs carry only the step count.
        """
        title = DialStageResearchReviewFormatter.format_title(
            research_iteration=outcome.research_iteration,
            will_continue=outcome.will_continue,
            duration_seconds=outcome.duration_seconds,
        )
        body = DialStageResearchReviewFormatter.format_body(
            research_iteration=outcome.research_iteration,
            max_research_iterations=outcome.max_research_iterations,
            assessment=outcome.assessment,
            next_steps=outcome.next_steps,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)

    def _emit_research_budget_exhausted_stage(self, outcome: ResearchBudgetExhausted) -> None:
        """Announce a coverage review the iteration cap skipped.

        Emitted while the graph still runs, so it sits among the stages of the research it belongs
        to rather than after the report's. Rendered from the router's numbers alone, with no model
        call — which is why it carries no elapsed time.
        """
        title = DialStageResearchReviewFormatter.format_budget_exhausted_title()
        body = DialStageResearchReviewFormatter.format_budget_exhausted_body(
            research_iteration=outcome.research_iteration,
            max_research_iterations=outcome.max_research_iterations,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)

    def _emit_report_review_result_stage(self, outcome: ReportReviewOutcome) -> None:
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

    def _emit_report_budget_exhausted_stage(self, outcome: ReportBudgetExhausted) -> None:
        """Announce a delivery whose draft the version budget left unreviewed.

        Distinguishes "review approved the draft" from "the budget ran out, so the previous
        review's findings may remain". The router decided it and measured the draft; this decides
        how it looks. No model call was made, so the stage carries no elapsed time.
        """
        title = DialStageReportReviewFormatter.format_budget_exhausted_title(
            draft_number=outcome.draft_number
        )
        body = DialStageReportReviewFormatter.format_budget_exhausted_body(
            draft_number=outcome.draft_number,
            word_count=outcome.word_count,
            max_words=outcome.max_words,
            length_exemptions=outcome.length_exemptions,
            max_versions=outcome.max_versions,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)

    def _emit_report_revision_failed_stage(self, outcome: ReportRevisionFailure) -> None:
        """Announce a revision the report call could not write, and the draft delivered instead.

        Without it the run ends on a review stage asking for a revision that never arrives. The
        body names draft numbers and the failure kind only: the draft being delivered is the
        answer, and the one that was never written has no text to show.
        """
        title = DialStageReportFormatter.format_revision_failed_title(
            failed_draft_number=outcome.failed_draft_number,
            delivered_draft_number=outcome.delivered_draft_number,
        )
        body = DialStageReportFormatter.format_revision_failed_body(
            failed_draft_number=outcome.failed_draft_number,
            delivered_draft_number=outcome.delivered_draft_number,
            error=outcome.error,
        )
        with self._choice.create_stage(title) as stage:
            stage.append_content(body)
