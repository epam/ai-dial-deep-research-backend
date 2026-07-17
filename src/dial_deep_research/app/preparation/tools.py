"""The preparation control tools.

Each tool mutates a shared per-turn `PrepState` holder as a side effect and
returns a plain string to the agent. The agent can only call the tools — it has
no path to write `PrepState` directly, so the readiness gates cannot be bypassed
by the model. Gate violations raise `ToolException` (the tools are marked
`handle_tool_error=True`), which reaches the agent as an error `ToolMessage`.
"""

from __future__ import annotations

from langchain.tools import ToolRuntime
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool, ToolException, tool

from dial_deep_research.app.history import Clarification, Plan, PrepState
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.llm import LLMModelConfig, get_chat_model, with_stream_drop_retry

from . import prompts
from .prompts import PlanReviewResponse, QueryReviewResponse


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {text}" for i, text in enumerate(items, start=1))


def _format_conversation(messages: list[BaseMessage]) -> str:
    """Render the user/assistant turns for the clarity and approval checks.

    Only natural-language user and assistant text is kept (the questions/plan the
    user saw and their replies); tool calls, tool results, and system messages are
    dropped as noise.
    """
    lines: list[str] = []
    for message in messages:
        if message.type not in ("human", "ai"):
            continue
        text = extract_text_from_content(message.content)
        if not text.strip():
            continue
        role = "User" if message.type == "human" else "Assistant"
        lines.append(f"{role}: {text}")
    return "\n\n".join(lines)


def _query_failure_reason(state: PrepState) -> str:
    if state.current_query is None:
        return prompts.QUERY_GATE_NO_QUERY
    if state.clarification is None:
        return prompts.QUERY_GATE_NOT_REVIEWED
    if state.clarification.questions:
        return prompts.QUERY_GATE_NOT_CLEAR
    return ""


class PrepTools:
    """Builds the four control tools over a shared per-turn `PrepState`.

    `state` is the live holder the tools mutate; the runner reads it back after the
    agent run to persist it.
    """

    def __init__(self, state: PrepState, today_date: str, data_sources_descriptions: str) -> None:
        self.state = state
        self._today = today_date
        self._data_sources_descriptions = data_sources_descriptions

    def build(self) -> list[BaseTool]:
        tools = [
            self._update_query(),
            self._update_plan(),
            self._approve_plan(),
            self._start_research(),
        ]
        for prep_tool in tools:
            # Make gate ToolExceptions reach the agent as error ToolMessages it can
            # react to, instead of bubbling out and failing the turn.
            prep_tool.handle_tool_error = True
        return tools

    def _update_query(self) -> BaseTool:
        @tool
        async def update_query(query: str, runtime: ToolRuntime) -> str:
            """Set or replace the working research query, then check it for clarity.

            Call this first with a faithful restatement of the user's request, and
            again with a refined query after the user answers clarifying questions.
            Returns clarifying questions to ask, or confirms the query is clear.
            Replacing the query discards any existing plan and approval.
            """
            conversation = _format_conversation(runtime.state["messages"])
            llm = with_stream_drop_retry(
                get_chat_model(LLMModelConfig()).with_structured_output(QueryReviewResponse)
            )
            check: QueryReviewResponse = await llm.ainvoke(
                [
                    (
                        "system",
                        prompts.QUERY_REVIEW_SYSTEM.format(
                            today_date=self._today,
                            data_sources_descriptions=self._data_sources_descriptions,
                        ),
                    ),
                    (
                        "human",
                        f"Conversation so far:\n{conversation or '(none yet)'}\n\n"
                        f"Current restatement of the request:\n{query}",
                    ),
                ]
            )  # type: ignore
            self.state.current_query = query
            self.state.clarification = Clarification(questions=check.questions)
            self.state.plan = None
            self.state.plan_approved = False
            if check.questions:
                return prompts.QUERY_CLARIFICATION_NEEDED.format(
                    questions=_numbered(check.questions)
                )
            return prompts.QUERY_CLEAR

        return update_query

    def _update_plan(self) -> BaseTool:
        @tool
        async def update_plan(steps: list[str]) -> str:
            """Record your research plan for the user to review.

            Provide the steps as an ordered list of plain strings (the tool numbers
            them). Call this with the exact steps you present to the user, and again
            every time you revise the plan, so the recorded plan matches what they
            see. Requires the query's clarifications to be resolved first.
            """
            if reason := _query_failure_reason(self.state):
                raise ToolException(prompts.UPDATE_PLAN_BLOCKED.format(reason=reason))
            self.state.plan = Plan(steps=steps)
            self.state.plan_approved = False
            return prompts.PLAN_RECORDED.format(
                query=self.state.current_query, plan=_numbered(self.state.plan.steps)
            )

        return update_plan

    def _approve_plan(self) -> BaseTool:
        @tool
        async def approve_plan(runtime: ToolRuntime) -> str:
            """Check whether the user has approved the current plan.

            Call this after the user responds to the plan. An independent reviewer
            reads the conversation and decides — you cannot approve it yourself. If
            it reports the recorded plan is stale, call update_plan with the latest
            steps you discussed, then call this again.
            """
            if reason := _query_failure_reason(self.state):
                raise ToolException(prompts.APPROVE_PLAN_BLOCKED.format(reason=reason))
            if self.state.plan is None:
                raise ToolException(prompts.APPROVE_NO_PLAN)
            conversation = _format_conversation(runtime.state["messages"])
            llm = with_stream_drop_retry(
                get_chat_model(LLMModelConfig()).with_structured_output(PlanReviewResponse)
            )
            check: PlanReviewResponse = await llm.ainvoke(
                [
                    ("system", prompts.PLAN_REVIEW_SYSTEM.format(today_date=self._today)),
                    (
                        "human",
                        f"Recorded plan:\n{_numbered(self.state.plan.steps)}\n\n"
                        f"Conversation:\n{conversation}",
                    ),
                ]
            )  # type: ignore
            if check.approved:
                self.state.plan_approved = True
                return prompts.PLAN_APPROVED
            return prompts.PLAN_NOT_APPROVED.format(
                failure_reason=check.failure_reason or "Ask the user to confirm the plan."
            )

        return approve_plan

    def _start_research(self) -> BaseTool:
        @tool
        async def start_research() -> str:
            """Start the research run. Only call this once the plan is approved."""
            state = self.state
            if reason := _query_failure_reason(state):
                raise ToolException(prompts.START_RESEARCH_BLOCKED.format(reason=reason))
            if state.plan is None:
                raise ToolException(prompts.START_NO_PLAN)
            if not state.plan_approved:
                raise ToolException(prompts.START_NOT_APPROVED)
            state.research_started = True
            return prompts.RESEARCH_READY.format(
                query=state.current_query, plan=_numbered(state.plan.steps)
            )

        return start_research
