"""Channel configuration: per-deployment content loaded from a YAML file.

The code ships channel-agnostic; everything specific to one deployment ("channel") —
the deployment name, the client wording in prompts, the topics map — lives in a YAML
file selected by CHANNEL_CONFIG_PATH. See `data/configs/example.yaml` for the schema.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ChannelPrompts(BaseModel):
    """Channel-specific content injected into the prompt templates."""

    client_name: str = Field(
        min_length=1,
        description="Name of the client using the Deep Research",
    )
    agent_name: str = Field(
        min_length=1,
        description="Name the agent uses to introduce itself in prompts",
    )
    data_sources_descriptions: str = Field(
        min_length=1,
        description="A topics map of the data sources available in the knowledge base",
    )


class ChannelConfig(BaseModel):
    channel_name: str = Field(
        min_length=1,
        description="DIAL deployment id the chat completion is registered under",
    )
    opik_project_name: str | None = Field(
        default=None,
        description="Opik project traces are reported to (when OPIK_TRACING_ENABLED=true)",
    )
    max_research_iterations: int = Field(
        default=10,
        ge=1,
        description="Max number of research iterations (researcher → reviewer loops) before"
        " the report is forced",
    )
    prompts: ChannelPrompts

    @classmethod
    def from_yaml(cls, path: Path | str) -> ChannelConfig:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))
