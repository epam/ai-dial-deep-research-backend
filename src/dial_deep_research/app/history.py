"""DIAL ↔ LangChain message-history serialisation.

`reconstruct_history` reads from the incoming `Request` and produces the
`list[BaseMessage]` the agent should see (rehydrating URL-form image blocks
back to base64 on the way). `create_dial_state` does the inverse:
walks the buffered slice from the current turn, uploads inline image content
to DIAL files, and returns the dict that goes into `choice.set_state`.

Both functions are pure-ish — they touch a `dial` client but no other agent
state — so they live outside `AgentRunner` and can be unit-tested directly.
"""

from __future__ import annotations

import logging
import typing as t

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Request, Role
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)
from pydantic import BaseModel, Field, ValidationError

from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.image_attachments import (
    rehydrate_image_blocks,
    upload_image_blocks,
)

logger = logging.getLogger(__name__)


class Clarification(BaseModel):
    """Result of the clarity check on the working query."""

    questions: list[str] = Field(default_factory=list)
    """Outstanding clarifying questions; empty means the query is clear enough."""


class Plan(BaseModel):
    """The agent-authored research plan. Authored only by `update_plan`.

    Steps are plain strings kept in order; numbering is a rendering concern (the
    tools present them as a numbered list), so there is no per-step number field to
    store — which also keeps the persisted list free of the SDK's reserved `index`
    key (see CLAUDE.md).
    """

    steps: list[str] = Field(default_factory=list)


class PrepState(BaseModel):
    """Working state of the preparation flow.

    Mutated only by the preparation tools. `plan_approved` is set only by
    `approve_plan`; `research_started` only by `start_research`.
    """

    current_query: str | None = None
    clarification: Clarification | None = None  # None until the clarity check runs
    plan: Plan | None = None
    plan_approved: bool = False
    research_started: bool = False


class DialState(BaseModel):
    """The shape we stash under `assistant.custom_content.state` per turn."""

    messages: list[BaseMessage]
    preparation: PrepState

    @classmethod
    def from_dict(cls, data: dict) -> t.Self:
        messages = data.get('messages', [])
        preparation = data.get('preparation', PrepState())
        return cls(messages=messages_from_dict(messages), preparation=preparation)

    def to_dict(self) -> dict:
        return {
            'messages': messages_to_dict(self.messages),
            'preparation': self.preparation.model_dump(mode="json"),
        }


async def reconstruct_history(request: Request, dial: AsyncDial) -> list[BaseMessage]:
    """Walk `request.messages` and rebuild the LangChain history fed to the agent.

    For each message:
    - USER -> `HumanMessage`;
    - ASSISTANT with a usable `custom_content.state["messages"]` -> the full
      decoded slice, with URL-form image blocks rehydrated back to base64 so
      the `multimodal-tool-output` in-flight contract holds;
    - ASSISTANT without state -> a single `AIMessage(content=…)` fallback
      (legacy turns produced before the persistence change).

    The system role is intentionally skipped — `create_agent` receives the
    app's system prompt via `system_prompt=` directly.
    """
    history: list[BaseMessage] = []
    for message in request.messages:
        role = message.role
        if role == Role.USER:
            history.append(HumanMessage(content=extract_text_from_content(message.content)))
        elif role == Role.ASSISTANT:
            state = _parse_dial_state(message)
            if state and state.messages:
                # state is available. reconstruct AI, Tool messages sequence from state.
                # TODO: batch rehydration across all assistant turns into one
                # `asyncio.gather` so tail latency is bounded by the slowest
                # single download, not the slowest per-message group.
                await rehydrate_image_blocks(state.messages, dial)
                history.extend(state.messages)
            else:
                # state not available. fallback to using DIAL Chat content as is (single AI message)
                history.append(AIMessage(content=extract_text_from_content(message.content)))
    return history


async def create_dial_state(
    messages: list[BaseMessage], preparation: PrepState, dial: AsyncDial
) -> dict:
    """Persist-side dual of `reconstruct_history`.

    Uploads inline image content blocks to DIAL files (rewriting them in place
    to carry `url` instead of `base64`) and returns the dict that `choice.set_state`
    should receive. Mutates `messages` in place — callers that need the
    pre-upload slice for any reason should copy first.
    """
    await upload_image_blocks(messages=messages, dial=dial)
    return DialState(messages=messages, preparation=preparation).to_dict()


def _parse_dial_state(message: Message) -> DialState | None:
    if not (cc := message.custom_content):
        logger.warning("No custom content found in message")
        return None
    if not isinstance(state := cc.state, dict):
        logger.warning(f"Custom content is not a dictionary. Got: {type(state)}")
        return None
    try:
        return DialState.from_dict(state)
    except ValidationError:
        logger.exception('Failed to validate DIAL state')
        return None


def load_last_prep_state(request: Request) -> PrepState:
    """Load `PrepState` from the latest assistant message that carries one.

    Returns a fresh `PrepState` when no prior assistant message has one (the first
    turn, or the first user message was edited away). After a rewind, the latest
    surviving assistant message carries the correct state, so this needs no
    special rewind handling. Fails soft to a fresh state on malformed data.
    """
    for message in reversed(request.messages):
        if message.role != Role.ASSISTANT:
            continue
        state = _parse_dial_state(message)
        if state is None:
            continue
        return state.preparation
    return PrepState()
