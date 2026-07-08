"""Assembles the deterministic research graph.

`START → researcher → reviewer → (researcher | report) → END`. No checkpointer, no
`interrupt()` — research runs autonomously within one turn. The only loop/termination
decision is `route_after_review`, pure Python over the state.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from .nodes import (
    build_researcher_agent,
    make_report_node,
    make_reviewer_node,
    route_after_review,
)
from .state import ResearchState


def build_research_graph(tools: list[BaseTool], today_date: str, max_iterations: int) -> Any:
    """Compile the research graph over the loaded tools and config."""
    researcher = build_researcher_agent(tools, today_date)

    builder = StateGraph(ResearchState)
    builder.add_node("researcher", researcher)
    # mypy can't infer the node's TypedDict state param from an async callable; the
    # plain-function node form is the documented one and works at runtime.
    builder.add_node("reviewer", make_reviewer_node(today_date))  # type: ignore[call-overload]
    builder.add_node("report", make_report_node(today_date))  # type: ignore[call-overload]

    builder.add_edge(START, "researcher")
    builder.add_edge("researcher", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        route_after_review(max_iterations),
        {"researcher": "researcher", "report": "report"},
    )
    builder.add_edge("report", END)

    return builder.compile()
