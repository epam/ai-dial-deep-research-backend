"""Builds the per-request preparation agent."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from dial_deep_research.app.data_sources import DataSources
from dial_deep_research.app.history import PrepState
from dial_deep_research.app_properties import Prompts
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    get_chat_model,
    stream_drop_retry_middleware,
)

from .middleware import StopAfterResearchStartMiddleware
from .prompts import DATASET_LIST_FAILED_INSTRUCTION, PREP_AGENT_SYSTEM
from .tools import PrepTools


def render_prep_agent_system(*, agent_name: str, today_date: str, data_sources: DataSources) -> str:
    """The preparation agent's system prompt, carrying the turn's data-sources string, and the
    instruction to plan around a failed list of datasets on a turn whose list failed."""
    return PREP_AGENT_SYSTEM.format(
        agent_name=agent_name,
        today_date=today_date,
        data_sources_descriptions=data_sources.text,
        dataset_list_failed_instruction=(
            DATASET_LIST_FAILED_INSTRUCTION if data_sources.dataset_list_failed else ""
        ),
    )


def build_prep_agent(
    state: PrepState, today_date: str, prompts: Prompts, data_sources: DataSources
) -> Any:
    """Build a preparation agent over the given per-turn `PrepState` holder.

    The agent drives clarify → plan → approve → launch via the `PrepTools`; it has
    no MCP tools and no checkpointer; its middleware is the logging pair, the transient
    stream-drop retry, and the hook that ends the run once research has started. `PrepState` is mutated only by the tools (which
    close over `state`), never by the model. `prompts` is the instance's per-request
    prompt content, and `data_sources` the turn's data-sources fetch, whose string the agent and
    the query clarity check receive in place of `prompts.data_sources_descriptions`.
    """
    tools = PrepTools(
        state=state,
        today_date=today_date,
        data_sources_descriptions=data_sources.text,
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
