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

`decide_report_action` is the single source for what happens to a reviewed draft: the router
turns its result into an edge and the review node logs the same value.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum
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
    count_words,
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
    LENGTH_REVISION_INSTRUCTION,
    REPORT_REQUEST,
    REPORT_REVIEW_REQUEST,
    REPORT_REVIEW_SYSTEM_PROMPT,
    REPORT_REVISION_REQUEST,
    REPORT_SYSTEM_PROMPT,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    ReportReview,
    ResearchReview,
    render_next_instruction,
    render_plan,
    render_protected_section_names,
    render_report_structure,
)
from .state import ResearchState

logger = logging.getLogger(__name__)

ResearchReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]


def build_research_agent(tools: list[BaseTool], today_date: str, client_name: str) -> Any:
    """Build research-agent: a `create_agent` over the tools, forced to call a tool every step."""
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT.format(
            today_date=today_date,
            client_name=client_name,
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


def _should_continue_research(*, plans_count: int, research_iteration: int) -> bool:
    """One more research-agent iteration iff research-review recorded a plan for a not-yet-run
    iteration. The iteration cap needs no check here: it is enforced before the review runs
    (`route_after_research_agent`), so a recorded plan may always run."""
    return plans_count > research_iteration


def research_budget_exhausted(*, research_iteration: int, max_iterations: int) -> bool:
    """True iff the just-finished iteration is the last permitted one, so no further one may run.

    Both numbers count iterations, 1-based — the research loop's mirror of
    `review_budget_exhausted`: a "continue" verdict on the last permitted iteration could not
    be acted on, so the router skips the review call when this holds.
    """
    return research_iteration >= max_iterations


def make_research_review_node(today_date: str) -> ResearchReviewNode:
    """Build the research-review node over the given date."""

    async def research_review(state: ResearchState) -> dict[str, Any]:
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
        # Order sections stable → append-only so successive research-review calls in a run share a
        # byte prefix (question, then the growing findings) that the provider's prompt cache
        # can reuse; the small plans list, which also only grows, comes last.
        result: dict[str, Any] = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCH_REVIEW_SYSTEM_PROMPT.format(today_date=today_date)),
                HumanMessage(
                    content=(
                        f"Research question:\n{state['original_query']}\n\n"
                        f"Findings gathered:\n{_render_findings(state['messages'])}\n\n"
                        f"Plans pursued so far:\n{plans_text}"
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

        # Verdict mirrors `route_after_research_review` over the post-update state, so the
        # skeleton event never disagrees with the actual routing.
        will_continue = _should_continue_research(
            plans_count=len(plans), research_iteration=state["research_iteration"]
        )
        logger.info(
            "Research iteration reviewed: research_iteration=%d duration=%.1fs verdict=%s "
            "next_plan_steps=%d tokens=%s",
            state["research_iteration"],
            time.monotonic() - start,
            "continue" if will_continue else "report",
            len(review.next_steps or []),
            format_token_usage(usage),
        )
        return update

    return research_review


class ReportAction(StrEnum):
    """What the app does with a reviewed draft. Distinct from the review model's verdict."""

    DELIVER = "deliver"
    REVISE = "revise"
    REVISE_OVER_CEILING = "revise_over_ceiling"


class ReportVerdict(StrEnum):
    """What the review model said, or that its call never produced a verdict."""

    APPROVED = "approved"
    REVISE = "revise"
    FAILED = "failed"


class ReportReviewOutcome(BaseModel):
    """One report review's result, handed to the runner so it can render a DIAL stage.

    Carries no DIAL types: the node decides what to report, the runner decides how it is
    rendered. `findings` is the review's text and belongs in the stage only — never in a log
    record, per the logging-policy content allowlist.
    """

    draft_number: int
    word_count: int
    max_words: int
    findings: list[str]
    verdict: ReportVerdict
    action: ReportAction
    duration_seconds: float


ReportReviewStageEmitter = Callable[[ReportReviewOutcome], None]


def review_budget_exhausted(*, report_version: int, max_versions: int) -> bool:
    """True iff the current draft is the last permitted version, so no rewrite may follow it.

    Both numbers count report versions, 1-based, which keeps the comparison plain. Shared by
    the router (which skips the review when it holds) and the runner (which then announces the
    unreviewed delivery), so the two cannot disagree.
    """
    return report_version >= max_versions


def decide_report_action(
    *,
    word_count: int,
    max_words: int,
    findings: list[str],
) -> tuple[ReportAction, str | None]:
    """Decide what happens to a reviewed draft, and the instruction a revision gets.

    The single source for that decision: the router turns the action into an edge and the
    report-review node logs the same value, so the log can never describe a different
    outcome than the one the graph took.

    Runs only for drafts with a rewrite still in budget — `route_after_report` gates the
    review on the budget — so a requested revision is always permitted. Exceeding the ceiling
    forces a revision even when the review found nothing: the count is the app's, not the
    model's opinion. A failed review call reaches here with no findings, so it revises on
    length alone or delivers.
    """
    over_ceiling = word_count > max_words
    if not findings and not over_ceiling:
        return ReportAction.DELIVER, None

    length_instruction = (
        LENGTH_REVISION_INSTRUCTION.format(word_count=word_count, max_words=max_words)
        if over_ceiling
        else None
    )
    if not findings:
        return ReportAction.REVISE_OVER_CEILING, length_instruction
    parts = [f"- {finding}" for finding in findings]
    if length_instruction:
        parts.append(f"- {length_instruction}")
    return ReportAction.REVISE, "\n".join(parts)


def make_report_node(
    today_date: str, sections: Sequence[ReportSection], max_words: int
) -> ReportNode:
    """Build the report node: it writes the first draft, and every revision after it."""

    async def report(state: ResearchState) -> dict[str, Any]:
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
                    report_structure=render_report_structure(sections),
                    max_words=max_words,
                    protected_sections=render_protected_section_names(sections),
                )
            ),
            *state["messages"],
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
                        word_count=count_words(previous_draft),
                        max_words=max_words,
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
            count_words(text),
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
    emit_stage: ReportReviewStageEmitter,
) -> ReportReviewNode:
    """Build the report-review node: judge the draft, emit its stage, decide the next step.

    It sees the draft, the configuration and the query and plan — never the findings, which is
    why it cannot reopen evidence coverage. A failing call never fails the turn: the loop falls
    back to the measured count alone.
    """

    async def report_review(state: ResearchState) -> dict[str, Any]:
        start = time.monotonic()
        draft = state["report"] or ""
        word_count = count_words(draft)
        draft_number = state.get("report_version", 0)

        findings: list[str] = []
        verdict = ReportVerdict.FAILED
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
                            max_words=max_words,
                            query=state["original_query"],
                            plan=render_plan(state["plans"][0]) if state["plans"] else "(none)",
                            word_count=word_count,
                            draft=draft,
                        )
                    ),
                ]
            )
            if result["parsing_error"] is not None:
                raise result["parsing_error"]
            review: ReportReview = result["parsed"]
            usage = result["raw"].usage_metadata
            findings = list(review.findings)
            verdict = ReportVerdict.APPROVED if not findings else ReportVerdict.REVISE
        except Exception as exc:
            # A failed review must not cost the report. The measured count still applies, so
            # the loop can still shorten an over-long draft on its own instruction.
            logger.warning(
                "Report review failed, falling back to the measured length: draft=%d error=%s",
                draft_number,
                type(exc).__name__,
            )

        action, instruction = decide_report_action(
            word_count=word_count,
            max_words=max_words,
            findings=findings,
        )
        duration = time.monotonic() - start
        emit_stage(
            ReportReviewOutcome(
                draft_number=draft_number,
                word_count=word_count,
                max_words=max_words,
                findings=findings,
                verdict=verdict,
                action=action,
                duration_seconds=duration,
            )
        )
        logger.info(
            "Report reviewed: draft=%d duration=%.1fs verdict=%s action=%s words=%d ceiling=%d "
            "findings=%d tokens=%s",
            draft_number,
            duration,
            verdict.value,
            action.value,
            word_count,
            max_words,
            len(findings),
            format_token_usage(usage),
        )
        return {"report_revision_instruction": instruction}

    return report_review


def route_after_research_agent(max_iterations: int) -> Callable[[ResearchState], str]:
    """Decide the edge out of the research-agent node.

    An iteration is reviewed only while another iteration may still run: a "continue" verdict
    on the last permitted iteration could not be acted on, so the call is not made and the
    findings go straight to the report. Logged here — no node sits on that path.
    """

    def route(state: ResearchState) -> str:
        research_iteration = state["research_iteration"]
        if research_budget_exhausted(
            research_iteration=research_iteration, max_iterations=max_iterations
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

    Revise iff the review left an instruction. `decide_report_action` already folded in the
    measured count, so this reads one field rather than re-deciding.
    """

    def route(state: ResearchState) -> str:
        return "report" if state.get("report_revision_instruction") else "end"

    return route
