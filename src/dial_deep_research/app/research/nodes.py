"""The four research-graph nodes: research-agent, research-review, report, report-review.

- `build_research_agent` returns a `create_agent` compiled graph used directly as
  the research-agent subgraph node (forced tool choice + the finish_iteration sentinel).
- `make_research_review_node` returns the research-review node: an independent structured LLM call
  that judges coverage and produces the next iteration's plan.
- `make_report_node` returns the report node: it writes the first draft and every revision after
  it. Nothing it produces is streamed to the user — a draft may still be revised, so only the
  draft the loop settles on becomes assistant content, appended by the runner.
- `make_report_review_node` returns the report-review node: an independent structured LLM call
  that judges the draft against the report rules, emits its DIAL stage through the runner-supplied
  callback, and records the instruction a revision would act on.

`ReportReviewOutcome.revision_instruction` is the single source for what happens to a reviewed
draft: the router turns its presence into an edge and the review node logs the same value.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    UsageMetadata,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from dial_deep_research.app.middleware import ImageBudgetMiddleware
from dial_deep_research.app_properties import ReportSection
from dial_deep_research.settings import settings
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.content import (
    count_image_blocks,
    extract_text_from_content,
)
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    format_token_usage,
    get_chat_model,
    stream_drop_retry_middleware,
    with_stream_drop_retry,
)

from .middleware import ForceToolChoiceMiddleware, IterationCounterMiddleware
from .prompts import (
    REPORT_REQUEST,
    REPORT_REVIEW_REQUEST,
    REPORT_REVIEW_SYSTEM_PROMPT,
    REPORT_REVISION_REQUEST,
    REPORT_SYSTEM_PROMPT,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_HUMAN_MESSAGE,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    ReportReview,
    ResearchReview,
    render_length_exemptions,
    render_next_instruction,
    render_plan,
    render_protected_section_names,
    render_report_structure,
)
from .report_length import count_report_words
from .report_rules import build_report_rules, render_writer_instructions
from .state import ResearchState
from .tools import (
    HOW_TO_WRITE_STATUS,
    RULE_NEVER_ALONE,
    RULE_NOT_WITH_FINISH,
    RULE_ONCE_PER_TURN,
    UPDATE_STATUS_TOOL_NAME,
    WHEN_TO_ANNOUNCE,
)

logger = logging.getLogger(__name__)

ResearchReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]

# Names the work a node is starting. The runner renders it as the open activity stage; a node
# never touches DIAL itself.
ActivityEmitter = Callable[[str], None]

# What each node calls itself while it runs. Written like research-agent's own statuses — short,
# present tense, no prefix — so the one live line reads the same whoever set it.
RESEARCH_REVIEW_ACTIVITY = "Reviewing research findings"
REPORT_ACTIVITY = "Writing the report"
REPORT_REVIEW_ACTIVITY = "Reviewing the report"


def build_research_agent(tools: list[BaseTool], today_date: str, client_name: str) -> Any:
    """Build research-agent: a `create_agent` over the tools, forced to call a tool every step."""
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT.format(
            today_date=today_date,
            client_name=client_name,
            # The same sentences the status tool's description carries, and that its response
            # quotes back when a rule is broken — one wording, so the model never has to
            # reconcile two.
            how_to_write_status=HOW_TO_WRITE_STATUS,
            when_to_announce=WHEN_TO_ANNOUNCE,
            rule_once_per_turn=RULE_ONCE_PER_TURN,
            rule_never_alone=RULE_NEVER_ALONE,
            rule_not_with_finish=RULE_NOT_WITH_FINISH,
        ),
        middleware=[
            *agent_logging_middleware("research-agent"),
            stream_drop_retry_middleware(),
            ForceToolChoiceMiddleware(),
            ImageBudgetMiddleware(limit=settings.max_context_images),
            IterationCounterMiddleware(),
        ],
    )


def _render_findings(messages: list[BaseMessage]) -> str:
    """Render the research transcript as a readable findings log for research-review.

    Images are noted but not embedded; research-review judges coverage from the text the
    tools returned, the searches research-agent ran, and the instructions it followed.
    """
    lines: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            lines.append(f"INSTRUCTION:\n{extract_text_from_content(message.content)}")
        elif isinstance(message, AIMessage):
            for tc in message.tool_calls:
                lines.append(f"SEARCHED: {tc['name']}({tc['args']})")
            if text := extract_text_from_content(message.content).strip():
                lines.append(f"NOTE: {text}")
        elif isinstance(message, ToolMessage):
            text = extract_text_from_content(message.content).strip()
            suffix = " [+image]" if count_image_blocks(message.content) else ""
            lines.append(f"RESULT:{suffix}\n{text or '(no text content)'}")
    return "\n\n".join(lines)


def _drop_tool_calls(message: AIMessage, ids: set[str]) -> AIMessage | None:
    """`message` without the tool calls in `ids`, or `None` if nothing of it is left.

    `additional_kwargs["tool_calls"]` is cleaned alongside the parsed list because
    langchain_openai falls back to it whenever the parsed list is empty, which would put the
    removed call straight back on the wire.
    """
    tool_calls = [tc for tc in message.tool_calls if tc["id"] not in ids]
    additional = {k: v for k, v in message.additional_kwargs.items() if k != "tool_calls"}
    raw = message.additional_kwargs.get("tool_calls") or []
    if remaining := [tc for tc in raw if tc.get("id") not in ids]:
        additional["tool_calls"] = remaining
    if not tool_calls and not extract_text_from_content(message.content).strip():
        return None
    return message.model_copy(update={"tool_calls": tool_calls, "additional_kwargs": additional})


def _strip_status_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The transcript without research-agent's status announcements.

    What the agent told the user it was doing is not evidence: it must not be weighed as a
    search when coverage is judged, nor sit in the context of the model writing the report. A
    status usually shares its message with real tool calls, so the call is removed from the
    message rather than the message from the transcript, and its result is removed with it —
    every remaining call keeps its own result, which providers require.

    Being deterministic, this preserves the byte prefix successive calls share (see the
    prompt-caching spec).
    """
    dropped_ids: set[str] = set()
    kept: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            if message.tool_call_id not in dropped_ids:
                kept.append(message)
            continue
        if isinstance(message, AIMessage) and message.tool_calls:
            status_ids = {
                tc["id"]
                for tc in message.tool_calls
                if tc["name"] == UPDATE_STATUS_TOOL_NAME and tc["id"]
            }
            if status_ids:
                dropped_ids |= status_ids
                if (stripped := _drop_tool_calls(message, status_ids)) is not None:
                    kept.append(stripped)
                continue
        kept.append(message)
    return kept


