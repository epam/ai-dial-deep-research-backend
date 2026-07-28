"""The three research-graph nodes: researcher, reviewer, report.

- `build_researcher_agent` returns a `create_agent` compiled graph used directly as
  the researcher subgraph node (forced tool choice + the finish_iteration sentinel).
- `make_reviewer_node` returns the reviewer node: an independent structured LLM call
  that judges coverage and produces the next iteration's plan.
- `make_report_node` returns the report node: a streamed LLM call writing the final
  report. Its tokens are the only node output that becomes assistant content.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
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

from dial_deep_research.app.middleware import ImageBudgetMiddleware
from dial_deep_research.settings import settings
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.llm import (
    STREAM_DROP_MAX_ATTEMPTS,
    TRANSIENT_STREAM_DROP_ERRORS,
    LLMModelConfig,
    format_token_usage,
    get_chat_model,
    stream_drop_retry_delay,
    stream_drop_retry_middleware,
    with_stream_drop_retry,
)

from .middleware import ForceToolChoiceMiddleware
from .prompts import (
    REPORT_REQUEST,
    REPORT_SYSTEM_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    ResearchReview,
    render_next_instruction,
    render_plan,
)
from .state import ResearchState

logger = logging.getLogger(__name__)

ReviewerNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]


def build_researcher_agent(tools: list[BaseTool], today_date: str, client_name: str) -> Any:
    """Build the researcher: a `create_agent` over the tools, forced to call a tool every step."""
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=RESEARCHER_SYSTEM_PROMPT.format(
            today_date=today_date,
            client_name=client_name,
        ),
        middleware=[
            *agent_logging_middleware("researcher"),
            stream_drop_retry_middleware(),
            ForceToolChoiceMiddleware(),
            ImageBudgetMiddleware(limit=settings.max_context_images),
        ],
    )


def _render_findings(messages: list[BaseMessage]) -> str:
    """Render the research transcript as a readable findings log for the reviewer.

    Images are noted but not embedded; the reviewer judges coverage from the text the
    tools returned, the searches the researcher ran, and the instructions it followed.
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
            has_image = isinstance(message.content, list) and any(
                isinstance(b, dict) and b.get("type") == "image" for b in message.content
            )
            suffix = " [+image]" if has_image else ""
            lines.append(f"RESULT:{suffix}\n{text or '(no text content)'}")
    return "\n\n".join(lines)


def _should_continue(*, plans_count: int, iteration: int, max_iterations: int) -> bool:
    """One more researcher iteration iff a not-yet-run plan exists and the cap allows it."""
    return plans_count > iteration and iteration < max_iterations


def make_reviewer_node(today_date: str, max_iterations: int) -> ReviewerNode:
    """Build the reviewer node over the given date and iteration cap."""

    async def reviewer(state: ResearchState) -> dict[str, Any]:
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
        # Order sections stable → append-only so successive reviewer calls in a run share a
        # byte prefix (question, then the growing findings) that the provider's prompt cache
        # can reuse; the small plans list, which also only grows, comes last.
        result: dict[str, Any] = await llm.ainvoke(
            [
                SystemMessage(content=REVIEWER_SYSTEM_PROMPT.format(today_date=today_date)),
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

        update: dict[str, Any] = {"iteration": state["iteration"] + 1}
        plans = state["plans"]
        if review.next_steps:
            plans = [*plans, review.next_steps]
            update["plans"] = plans
            update["messages"] = [HumanMessage(content=render_next_instruction(review.next_steps))]

        # Verdict mirrors `route_after_review` over the post-update state, so the
        # skeleton event never disagrees with the actual routing.
        will_continue = _should_continue(
            plans_count=len(plans), iteration=update["iteration"], max_iterations=max_iterations
        )
        logger.info(
            "Iteration reviewed: iteration=%d duration=%.1fs verdict=%s next_plan_steps=%d "
            "tokens=%s",
            update["iteration"],
            time.monotonic() - start,
            "continue" if will_continue else "report",
            len(review.next_steps or []),
            format_token_usage(usage),
        )
        return update

    return reviewer


def make_report_node(today_date: str) -> ReportNode:
    """Build the report node over the given date."""

    async def report(state: ResearchState) -> dict[str, Any]:
        start = time.monotonic()
        llm = get_chat_model(LLMModelConfig())
        plans_text = "\n\n".join(
            f"Plan {i}:\n{render_plan(steps)}" for i, steps in enumerate(state["plans"], start=1)
        )
        report_messages: list[BaseMessage] = [
            SystemMessage(content=REPORT_SYSTEM_PROMPT.format(today_date=today_date)),
            *state["messages"],
            HumanMessage(
                content=REPORT_REQUEST.format(query=state["original_query"], plans=plans_text)
            ),
        ]
        # `with_retry` does not cover streaming, so the stream-drop retry is a loop here. The
        # accumulated chunks reset each attempt, so the persisted report is one attempt's full
        # text (partial tokens an aborted attempt already streamed to the user stay visible).
        chunks: list[str] = []
        usage: UsageMetadata | None = None
        for attempt in range(STREAM_DROP_MAX_ATTEMPTS):
            chunks = []
            usage = None
            try:
                async for chunk in llm.astream(report_messages):
                    text = extract_text_from_content(chunk.content)
                    if text:
                        chunks.append(text)
                    # Usage arrives on the final chunk when stream_usage is on; keep the last.
                    if chunk_usage := chunk.usage_metadata:
                        usage = chunk_usage
                break
            except TRANSIENT_STREAM_DROP_ERRORS:
                if attempt + 1 >= STREAM_DROP_MAX_ATTEMPTS:
                    raise
                logger.warning(
                    "Report stream dropped mid-response, retrying (attempt %d of %d)",
                    attempt + 2,
                    STREAM_DROP_MAX_ATTEMPTS,
                )
                await asyncio.sleep(stream_drop_retry_delay(attempt))
        text = "".join(chunks)
        logger.info(
            "Report generated: duration=%.1fs length=%d tokens=%s",
            time.monotonic() - start,
            len(text),
            format_token_usage(usage),
        )
        return {"report": text, "messages": [AIMessage(content=text)]}

    return report


def route_after_review(max_iterations: int) -> Callable[[ResearchState], str]:
    """Decide the edge out of the reviewer node.

    Continue researching when the reviewer recorded a plan for a not-yet-run iteration
    (`len(plans) > iteration`) and the iteration cap is not yet reached; otherwise report.
    """

    def route(state: ResearchState) -> str:
        if _should_continue(
            plans_count=len(state["plans"]),
            iteration=state["iteration"],
            max_iterations=max_iterations,
        ):
            return "researcher"
        return "report"

    return route
