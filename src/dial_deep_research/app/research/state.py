"""Graph-channel state for the research execution graph.

This is the one place we use a LangGraph state object (a `TypedDict` with the
`add_messages` reducer) rather than the closure-held Pydantic state the preparation
flow uses: the `research_agent_messages` channel needs the annotated reducer so the
research-agent node and the research-review node can both append to it. The other
channels hold plain typed values, each written whole by the node that changes it.

The channels hold model outputs and the counts derived from them, never a value a node can
derive itself: the plan list, the draft number and the revision instruction are built by the
node that reads them, so a run resumed from a research record derives them as a fresh run does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from dial_deep_research.app.history import CrossTurnPrepState

from .prompts import ReportReview, ResearchReview, render_first_instruction

if TYPE_CHECKING:
    from .snapshot import ResumableSnapshot


class ReportReviewRound(BaseModel):
    """One report-review round, whole: what the app's own rules found and both reviews' responses.

    The research record stores each round, so a field added later needs a default: an older
    record without it would otherwise fail validation and be discarded.
    """

    draft_number: int
    """The draft the round reviewed, 1-based."""

    rule_violations: list[str]
    """What the app's own report rules found, as they measured it."""

    blind_review: ReportReview | None
    """The blind review's response; `None` when its call failed."""

    grounded_review: str | None
    """The grounded review's answer text; `None` when its call failed or answered with no text."""


class ResearchState(TypedDict):
    """State threaded through the research graph for one turn."""

    research_query: str
    """The aligned research query from preparation (`CrossTurnPrepState.current_query`)."""

    approved_plan: list[str]
    """The plan the user approved."""

    research_agent_messages: Annotated[list[BaseMessage], add_messages]
    """Research-agent's conversation: the first instruction, its model replies and tool results,
    and the instruction research-review injects for each further iteration."""

    research_iteration: int
    """Research-agent iterations completed. The research-agent node counts each one when it
    finishes, so the last permitted iteration — which goes to the report unreviewed — is counted
    too."""

    research_reviews: list[ResearchReview]
    """Each research-review response, whole, in order."""

    reports: list[str]
    """Each draft the writer wrote, in order. The last one is the latest draft."""

    report_reviews: list[ReportReviewRound]
    """One entry per report-review round, in order."""

    report_revision_failed: bool
    """Set when a revision's own model call failed, so the loop exits with the previous draft."""


def build_initial_state(prep_state: CrossTurnPrepState) -> ResearchState:
    """Seed the graph state from an approved `CrossTurnPrepState`.

    The query and the approved plan come straight from preparation; the
    plan is rendered as a `HumanMessage` so research-agent sees it as its
    instruction for the first iteration.
    """
    if prep_state.current_query is None or prep_state.plan is None:
        raise ValueError("Cannot start research without an approved query and plan")
    approved_plan = prep_state.plan.steps
    # Every channel is seeded explicitly: an unwritten channel is absent from the state a node
    # reads rather than defaulted, so a node reading it would raise instead of seeing a default.
    return ResearchState(
        research_query=prep_state.current_query,
        approved_plan=approved_plan,
        research_agent_messages=[
            HumanMessage(content=render_first_instruction(prep_state.current_query, approved_plan))
        ],
        research_iteration=0,
        research_reviews=[],
        reports=[],
        report_reviews=[],
        report_revision_failed=False,
    )


def build_resumed_state(resumed: ResumableSnapshot) -> ResearchState:
    """Seed the graph state from the snapshot a failed run saved, every channel as it was."""
    snapshot = resumed.snapshot
    return ResearchState(
        research_query=snapshot.research_query,
        approved_plan=snapshot.approved_plan,
        research_agent_messages=resumed.messages,
        research_iteration=snapshot.research_iteration,
        research_reviews=snapshot.research_reviews,
        reports=snapshot.reports,
        report_reviews=snapshot.report_reviews,
        report_revision_failed=snapshot.report_revision_failed,
    )
