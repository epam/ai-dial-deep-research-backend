"""Builds the per-request playground agent."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from dial_deep_research.app_properties import Prompts
from dial_deep_research.utils.llm import LLMModelConfig, get_chat_model

from .prompts import PLAYGROUND_SYSTEM


def build_playground_agent(tools: list[BaseTool], prompts: Prompts, today_date: str) -> Any:
    """Build a single tool-calling agent over the MCP tools, with a minimal system prompt.

    No forced tool choice and no middleware: the agent decides whether to call a tool or
    answer directly.
    """
    return create_agent(
        model=get_chat_model(LLMModelConfig()),
        tools=tools,
        system_prompt=PLAYGROUND_SYSTEM.format(
            agent_name=prompts.agent_name,
            today_date=today_date,
            data_sources_descriptions=prompts.data_sources_descriptions,
        ),
    )