def _should_continue_research(*, plans_count: int, research_iteration: int) -> bool:
    """One more research-agent iteration iff research-review recorded a plan for a not-yet-run
    iteration. The iteration cap needs no check here: it is enforced before the review runs
    (`route_after_research_agent`), so a recorded plan may always run."""
    return plans_count > research_iteration


def research_budget_exhausted(*, research_iteration: int, max_research_iterations: int) -> bool:
    """True iff the just-finished iteration is the last permitted one, so no further one may run.

    Both numbers count iterations, 1-based — the research loop's mirror of
    `review_budget_exhausted`: a "continue" verdict on the last permitted iteration could not
    be acted on, so the router skips the review call when this holds.
    """
    return research_iteration >= max_research_iterations


class ResearchReviewOutcome(BaseModel):
    """One research review's result, handed to the runner so it can render a DIAL stage.

    Carries no DIAL types: the node decides what to report, the runner decides how it is rendered.
    `max_research_iterations` accompanies the iteration number so the stage can say how much further
    research may go. `will_continue` comes from the same function the router calls, so the stage
    cannot announce one route while the graph takes the other. There is no error field, unlike
    `ReportReviewOutcome`: research-review re-raises a failed call instead of absorbing it, so a
    failure ends the turn and shows as the activity stage closing failed. The assessment and the
    next steps belong in the stage only — never in a log record, per the logging-policy content
    allowlist.
    """

    research_iteration: int
    max_research_iterations: int
    assessment: str
    next_steps: list[str]
    will_continue: bool
    duration_seconds: float


ResearchReviewResultStageEmitter = Callable[[ResearchReviewOutcome], None]


