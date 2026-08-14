"""Assembles the deterministic research graph.

`START → research-agent → (research-review | report) → (research-agent | report) →
(report-review | END) → (report | END)`. No checkpointer, no `interrupt()` — research runs
autonomously within one turn. Every loop/termination decision is pure Python over the graph
state: the research loop's are `route_after_research_agent` and `route_after_research_review`,
the report loop's are `route_after_report` and `route_after_report_review`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from dial_deep_research.app_properties import ReportSection

from .nodes import (
    ActivityEmitter,
    ReportReviewResultStageEmitter,
    ResearchReviewResultStageEmitter,
    build_research_agent,
    make_report_node,
    make_report_review_node,
    make_research_review_node,
    route_after_report,
    route_after_report_review,
    route_after_research_agent,
    route_after_research_review,
)
from .state import ResearchState


def build_research_graph(
    tools: list[BaseTool],
    today_date: str,
    max_research_iterations: int,
    client_name: str,
    report_structure: Sequence[ReportSection],
    max_report_words: int,
    max_report_versions: int,
    emit_research_review_result_stage: ResearchReviewResultStageEmitter,
    emit_report_review_result_stage: ReportReviewResultStageEmitter,
    emit_activity: ActivityEmitter,
) -> Any:
    """Compile the research graph over the loaded tools and this turn's configuration.

    Every callback is the runner's own, on the same split: the node decides what to report, the
    runner holds the DIAL `Choice` and decides how it renders. The two result-stage emitters each
    carry the outcome of one review. `emit_activity` names the work a node is starting, and each
    node calls it first thing — the graph has no node-entry signal a stream consumer could read,
    since an `updates` part arrives only once a node has finished.
    """
    research_agent = build_research_agent(
        tools=tools,
        today_date=today_date,
        client_name=client_name,
    )

    builder = StateGraph(ResearchState)
    builder.add_node(node="research-agent", action=research_agent)
    # mypy can't infer the node's TypedDict state param from an async callable; the
    # plain-function node form is the documented one and works at runtime.
    builder.add_node(
        node="research-review",
        action=make_research_review_node(  # type: ignore[call-overload]
            today_date=today_date,
            max_research_iterations=max_research_iterations,
            emit_result_stage=emit_research_review_result_stage,
            emit_activity=emit_activity,
        ),
    )
    builder.add_node(
        node="report",
        action=make_report_node(  # type: ignore[call-overload]
            today_date=today_date,
            sections=report_structure,
            max_words=max_report_words,
            emit_activity=emit_activity,
        ),
    )
    builder.add_node(
        node="report-review",
        action=make_report_review_node(  # type: ignore[call-overload]
            today_date=today_date,
            sections=report_structure,
            max_words=max_report_words,
            emit_result_stage=emit_report_review_result_stage,
            emit_activity=emit_activity,
        ),
    )

    builder.add_edge(start_key=START, end_key="research-agent")
    builder.add_conditional_edges(
        source="research-agent",
        path=route_after_research_agent(max_research_iterations=max_research_iterations),
        path_map={"research-review": "research-review", "report": "report"},
    )
    builder.add_conditional_edges(
        source="research-review",
        path=route_after_research_review(),
        path_map={"research-agent": "research-agent", "report": "report"},
    )
    builder.add_conditional_edges(
        source="report",
        path=route_after_report(max_versions=max_report_versions),
        path_map={"report-review": "report-review", "end": END},
    )
    builder.add_conditional_edges(
        source="report-review",
        path=route_after_report_review(),
        path_map={"report": "report", "end": END},
    )

    return builder.compile()
