"""Builds the per-request preparation agent."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.history import CrossTurnPrepState
from dial_deep_research.app_properties import Prompts
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    get_chat_model,
    stream_drop_retry_middleware,
)

from .middleware import StopAfterResearchStartMiddleware
from .prompts import render_prep_agent_system
from .tools import PrepReviews, PrepTools


def build_prep_agent(
    state: CrossTurnPrepState,
    today_date: str,
    prompts: Prompts,
    data_sources: DataSources,
    reviews: PrepReviews | None = None,
) -> Any:
    """Build a preparation agent over the turn's `CrossTurnPrepState` holder.

    The agent drives clarify → plan → approve → launch via the `PrepTools`; it has no MCP tools and
    no checkpointer; its middleware is the logging pair, the transient stream-drop retry, and the
    hook that ends the run once research has started. `CrossTurnPrepState` is mutated only by the
    tools (which close over `state`), never by the model. `prompts` is the instance's per-request
    prompt content, and `data_sources` the turn's data-sources fetch, whose string the agent and the
    query clarity check receive as the description of the channel's data sources.
    `reviews`, when given, collects the whole response of each check for the turn's state.
    """
    tools = PrepTools(
        state=state,
        today_date=today_date,
        data_sources=data_sources.text,
        reviews=reviews,
    ).build()
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=render_prep_agent_system(
            agent_name=prompts.agent_name, today_date=today_date, data_sources=data_sources
        ),
        middleware=[
            *agent_logging_middleware("preparation"),
            stream_drop_retry_middleware(),
            StopAfterResearchStartMiddleware(state),
        ],
    )