def make_research_review_node(
    today_date: str,
    max_research_iterations: int,
    emit_result_stage: ResearchReviewResultStageEmitter,
    emit_activity: ActivityEmitter,
) -> ResearchReviewNode:
    """Build the research-review node: judge coverage, emit its result stage, plan what remains.

    `max_research_iterations` is not a bound this node enforces — the router does that before the
    node is reached. It is here for the stage, which states the cap beside the iteration number.
    """

    async def research_review(state: ResearchState) -> dict[str, Any]:
        emit_activity(RESEARCH_REVIEW_ACTIVITY)
        start = time.monotonic()
        # include_raw keeps the raw AIMessage alongside the parsed verdict so we can log the
        # call's token usage (including cached input tokens); with it, parse failures surface
        # as `parsing_error` instead of raising inside the chain, so we re-raise below to keep
        # the previous fail-loud behavior.
        llm = with_stream_drop_retry(
            get_chat_model(LLMModelConfig()).with_structured_output(
                ResearchReview, include_raw=True
            )
        )
        plans_text = "\n\n".join(
            f"Plan {i}:\n{render_plan(steps)}" for i, steps in enumerate(state["plans"], start=1)
        )
        result: dict[str, Any] = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCH_REVIEW_SYSTEM_PROMPT.format(today_date=today_date)),
                HumanMessage(
                    content=RESEARCH_REVIEW_HUMAN_MESSAGE.format(
                        query=state["original_query"],
                        findings=_render_findings(_strip_status_calls(state["messages"])),
                        plans=plans_text,
                    )
                ),
            ]
        )

        if result["parsing_error"] is not None:
            raise result["parsing_error"]
        review: ResearchReview = result["parsed"]
        usage = result["raw"].usage_metadata

        # `research_iteration` is already the just-reviewed iteration's number: the
        # research-agent node counts itself (`IterationCounterMiddleware`), so this node only
        # records the plan.
        update: dict[str, Any] = {}
        plans = state["plans"]
        if review.next_steps:
            plans = [*plans, review.next_steps]
            update["plans"] = plans
            update["messages"] = [HumanMessage(content=render_next_instruction(review.next_steps))]

        # Verdict mirrors `route_after_research_review` over the post-update state, so neither the
        # skeleton event nor the stage disagrees with the actual routing.
        will_continue = _should_continue_research(
            plans_count=len(plans), research_iteration=state["research_iteration"]
        )
        duration = time.monotonic() - start
        emit_result_stage(
            ResearchReviewOutcome(
                research_iteration=state["research_iteration"],
                max_research_iterations=max_research_iterations,
                assessment=review.assessment,
                next_steps=list(review.next_steps or []),
                will_continue=will_continue,
                duration_seconds=duration,
            )
        )
        logger.info(
            "Research iteration reviewed: research_iteration=%d duration=%.1fs verdict=%s "
            "next_plan_steps=%d tokens=%s",
            state["research_iteration"],
            duration,
            "continue" if will_continue else "report",
            len(review.next_steps or []),
            format_token_usage(usage),
        )
        return update

    return research_review


class ReportReviewOutcome(BaseModel):
    """One report review's result, handed to the runner so it can render a DIAL stage.

    Carries no DIAL types: the node decides what to report, the runner decides how it is
    rendered. `length_exemptions` names what `word_count` leaves out, so the stage can state the
    measure it shows rather than let a reader count the report and find a different number.
    `violations` is everything the next revision must fix — the review model's violations, with
    the app-measured length violation prepended when the draft exceeds the ceiling. `error` records a failed review call (the exception kind); the length violation
    joins the list regardless, so a failed call still carries it. The violation text belongs
    in the stage only — never in a log record, per the logging-policy content allowlist.
    """

    draft_number: int
    word_count: int
    max_words: int
    length_exemptions: str
    violations: list[str]
    error: str | None
    duration_seconds: float

    @property
    def revision_instruction(self) -> str | None:
        """The instruction the next revision acts on; None delivers the draft as it stands.

        The single source for that decision: the review node stores it in the state, where its
        presence routes the loop back to the report node, and the stage title reflects the same
        value, so the two cannot disagree.
        """
        if not self.violations:
            return None
        return "\n".join(
            f"{i}. {violation}" for i, violation in enumerate(self.violations, start=1)
        )


ReportReviewResultStageEmitter = Callable[[ReportReviewOutcome], None]


def review_budget_exhausted(*, report_version: int, max_versions: int) -> bool:
    """True iff the current draft is the last permitted version, so no rewrite may follow it.

    Both numbers count report versions, 1-based, which keeps the comparison plain. Shared by
    the router (which skips the review when it holds) and the runner (which then announces the
    unreviewed delivery), so the two cannot disagree.
    """
    return report_version >= max_versions


