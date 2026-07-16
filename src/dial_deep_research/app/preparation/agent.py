"""Builds the per-request preparation agent."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from dial_deep_research.app.history import PrepState
from dial_deep_research.app_properties import Prompts
from dial_deep_research.utils.agent_logging import agent_logging_middleware
from dial_deep_research.utils.llm import (
    LLMModelConfig,
    get_chat_model,
    stream_drop_retry_middleware,
)

from .prompts import PREP_AGENT_SYSTEM
from .tools import PrepTools


def build_prep_agent(state: PrepState, today_date: str, prompts: Prompts) -> Any:
    """Build a preparation agent over the given per-turn `PrepState` holder.

    The agent drives clarify → plan → approve → launch via the `PrepTools`; it has
    no MCP tools and no checkpointer; its middleware is the logging pair plus the
    transient stream-drop retry. `PrepState` is mutated only by the tools (which
    close over `state`), never by the model. `prompts` is the instance's per-request
    prompt content.
    """
    tools = PrepTools(state=state, today_date=today_date).build()
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=PREP_AGENT_SYSTEM.format(
            agent_name=prompts.agent_name,
            today_date=today_date,
            data_sources_descriptions=prompts.data_sources_descriptions,
        ),
        middleware=[*agent_logging_middleware("preparation"), stream_drop_retry_middleware()],
    )
