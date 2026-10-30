"""The four research-graph nodes: research-agent, research-review, report, report-review.

- `build_research_agent` returns research-agent, a `create_agent` compiled graph (forced tool
  choice + the finish_iteration sentinel), and `make_research_agent_node` the node that runs one
  iteration of it over the research graph's state.
- `make_research_review_node` returns the research-review node: an independent structured LLM call
  that judges coverage and produces the next iteration's plan.
- `make_report_node` returns the report node: it writes the first draft and every revision after
  it. Nothing it produces is streamed to the user — a draft may still be revised, so only the
  draft the loop settles on becomes assistant content, appended by the runner.
- `make_report_review_node` returns the report-review node: the app's own rules and two LLM calls
  judge the draft, its DIAL stage goes out through the runner-supplied callback, and the round is
  stored whole, so the next revision's instruction is built from it.

Each node appends its model's response to the state whole, and derives what it needs from those
lists on every run (the plan list, the draft number, the revision instruction), so a run resumed
from a research record derives them exactly as a fresh run does. `review_violations` is the single
source for what happens to a reviewed draft: the router, the writer and the review stage all read
the latest round through it.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable, Collection, Sequence
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    UsageMetadata,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from dial_deep_research.app.middleware import ImageBudgetMiddleware
from dial_deep_research.app.tool_failures import RetryVerdict, ToolFailureMiddleware
from dial_deep_research.app_properties import (
    GlossaryTools,
    QualityRule,
    ReportSection,
    RuleStep,
    SourceKind,
)
from dial_deep_research.settings import settings
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.content import (
    count_image_blocks,
    extract_text_from_content,
)
from dial_deep_research.utils.dial_stages import ReviewTally
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    ReasoningEffortEnum,
    format_token_usage,
    get_chat_model,
    stream_drop_retry_middleware,
    with_stream_drop_retry,
)

from .citation_lookups import CitationLookups
from .middleware import ForceToolChoiceMiddleware
from .prompts import (
    GROUNDED_REVIEW_SYSTEM_MESSAGE,
    REPORT_REQUEST,
    REPORT_REVIEW_REQUEST,
    REPORT_REVISION_REQUEST,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_HUMAN_MESSAGE,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    ReportReview,
    ResearchReview,
    render_blind_review_system_prompt,
    render_client_rules,
    render_generic_rules,
    render_grounded_review_prompt,
    render_next_instruction,
    render_plan,
    render_protected_section_names,
    render_report_structure,
    render_report_system_prompt,
)
from .report_length import LENGTH_EXEMPTIONS, count_report_words
from .report_rules import build_report_rules, render_writer_instructions
from .state import ReportReviewRound, ResearchState
from .tools import RULE_NEVER_ALONE, RULE_ONCE_PER_TURN, UPDATE_STATUS_TOOL_NAME

logger = logging.getLogger(__name__)

ResearchAgentNode = Callable[[ResearchState, RunnableConfig], Awaitable[dict[str, Any]]]
ResearchReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]
ReportReviewNode = Callable[[ResearchState], Awaitable[dict[str, Any]]]

# Names the work a node is starting. The runner renders it as the open activity stage; a node
# never touches DIAL itself.
ActivityEmitter = Callable[[str], None]

# What each node calls itself while it runs. Written like research-agent's own statuses — short,
# present tense, no prefix — so the one live line reads the same whoever set it.
RESEARCH_REVIEW_ACTIVITY = "Reviewing the research findings"
REPORT_ACTIVITY = "Writing the report"
REPORT_REVIEW_ACTIVITY = "Reviewing the report"


def build_research_agent(
    tools: list[BaseTool],
    today_date: str,
    client_name: str,
    data_sources: str,
    data_sources_instructions: str,
    source_kinds: Collection[SourceKind],
    client_rules: Sequence[QualityRule],
    glossary: GlossaryTools | None,
) -> Any:
    """Build research-agent: a `create_agent` over the tools, forced to call a tool every step.

    `data_sources` is the turn's data-sources string, and `data_sources_instructions` what the
    agent is told about the app's own dataset and glossary calls (empty when nothing applies).
    `client_rules` is the channel's own rules, whose research-agent parts follow the generic ones.
    `source_kinds` is the kinds of source the channel's servers give it; the generic rules are
    told them, so their parts about a missing kind do not apply. `glossary` is the channel's
    glossary configuration, which adds the generic rules that need a glossary.
    """
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT.format(
            today_date=today_date,
            client_name=client_name,
            data_sources=data_sources,
            data_sources_instructions=data_sources_instructions,
            generic_rules=render_generic_rules(
                RuleStep.RESEARCH_AGENT, source_kinds=source_kinds, glossary=glossary is not None
            ),
            client_rules=render_client_rules(client_rules, step=RuleStep.RESEARCH_AGENT),
            # The two rules the status tool quotes back when it catches one being broken, so the
            # correction repeats the instruction word for word. The prompt writes its other status
            # rules itself.
            rule_once_per_turn=RULE_ONCE_PER_TURN,
            rule_never_alone=RULE_NEVER_ALONE,
            verdict_retry_now=RetryVerdict.RETRY_NOW,
            verdict_retry_later=RetryVerdict.RETRY_LATER,
            verdict_will_not_help=RetryVerdict.WILL_NOT_HELP,
        ),
        middleware=[
            *agent_logging_middleware("research-agent"),
            stream_drop_retry_middleware(),
            ForceToolChoiceMiddleware(),
            ImageBudgetMiddleware(limit=settings.max_context_images),
            ToolFailureMiddleware(),
        ],
    )


def make_research_agent_node(agent: Any) -> ResearchAgentNode:
    """The research-agent node: one iteration of `agent` over `research_agent_messages`.

    `create_agent` fixes the agent's conversation key as `messages`, and a compiled graph added
    directly as a node shares only the channels its parent names the same. So the node maps the
    conversation in and out, and counts the iteration once the agent returns: a failure inside
    the iteration leaves the count as it was, so a resumed run reads the same count until that
    iteration ends. The agent's own stream parts keep the namespace `research-agent:<task id>` and
    the key `messages`, which the runner reads.

    The node passes its own `config` on, because `create_agent` presets `recursion_limit=9_999`
    on the graph it returns, and that preset wins over an inherited limit. Only a config passed
    to `ainvoke` wins over it, so without one an agent that never finishes would not be stopped
    by the channel's step budget.
    """

    async def research_agent(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
        result = await agent.ainvoke({"messages": state["research_agent_messages"]}, config=config)
        return {
            "research_agent_messages": result["messages"],
            "research_iteration": state["research_iteration"] + 1,
        }

    return research_agent


def iteration_plans(state: ResearchState) -> list[list[str]]:
    """The plan of each iteration so far: the approved plan, then the next steps of each research
    review that returned some, which are exactly the steps research-agent was given."""
    return [
        state["approved_plan"],
        *(review.next_steps for review in state["research_reviews"] if review.next_steps),
    ]


def _render_plans(state: ResearchState) -> str:
    return "\n\n".join(
        f"Plan {i}:\n{render_plan(steps)}"
        for i, steps in enumerate(iteration_plans(state), start=1)
    )


def latest_draft(state: ResearchState) -> str | None:
    """The latest draft, or `None` while the writer has written none."""
    reports = state["reports"]
    return reports[-1] if reports else None


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
    `report_review_budget_exhausted`: a "continue" verdict on the last permitted iteration could not
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


class ResearchBudgetExhausted(BaseModel):
    """The iteration cap skipping a coverage review, handed to the runner to render as a stage.

    Both numbers travel because the stage states the cap beside the iteration: a reader who does not
    know the channel's configuration cannot tell an exhausted budget from an early stop otherwise.
    """

    research_iteration: int
    max_research_iterations: int


ResearchBudgetExhaustedEmitter = Callable[[ResearchBudgetExhausted], None]


def make_research_review_node(
    today_date: str,
    max_research_iterations: int,
    data_sources: str,
    emit_result_stage: ResearchReviewResultStageEmitter,
    emit_activity: ActivityEmitter,
    source_kinds: Collection[SourceKind],
    client_rules: Sequence[QualityRule],
    glossary: GlossaryTools | None,
) -> ResearchReviewNode:
    """Build the research-review node: judge coverage, emit its result stage, plan what remains.

    `max_research_iterations` is not a bound this node enforces — the router does that before the
    node is reached. It is here for the stage, which states the cap beside the iteration number.
    `glossary` is the channel's glossary configuration, which adds the generic rules that need one.
    """
    system_prompt = RESEARCH_REVIEW_SYSTEM_PROMPT.format(
        today_date=today_date,
        data_sources=data_sources,
        generic_rules=render_generic_rules(
            RuleStep.RESEARCH_REVIEW, source_kinds=source_kinds, glossary=glossary is not None
        ),
        client_rules=render_client_rules(client_rules, step=RuleStep.RESEARCH_REVIEW),
    )

    async def research_review(state: ResearchState) -> dict[str, Any]:
        emit_activity(RESEARCH_REVIEW_ACTIVITY)
        start = time.monotonic()
        # include_raw keeps the raw AIMessage alongside the parsed verdict so we can log the
        # call's token usage (including cached input tokens); with it, parse failures surface
        # as `parsing_error` instead of raising inside the chain, so we re-raise below to keep
        # the previous fail-loud behavior.
        llm = with_stream_drop_retry(
            get_chat_model(
                LLMModelConfig(reasoning_effort=ReasoningEffortEnum.MEDIUM)
            ).with_structured_output(ResearchReview, include_raw=True)
        )
        review_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=RESEARCH_REVIEW_HUMAN_MESSAGE.format(
                    query=state["research_query"],
                    findings=_render_findings(
                        _strip_status_calls(state["research_agent_messages"])
                    ),
                    plans=_render_plans(state),
                )
            ),
        ]
        llm_start = time.monotonic()
        result: dict[str, Any] = await llm.ainvoke(review_messages)
        llm_duration = time.monotonic() - llm_start

        if result["parsing_error"] is not None:
            raise result["parsing_error"]
        review: ResearchReview = result["parsed"]
        usage = result["raw"].usage_metadata

        # `research_iteration` is already the just-reviewed iteration's number: the
        # research-agent node counts each iteration it finishes, so this node only records the
        # review.
        update: dict[str, Any] = {"research_reviews": [*state["research_reviews"], review]}
        if review.next_steps:
            update["research_agent_messages"] = [
                HumanMessage(content=render_next_instruction(review.next_steps))
            ]

        # Verdict mirrors `route_after_research_review` over the post-update state, so neither the
        # skeleton event nor the stage disagrees with the actual routing.
        will_continue = _should_continue_research(
            plans_count=len(iteration_plans(state)) + (1 if review.next_steps else 0),
            research_iteration=state["research_iteration"],
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
            "Research iteration reviewed: research_iteration=%d duration=%.1fs messages=%d "
            "verdict=%s next_plan_steps=%d tokens=%s",
            state["research_iteration"],
            llm_duration,
            len(review_messages),
            "continue" if will_continue else "report",
            len(review.next_steps or []),
            format_token_usage(usage),
        )
        return update

    return research_review


def _numbered_instruction(violations: Sequence[str]) -> str | None:
    """The revision instruction for `violations`; `None` when there are none, which delivers the
    draft as it stands."""
    if not violations:
        return None
    return "\n".join(f"{i}. {violation}" for i, violation in enumerate(violations, start=1))


class ReportReviewOutcome(BaseModel):
    """One report review's result, handed to the runner so it can render a DIAL stage.

    Carries no DIAL types: the node decides what to report, the runner decides how it is
    rendered. `violations` is everything the next revision must fix — the review model's
    violations, with the app-measured length violation prepended when the draft exceeds the
    ceiling, and the grounded review's items after them. `blind_review_error` and
    `grounded_review_error` record a failed call of either review (each the exception kind); the
    length violation joins the list regardless, so a failed call still carries it. The violation
    text belongs in the stage only — never in a log record, per the logging-policy content
    allowlist.
    """

    draft_number: int
    word_count: int
    max_words: int
    violations: list[str]
    blind_review_error: str | None
    duration_seconds: float
    grounded_review_error: str | None = None
    # One tally per check, in the order the violations list them, so that the stage can say which
    # check found what.
    reviews: list[ReviewTally] | None = None

    @property
    def revision_instruction(self) -> str | None:
        """The instruction the next revision acts on; None delivers the draft as it stands.

        `violations` comes from `review_violations` over the round the node stores, and the
        router and the writer read that round through the same function, so the stage title
        cannot disagree with the route.
        """
        return _numbered_instruction(self.violations)


ReportReviewResultStageEmitter = Callable[[ReportReviewOutcome], None]


class ReportBudgetExhausted(BaseModel):
    """The version budget skipping a report review, handed to the runner to render as a stage.

    The counterpart of `ResearchBudgetExhausted` on the report side: both are reported by the
    router that decides the hand-off, and both carry the budget beside the number it bounds.
    """

    draft_number: int
    word_count: int
    max_words: int
    max_versions: int


ReportBudgetExhaustedEmitter = Callable[[ReportBudgetExhausted], None]


def report_review_budget_exhausted(*, draft_number: int, max_versions: int) -> bool:
    """True iff the current draft is the last permitted version, so no rewrite may follow it.

    Both numbers count report versions, 1-based, which keeps the comparison plain. The report
    loop's mirror of `research_budget_exhausted`: a verdict on the last permitted version could
    not be acted on, so the router skips report review when this holds.
    """
    return draft_number >= max_versions


class ReportRevisionFailure(BaseModel):
    """A revision the report call could not write, handed to the runner to render as a stage.

    Carries numbers and the exception kind, never draft text: the draft the loop settles on is the
    only one that reaches the response. The exception kind is known here and nowhere else — the
    graph state records only that a revision failed.
    """

    failed_draft_number: int
    delivered_draft_number: int
    error: str


ReportRevisionFailureEmitter = Callable[[ReportRevisionFailure], None]


def make_report_node(
    today_date: str,
    sections: Sequence[ReportSection],
    max_words: int,
    references_name: str,
    lookups: CitationLookups,
    data_sources: str,
    glossary: GlossaryTools | None,
    emit_revision_failed_stage: ReportRevisionFailureEmitter,
    emit_activity: ActivityEmitter,
    source_kinds: Collection[SourceKind],
    client_rules: Sequence[QualityRule],
) -> ReportNode:
    """Build the report node: it writes the first draft, and every revision after it.

    `glossary` is the channel's glossary configuration, which gives the writer the glossary
    citation form and the terminology rule on every turn, whether or not the fetch succeeded.
    """
    system_prompt = render_report_system_prompt(
        today_date=today_date,
        rules=render_writer_instructions(
            build_report_rules(
                sections=sections,
                max_words=max_words,
                references_name=references_name,
                lookups=lookups,
            )
        ),
        protected_sections=render_protected_section_names(sections),
        data_sources=data_sources,
        glossary=glossary is not None,
        client_rules=client_rules,
        source_kinds=source_kinds,
    )

    async def report(state: ResearchState) -> dict[str, Any]:
        emit_activity(REPORT_ACTIVITY)
        llm = with_stream_drop_retry(get_chat_model(LLMModelConfig()))
        previous_draft = latest_draft(state)
        report_messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            *_strip_status_calls(state["research_agent_messages"]),
            HumanMessage(
                content=REPORT_REQUEST.format(
                    query=state["research_query"], plans=_render_plans(state)
                )
            ),
        ]
        if previous_draft is not None:
            # Appended after the first draft's request, never inserted before the transcript,
            # so the byte prefix holds and the provider's prompt cache can serve it.
            report_messages.append(
                HumanMessage(
                    content=REPORT_REVISION_REQUEST.format(
                        word_count=count_report_words(previous_draft),
                        max_words=max_words,
                        length_exemptions=LENGTH_EXEMPTIONS,
                        instruction=revision_instruction(state) or "",
                        draft=previous_draft,
                    )
                )
            )
        draft_number = len(state["reports"]) + 1
        llm_start = time.monotonic()
        try:
            response = await llm.ainvoke(report_messages)
        except Exception as exc:
            llm_duration = time.monotonic() - llm_start
            # Once a draft exists, no later failure may discard it: deliver the previous draft
            # and leave the loop. The first draft has nothing to fall back to, so it propagates.
            if previous_draft is None:
                raise
            error = type(exc).__name__
            logger.warning(
                "Report revision failed, delivering the previous draft: "
                "failed_draft=%d delivered_draft=%d duration=%.1fs messages=%d error=%s "
                "tokens=%s",
                draft_number,
                draft_number - 1,
                llm_duration,
                len(report_messages),
                error,
                format_token_usage(None),
            )
            emit_revision_failed_stage(
                ReportRevisionFailure(
                    failed_draft_number=draft_number,
                    delivered_draft_number=draft_number - 1,
                    error=error,
                )
            )
            return {"report_revision_failed": True}

        llm_duration = time.monotonic() - llm_start
        text = extract_text_from_content(response.content)
        logger.info(
            "Report generated: draft=%d duration=%.1fs messages=%d length=%d words=%d tokens=%s",
            draft_number,
            llm_duration,
            len(report_messages),
            len(text),
            count_report_words(text),
            format_token_usage(response.usage_metadata),
        )
        # No `AIMessage` into `research_agent_messages`: drafts stay out of the transcript, so a
        # rejected one is never re-sent to a model. Every draft is kept in `reports`, which the
        # research record persists; the runner delivers the last one.
        return {"reports": [*state["reports"], text]}

    return report


def grounded_review_messages(
    *, transcript: Sequence[BaseMessage], instructions: str, request: str
) -> list[BaseMessage]:
    """The grounded review's messages: a neutral system message, the transcript, then the
    instructions and the review request as two more system messages.

    `transcript` is the research transcript as the report writer receives it. The instructions
    follow it so that the rules stand next to the draft they are applied to; they are fixed for the
    turn, so their position costs no cache. The request carries the draft, the only part that
    changes between rounds, so it comes last. Both are system messages because a trailing system
    message does not end a cacheable prompt and a trailing user message does: the cached prefix
    then ends with the transcript, which every review round of a turn shares. The call does not
    open with the research agent's system prompt to reuse that call's cache, chiefly because it
    runs at another reasoning effort; the faithful-relay spec lists the premises.
    """
    return [
        SystemMessage(content=GROUNDED_REVIEW_SYSTEM_MESSAGE),
        *transcript,
        SystemMessage(content=instructions),
        SystemMessage(content=request),
    ]


_NUMBERED_ITEM = re.compile(r"^(\d+)[.)]\s+")

# Markdown a model may wrap the bare answer in, and the punctuation that may end it.
_ANSWER_WRAPPING = "`*_\"' "
_ANSWER_ENDING = ".!;:"

# Deep enough for a line after "10. " to stay inside its Markdown list item.
_CONTINUATION_INDENT = "    "


class EmptyReviewAnswerError(Exception):
    """A plain-text review answered with no text, so it checked nothing."""


def parse_review_items(text: str) -> list[str]:
    """The violations of a plain-text review: one per numbered item, with the lines after an item
    joined to it.

    A line opens an item only when it starts, unindented, with the next number in sequence, so an
    indented sub-list or a line that starts with a year stays inside the item above it. Joined
    lines are indented, so that a sub-list stays nested when the items are numbered again. Only an
    answer that is "No violations", with any Markdown around it and any punctuation after it,
    gives none. A non-empty answer with no numbered line is one item, so a violation is never
    dropped for being written in prose. An empty answer raises `EmptyReviewAnswerError`: it is not
    an approval.
    """
    stripped = text.strip()
    if not stripped:
        raise EmptyReviewAnswerError("the review answered with no text")
    bare = stripped.strip(_ANSWER_WRAPPING).rstrip(_ANSWER_ENDING).strip(_ANSWER_WRAPPING)
    if bare.lower() == "no violations":
        return []
    items: list[str] = []
    for line in stripped.splitlines():
        match = _NUMBERED_ITEM.match(line)
        if match is not None and int(match.group(1)) == len(items) + 1:
            items.append(line[match.end() :].strip())
        elif items and line.strip():
            items[-1] += "\n" + _CONTINUATION_INDENT + line.strip()
    return items or [stripped]


def review_violations(review_round: ReportReviewRound) -> list[str]:
    """Everything the next revision must fix: the app's rule violations, then the blind review's,
    then the grounded review's items. A review whose response is absent contributes nothing, so a
    failed call is never read as an approval and never parsed into an error."""
    blind = review_round.blind_review.report_violations if review_round.blind_review else []
    # A blank answer counts as absent, as the review node stores one, so a record written
    # elsewhere never raises here.
    grounded_answer = review_round.grounded_review
    grounded = (
        parse_review_items(grounded_answer) if grounded_answer and grounded_answer.strip() else []
    )
    return [*review_round.rule_violations, *blind, *grounded]


def revision_instruction(state: ResearchState) -> str | None:
    """The instruction the next revision acts on, from the latest review round only; `None`
    delivers the latest draft as it stands."""
    if not state["report_reviews"]:
        return None
    return _numbered_instruction(review_violations(state["report_reviews"][-1]))


def _log_review_call(
    *,
    name: Literal["blind", "grounded"],
    draft_number: int,
    duration: float,
    messages: int,
    items: int,
    error: str | None,
    usage: UsageMetadata | None,
) -> None:
    """Log one review call's record. Its items are LLM response text, so only their count is
    logged."""
    logger.info(
        "Report %s-reviewed: draft=%d duration=%.1fs messages=%d items=%d error=%s tokens=%s",
        name,
        draft_number,
        duration,
        messages,
        items,
        error,
        format_token_usage(usage),
    )


def make_report_review_node(
    today_date: str,
    sections: Sequence[ReportSection],
    max_words: int,
    references_name: str,
    lookups: CitationLookups,
    data_sources: str,
    glossary: GlossaryTools | None,
    glossary_fetch_listed_terms: bool,
    emit_result_stage: ReportReviewResultStageEmitter,
    emit_activity: ActivityEmitter,
    source_kinds: Collection[SourceKind],
    client_rules: Sequence[QualityRule],
) -> ReportReviewNode:
    """Build the report-review node: judge the draft, emit its result stage, decide the next step.

    Two judgements meet here. The app's own rules (`report_rules`) are checked in Python over the
    draft text, and two model calls judge what needs a reader. The blind review judges padding,
    banned annotations, protected-section rules, citation format, and the blind parts of the
    quality rules (`client_rules` holds the channel's own). It sees the draft, the configuration
    and the query and plan, never the research findings, which is why it cannot reopen evidence
    coverage. The grounded review runs beside it and does see the findings: the transcript the
    writer received, then its instructions (the source-selection and faithful-relay rules' writer
    parts, and every other rule's grounded part, the client rules' included) and the review
    request, and its items follow the blind review's. A failing call never fails the turn: the
    rules still run, and their violations and the other call's still stand.

    The identifier rules need the cited ids looked up first, and the rules are synchronous, so
    the lookups the draft needs run concurrently with the two reviews, before the rules.

    On a glossary channel the reviewer also receives the research agent's successful glossary
    tool results, and the terminology check whenever the app's fetch listed a term
    (`glossary_fetch_listed_terms`) or there is such a result: otherwise it has no glossary to
    judge against.
    """
    rules = build_report_rules(
        sections=sections, max_words=max_words, references_name=references_name, lookups=lookups
    )
    grounded_review_instructions = render_grounded_review_prompt(
        today_date=today_date,
        data_sources=data_sources,
        source_kinds=source_kinds,
        glossary=glossary is not None,
        client_rules=client_rules,
    )

    async def report_review(state: ResearchState) -> dict[str, Any]:
        emit_activity(REPORT_REVIEW_ACTIVITY)
        start = time.monotonic()
        draft = latest_draft(state) or ""
        word_count = count_report_words(draft)
        draft_number = len(state["reports"])

        tool_results = glossary_tool_results(state["research_agent_messages"], glossary=glossary)
        system_prompt = render_blind_review_system_prompt(
            today_date=today_date,
            data_sources=data_sources,
            glossary=glossary is not None,
            glossary_check=glossary is not None
            and (glossary_fetch_listed_terms or bool(tool_results)),
            glossary_tool_results=tool_results,
            client_rules=client_rules,
            source_kinds=source_kinds,
        )
        review_request = REPORT_REVIEW_REQUEST.format(
            report_structure=render_report_structure(sections),
            protected_sections=render_protected_section_names(sections),
            query=state["research_query"],
            plan=render_plan(state["approved_plan"]),
            draft=draft,
        )
        blind_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=review_request),
        ]
        grounded_messages = grounded_review_messages(
            transcript=_strip_status_calls(state["research_agent_messages"]),
            instructions=grounded_review_instructions,
            request=review_request,
        )

        async def blind_review_call() -> tuple[ReportReview | None, str | None, float]:
            """The blind review's response (`None` when the call failed), its failure kind and
            its duration.

            It logs its own record.
            """
            llm_start = time.monotonic()
            usage: UsageMetadata | None = None
            review: ReportReview | None = None
            error: str | None = None
            try:
                llm = with_stream_drop_retry(
                    get_chat_model(
                        LLMModelConfig(reasoning_effort=ReasoningEffortEnum.MEDIUM)
                    ).with_structured_output(ReportReview, include_raw=True)
                )
                result: dict[str, Any] = await llm.ainvoke(blind_messages)
                usage = result["raw"].usage_metadata
                if result["parsing_error"] is not None:
                    raise result["parsing_error"]
                if result["parsed"] is None:
                    # An answer with no structured output checked nothing.
                    raise ValueError("the blind review returned no structured output")
                review = result["parsed"]
            except Exception as exc:
                # A failed blind review must not cost the report. The measured count still
                # applies, so the loop can still shorten an over-long draft on its own instruction.
                error = type(exc).__name__
                logger.warning(
                    "Blind review failed, falling back to the measured length: draft=%d error=%s",
                    draft_number,
                    error,
                )
            call_seconds = time.monotonic() - llm_start
            _log_review_call(
                name="blind",
                draft_number=draft_number,
                duration=call_seconds,
                messages=len(blind_messages),
                items=len(review.report_violations) if review is not None else 0,
                error=error,
                usage=usage,
            )
            return review, error, call_seconds

        async def grounded_review_call() -> tuple[str | None, list[str], str | None, float]:
            """The grounded review's answer text (`None` when the call failed or answered with no
            text), its items, its failure kind and its duration.

            It logs its own record.
            """
            llm_start = time.monotonic()
            usage: UsageMetadata | None = None
            answer: str | None = None
            items: list[str] = []
            error: str | None = None
            try:
                llm = with_stream_drop_retry(
                    get_chat_model(LLMModelConfig(reasoning_effort=ReasoningEffortEnum.MEDIUM))
                )
                response = await llm.ainvoke(grounded_messages)
                usage = response.usage_metadata
                text = extract_text_from_content(response.content)
                # Raises on an answer with no text, which therefore counts as a failed call.
                items = parse_review_items(text)
                answer = text
            except Exception as exc:
                # Like a failed blind review, a failed grounded review must not cost the report:
                # the other violations still stand.
                error = type(exc).__name__
                logger.warning("Grounded review failed: draft=%d error=%s", draft_number, error)
            call_seconds = time.monotonic() - llm_start
            _log_review_call(
                name="grounded",
                draft_number=draft_number,
                duration=call_seconds,
                messages=len(grounded_messages),
                items=len(items),
                error=error,
                usage=usage,
            )
            return answer, items, error, call_seconds

        (
            (blind_review, blind_error, blind_seconds),
            (grounded_answer, grounded_items, grounded_error, grounded_seconds),
            _,
        ) = await asyncio.gather(
            blind_review_call(), grounded_review_call(), lookups.prefetch(draft)
        )

        # The rules are the app's own, not the model's opinion: their violations join the list
        # whether the model reported any, reported none, or the call failed — so an approving
        # review cannot pass a draft that breaks one, and a failed review still shortens an
        # over-long draft and reports a mis-headed section.
        review_round = ReportReviewRound(
            draft_number=draft_number,
            rule_violations=[v for rule in rules for v in rule.violations(draft)],
            blind_review=blind_review,
            grounded_review=grounded_answer,
        )
        violations = review_violations(review_round)
        blind_count = len(blind_review.report_violations) if blind_review is not None else 0
        duration = time.monotonic() - start
        outcome = ReportReviewOutcome(
            draft_number=draft_number,
            word_count=word_count,
            max_words=max_words,
            violations=violations,
            blind_review_error=blind_error,
            duration_seconds=duration,
            grounded_review_error=grounded_error,
            reviews=[
                ReviewTally(name="code checks", violation_count=len(review_round.rule_violations)),
                ReviewTally(
                    name="blind review",
                    violation_count=blind_count,
                    duration_seconds=blind_seconds,
                ),
                ReviewTally(
                    name="grounded review",
                    violation_count=len(grounded_items),
                    duration_seconds=grounded_seconds,
                ),
            ],
        )
        emit_result_stage(outcome)
        logger.info(
            "Report reviewed: draft=%d duration=%.1fs outcome=%s words=%d ceiling=%d "
            "violations=%d",
            draft_number,
            duration,
            "revise" if outcome.revision_instruction else "deliver",
            word_count,
            max_words,
            len(violations),
        )
        return {"report_reviews": [*state["report_reviews"], review_round]}

    return report_review


def glossary_tool_messages(
    messages: Sequence[BaseMessage], *, glossary: GlossaryTools | None
) -> list[ToolMessage]:
    """The research agent's successful results of the two configured glossary tools, in order.

    Selected by tool name, so nothing about the answers' shape is assumed; a result marked as an
    error is left out.
    """
    if glossary is None:
        return []
    names = {glossary.list_terms_tool, glossary.definitions_tool}
    return [
        message
        for message in messages
        if isinstance(message, ToolMessage) and message.name in names and message.status != "error"
    ]


def glossary_tool_results(
    messages: Sequence[BaseMessage], *, glossary: GlossaryTools | None
) -> list[str]:
    """The text of `glossary_tool_messages`, as the server sent it, for the report reviewer."""
    return [
        text
        for message in glossary_tool_messages(messages, glossary=glossary)
        if (text := extract_text_from_content(message.content).strip())
    ]


def route_after_research_agent(
    max_research_iterations: int, emit_budget_exhausted: ResearchBudgetExhaustedEmitter
) -> Callable[[ResearchState], str]:
    """Decide the edge out of the research-agent node.

    An iteration is reviewed only while another iteration may still run: a "continue" verdict
    on the last permitted iteration could not be acted on, so the call is not made and the
    findings go straight to the report. Reported here — no node sits on that path, and announcing
    the skip from anywhere later would place it after the report's own stages.

    A cap of one exhausts nothing: with a single permitted iteration a review could never be acted
    on, so review is off by configuration and the user is told nothing. The log record still fires,
    the hand-off having happened either way.
    """

    def route(state: ResearchState) -> str:
        research_iteration = state["research_iteration"]
        if not research_budget_exhausted(
            research_iteration=research_iteration, max_research_iterations=max_research_iterations
        ):
            return "research-review"
        logger.info(
            "Research iteration budget exhausted: research_iteration=%d "
            "max_research_iterations=%d",
            research_iteration,
            max_research_iterations,
        )
        if max_research_iterations > 1:
            emit_budget_exhausted(
                ResearchBudgetExhausted(
                    research_iteration=research_iteration,
                    max_research_iterations=max_research_iterations,
                )
            )
        return "report"

    return route


def route_after_research_review() -> Callable[[ResearchState], str]:
    """Decide the edge out of the research-review node.

    Continue researching when research-review recorded a plan for a not-yet-run iteration (more
    iteration plans than finished iterations); otherwise report.
    """

    def route(state: ResearchState) -> str:
        if _should_continue_research(
            plans_count=len(iteration_plans(state)),
            research_iteration=state["research_iteration"],
        ):
            return "research-agent"
        return "report"

    return route


def route_after_report(
    max_versions: int,
    max_words: int,
    emit_budget_exhausted: ReportBudgetExhaustedEmitter,
) -> Callable[[ResearchState], str]:
    """Decide the edge out of the report node, and report the hand-off it decides on.

    Three exits. A revision whose own call failed leaves the loop immediately with the previous
    draft: returning to review would re-judge an unchanged draft and route straight back to a
    call that fails again, and since a failed revision writes nothing, no counter would bound
    that cycle — the report node has already announced that one. The last permitted version is
    delivered without a review — a verdict that cannot be acted on is not worth one — and this
    router announces it, the way its research counterpart announces the review the iteration cap
    skipped. Otherwise the draft is reviewed.

    A budget of one exhausts nothing: review is off by configuration, so the user is told nothing.
    The log record still fires, the delivery having gone unreviewed either way.
    """

    def route(state: ResearchState) -> str:
        if state.get("report_revision_failed"):
            return "end"
        draft_number = len(state["reports"])
        if not report_review_budget_exhausted(draft_number=draft_number, max_versions=max_versions):
            return "report-review"
        word_count = count_report_words(latest_draft(state) or "")
        logger.info(
            "Report delivered without review: draft=%d max_versions=%d words=%d",
            draft_number,
            max_versions,
            word_count,
        )
        if max_versions > 1:
            emit_budget_exhausted(
                ReportBudgetExhausted(
                    draft_number=draft_number,
                    word_count=word_count,
                    max_words=max_words,
                    max_versions=max_versions,
                )
            )
        return "end"

    return route


def route_after_report_review() -> Callable[[ResearchState], str]:
    """Decide the edge out of the report-review node.

    Revise iff the latest round left an instruction. Its rule violations already hold the
    measured count, so this reads the round rather than re-deciding.
    """

    def route(state: ResearchState) -> str:
        return "report" if revision_instruction(state) else "end"

    return route