def make_report_node(
    today_date: str,
    sections: Sequence[ReportSection],
    max_words: int,
    emit_activity: ActivityEmitter,
) -> ReportNode:
    """Build the report node: it writes the first draft, and every revision after it."""

    async def report(state: ResearchState) -> dict[str, Any]:
        emit_activity(REPORT_ACTIVITY)
        start = time.monotonic()
        llm = with_stream_drop_retry(get_chat_model(LLMModelConfig()))
        plans_text = "\n\n".join(
            f"Plan {i}:\n{render_plan(steps)}" for i, steps in enumerate(state["plans"], start=1)
        )
        previous_draft = state.get("report")
        report_messages: list[BaseMessage] = [
            SystemMessage(
                content=REPORT_SYSTEM_PROMPT.format(
                    today_date=today_date,
                    rules=render_writer_instructions(
                        build_report_rules(sections=sections, max_words=max_words)
                    ),
                    protected_sections=render_protected_section_names(sections),
                )
            ),
            *_strip_status_calls(state["messages"]),
            HumanMessage(
                content=REPORT_REQUEST.format(query=state["original_query"], plans=plans_text)
            ),
        ]
        if previous_draft is not None:
            # Appended after the first draft's request, never inserted before the transcript,
            # so the byte prefix holds and the provider's prompt cache can serve it.
            report_messages.append(
                HumanMessage(
                    content=REPORT_REVISION_REQUEST.format(
                        word_count=count_report_words(previous_draft, sections=sections),
                        max_words=max_words,
                        length_exemptions=render_length_exemptions(sections),
                        instruction=state.get("report_revision_instruction") or "",
                        draft=previous_draft,
                    )
                )
            )
        draft_number = state.get("report_version", 0) + 1
        try:
            response = await llm.ainvoke(report_messages)
        except Exception as exc:
            # Once a draft exists, no later failure may discard it: deliver the previous draft
            # and leave the loop. The first draft has nothing to fall back to, so it propagates.
            if previous_draft is None:
                raise
            logger.warning(
                "Report revision failed, delivering the previous draft: "
                "failed_draft=%d delivered_draft=%d error=%s",
                draft_number,
                draft_number - 1,
                type(exc).__name__,
            )
            return {"report_revision_failed": True}

        text = extract_text_from_content(response.content)
        logger.info(
            "Report generated: draft=%d duration=%.1fs length=%d words=%d tokens=%s",
            draft_number,
            time.monotonic() - start,
            len(text),
            count_report_words(text, sections=sections),
            format_token_usage(response.usage_metadata),
        )
        # No `AIMessage` into `messages`: drafts stay out of the transcript, so a rejected one
        # is never re-sent to a model nor persisted. The runner builds the assistant message
        # for the delivered report from the graph's final state.
        return {"report": text, "report_version": draft_number}

    return report


