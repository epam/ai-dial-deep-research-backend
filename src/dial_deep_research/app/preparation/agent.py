"""Builds the per-request preparation agent."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from dial_deep_research.app.history import PrepState
from dial_deep_research.settings import settings
from dial_deep_research.utils.llm import LLMModelConfig, get_chat_model

from .prompts import PREP_AGENT_SYSTEM
from .tools import PrepTools


def build_prep_agent(state: PrepState, today_date: str) -> Any:
    """Build a preparation agent over the given per-turn `PrepState` holder.

    The agent drives clarify → plan → approve → launch via the `PrepTools`; it has
    no MCP tools, no checkpointer, and no middleware. `PrepState` is mutated only
    by the tools (which close over `state`), never by the model.
    """
    tools = PrepTools(state=state, today_date=today_date).build()
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=PREP_AGENT_SYSTEM.format(
            agent_name=settings.channel.prompts.agent_name,
            today_date=today_date,
            data_sources_descriptions=settings.channel.prompts.data_sources_descriptions,
        ),
    )
