"""Graph-channel state for the research execution graph.

This is the one place we use a LangGraph state object (a `TypedDict` with the
`add_messages` reducer) rather than the closure-held Pydantic state the preparation
flow uses: the `messages` channel needs the annotated reducer so the researcher
subgraph and the reviewer node can both append to it. The plan/review payloads
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
    """Researcher AIMessages/ToolMessages plus the reviewer-injected plan HumanMessages."""

    original_query: str
    """The aligned research query from preparation (`PrepState.current_query`)."""

    plans: list[list[str]]
    """Iteration plans in order: [approved prep plan, reviewer plan 1, …]; current = plans[-1]."""

    iteration: int
    """Number of researcher iterations completed (guards the iteration cap)."""

    report: str | None
    """The final report text, set by the report node."""


def build_initial_state(prep_state: PrepState) -> ResearchState:
    """Seed the graph state from an approved `PrepState`.

    The original query and the approved plan come straight from preparation; the
    first plan is rendered as a `HumanMessage` so the researcher sees it as its
    instruction for the first iteration.
    """
    if prep_state.current_query is None or prep_state.plan is None:
        raise ValueError("Cannot start research without an approved query and plan")
    first_plan = prep_state.plan.steps
    return ResearchState(
        messages=[
            HumanMessage(content=render_first_instruction(prep_state.current_query, first_plan))
        ],
        original_query=prep_state.current_query,
        plans=[first_plan],
        iteration=0,
        report=None,
    )