def make_report_review_node(
    today_date: str,
    sections: Sequence[ReportSection],
    max_words: int,
    emit_result_stage: ReportReviewResultStageEmitter,
    emit_activity: ActivityEmitter,
) -> ReportReviewNode:
    """Build the report-review node: judge the draft, emit its result stage, decide the next step.

    Two judgements meet here. The app's own rules (`report_rules`) are checked in Python over the
    draft text, and the review model judges what needs a reader — padding, banned annotations,
    protected-section rules, citation format. It sees the draft, the configuration and the query
    and plan, never the research findings, which is why it cannot reopen evidence coverage. A
    failing call never fails the turn: the rules still run and their violations still stand.
    """
    rules = build_report_rules(sections=sections, max_words=max_words)

    async def report_review(state: ResearchState) -> dict[str, Any]:
        emit_activity(REPORT_REVIEW_ACTIVITY)
        start = time.monotonic()
        draft = state["report"] or ""
        word_count = count_report_words(draft, sections=sections)
        draft_number = state.get("report_version", 0)

        violations: list[str] = []
        error: str | None = None
        usage: UsageMetadata | None = None
        try:
            llm = with_stream_drop_retry(
                get_chat_model(LLMModelConfig()).with_structured_output(
                    ReportReview, include_raw=True
                )
            )
            result: dict[str, Any] = await llm.ainvoke(
                [
                    SystemMessage(
                        content=REPORT_REVIEW_SYSTEM_PROMPT.format(today_date=today_date)
                    ),
                    HumanMessage(
                        content=REPORT_REVIEW_REQUEST.format(
                            report_structure=render_report_structure(sections),
                            protected_sections=render_protected_section_names(sections),
                            query=state["original_query"],
                            plan=render_plan(state["plans"][0]) if state["plans"] else "(none)",
                            draft=draft,
                        )
                    ),
                ]
            )
            if result["parsing_error"] is not None:
                raise result["parsing_error"]
            review: ReportReview = result["parsed"]
            usage = result["raw"].usage_metadata
            violations = list(review.report_violations)
        except Exception as exc:
            # A failed review must not cost the report. The measured count still applies, so
            # the loop can still shorten an over-long draft on its own instruction.
            error = type(exc).__name__
            logger.warning(
                "Report review failed, falling back to the measured length: draft=%d error=%s",
                draft_number,
                error,
            )

        # The rules are the app's own, not the model's opinion: their violations join the list
        # whether the model reported any, reported none, or the call failed — so an approving
        # review cannot pass a draft that breaks one, and a failed review still shortens an
        # over-long draft and reports a mis-headed section.
        rule_violations = [v for rule in rules for v in rule.violations(draft)]
        violations = [*rule_violations, *violations]
        duration = time.monotonic() - start
        outcome = ReportReviewOutcome(
            draft_number=draft_number,
            word_count=word_count,
            max_words=max_words,
            length_exemptions=render_length_exemptions(sections),
            violations=violations,
            error=error,
            duration_seconds=duration,
        )
        emit_result_stage(outcome)
        logger.info(
            "Report reviewed: draft=%d duration=%.1fs outcome=%s error=%s words=%d "
            "ceiling=%d violations=%d tokens=%s",
            draft_number,
            duration,
            "revise" if outcome.revision_instruction else "deliver",
            error,
            word_count,
            max_words,
            len(violations),
            format_token_usage(usage),
        )
        return {"report_revision_instruction": outcome.revision_instruction}

    return report_review


def route_after_research_agent(max_research_iterations: int) -> Callable[[ResearchState], str]:
    """Decide the edge out of the research-agent node.

    An iteration is reviewed only while another iteration may still run: a "continue" verdict
    on the last permitted iteration could not be acted on, so the call is not made and the
    findings go straight to the report. Logged here — no node sits on that path.
    """

    def route(state: ResearchState) -> str:
        research_iteration = state["research_iteration"]
        if research_budget_exhausted(
            research_iteration=research_iteration, max_research_iterations=max_research_iterations
        ):
            logger.info(
                "Research iteration budget exhausted: research_iteration=%d", research_iteration
            )
            return "report"
        return "research-review"

    return route


def route_after_research_review() -> Callable[[ResearchState], str]:
    """Decide the edge out of the research-review node.

    Continue researching when research-review recorded a plan for a not-yet-run iteration
    (`len(plans) > iteration`); otherwise report.
    """

    def route(state: ResearchState) -> str:
        if _should_continue_research(
            plans_count=len(state["plans"]), research_iteration=state["research_iteration"]
        ):
            return "research-agent"
        return "report"

    return route


def route_after_report(max_versions: int) -> Callable[[ResearchState], str]:
    """Decide the edge out of the report node.

    Three exits. A revision whose own call failed leaves the loop immediately with the previous
    draft: returning to review would re-judge an unchanged draft and route straight back to a
    call that fails again, and since a failed revision writes nothing, no counter would bound
    that cycle. The last permitted version is delivered without a review call — a verdict that
    cannot be acted on is not worth one; the runner announces the unreviewed delivery. A budget
    of one is the same gate failing already for the first draft. Otherwise the draft is
    reviewed.
    """

    def route(state: ResearchState) -> str:
        if state.get("report_revision_failed"):
            return "end"
        exhausted = review_budget_exhausted(
            report_version=state.get("report_version", 0), max_versions=max_versions
        )
        return "end" if exhausted else "report-review"

    return route


def route_after_report_review() -> Callable[[ResearchState], str]:
    """Decide the edge out of the report-review node.

    Revise iff the review left an instruction. `revision_instruction` already folded in the
    measured count, so this reads one field rather than re-deciding.
    """

    def route(state: ResearchState) -> str:
        return "report" if state.get("report_revision_instruction") else "end"

    return route
