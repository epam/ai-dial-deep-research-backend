"""Graph-channel state for the research execution graph.

This is the one place we use a LangGraph state object (a `TypedDict` with the
`add_messages` reducer) rather than the closure-held Pydantic state the preparation
flow uses: the `messages` channel needs the annotated reducer so the research-agent
subgraph and the research-review node can both append to it. The plan/review payloads
themselves stay plain typed values.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages

from dial_deep_research.app.history import PrepState

from .prompts import render_first_instruction


class ResearchState(TypedDict):
    """State threaded through the research graph for one turn."""

    messages: Annotated[list[BaseMessage], add_messages]
    """Research-agent AIMessages/ToolMessages plus the research-review-injected plan HumanMessages."""

    original_query: str
    """The aligned research query from preparation (`PrepState.current_query`)."""

    plans: list[list[str]]
    """Iteration plans in order: [approved prep plan, research-review plan 1, …]; current = plans[-1]."""

    research_iteration: int
    """Research-agent iterations completed. The research-agent node counts itself
    (`IterationCounterMiddleware`), so the last permitted iteration — which goes to the
    report unreviewed — is counted too."""

    report: str | None
    """The latest report draft, set by the report node; the delivered report once the loop ends."""

    report_revision_instruction: str | None
    """What a revision must change, set by report-review. `None` means the draft is deliverable."""

    report_version: int
    """1-based version index of `report` — 1 for the first draft, 0 while no draft exists.
    Bounds the report loop against `max_report_versions`."""

    report_revision_failed: bool
    """Set when a revision's own model call failed, so the loop exits with the previous draft."""


def build_initial_state(prep_state: PrepState) -> ResearchState:
    """Seed the graph state from an approved `PrepState`.

    The original query and the approved plan come straight from preparation; the
    first plan is rendered as a `HumanMessage` so research-agent sees it as its
    instruction for the first iteration.
    """
    if prep_state.current_query is None or prep_state.plan is None:
        raise ValueError("Cannot start research without an approved query and plan")
    first_plan = prep_state.plan.steps
    # Every channel is seeded explicitly: an unwritten channel is absent from the state a node
    # reads rather than defaulted, so a node reading it would raise instead of seeing a default.
    return ResearchState(
        messages=[
            HumanMessage(content=render_first_instruction(prep_state.current_query, first_plan))
        ],
        original_query=prep_state.current_query,
        plans=[first_plan],
        research_iteration=0,
        report=None,
        report_revision_instruction=None,
        report_version=0,
        report_revision_failed=False,
    )
