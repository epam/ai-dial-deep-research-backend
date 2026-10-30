"""DIAL ↔ LangChain message-history serialisation.

`reconstruct_prep_agent_history` reads the incoming `Request` and produces the
`list[BaseMessage]` the preparation agent should see. `PreparationDialState` is the `preparation`
part of the state a turn stores under `custom_content.state`; `create_dial_state` adds the
research record and the failure flag beside it, as top-level keys of their own.

Both are pure: they touch no client and no other agent state, so they live outside
`PrepAgentRunner` and can be unit-tested directly.
"""

from __future__ import annotations

import logging
import typing as t

from aidial_sdk.chat_completion import Message, Request, Role
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    messages_from_dict,
    messages_to_dict,
)
from pydantic import BaseModel, Field, ValidationError

from dial_deep_research.app.preparation.prompts import (
    FAILED_TURN_NOTE,
    PlanReviewResponse,
    QueryReviewResponse,
)
from dial_deep_research.utils.content import extract_text_from_content
from dial_deep_research.utils.pydantic_errors import validation_error_summary

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


class CrossTurnPrepState(BaseModel):
    """Working state of the preparation flow, carried from turn to turn: every turn loads it from
    the latest answer and saves it again. Data that belongs to one turn lives beside it, in
    `PreparationDialState`.

    Mutated only by the preparation tools. `plan_approved` is set only by
    `approve_plan`; `research_started` only by `start_research`. `plan_id` names the
    recorded query and plan, so a snapshot of failed research is resumed only for them:
    `update_plan` sets a fresh one on every call, `update_query` clears it with the plan,
    and `start_research` gives one to a plan an earlier release recorded without it.
    """

    current_query: str | None = None
    clarification: Clarification | None = None  # None until the clarity check runs
    plan: Plan | None = None
    plan_id: str | None = None
    plan_approved: bool = False
    research_started: bool = False


# The top-level keys of the state, which `create_dial_state` lays out. The research record and the
# failure flag sit beside the preparation part, never inside it: a research record this code
# cannot read must never make the turn's `CrossTurnPrepState` unreadable, and the failure flag
# must not ride in `CrossTurnPrepState`, which every turn carries forward.
PREPARATION_STATE_KEY = "preparation"
"""The turn's preparation part (`PreparationDialState`)."""

SNAPSHOT_STATE_KEY = "research"
"""The turn's research record, read only by the snapshot reader."""

FAILURE_STATE_KEY = "turn_failed"
"""`True` on the state of a turn that failed and was delivered as a protocol error."""


class PreparationDialState(BaseModel):
    """The `preparation` part of the state a turn stores under `custom_content.state`.

    Stored, it holds every `CrossTurnPrepState` field directly, because StatGPT reads
    `preparation.research_started`, and next to them the preparation agent's messages of this
    turn and the whole response of each clarity check and each approval check it made. The two
    review lists are for observability only: nothing in the app reads them.
    """

    prep_state: CrossTurnPrepState
    # The fields below are stored in the same dict as the `CrossTurnPrepState` fields, so
    # `CrossTurnPrepState` must never get a field with one of their names: `to_dict` would
    # overwrite one value with the other.
    agent_messages: list[BaseMessage] = Field(default_factory=list)
    """The preparation agent's model replies and tool results of this turn, in run order."""

    query_reviews: list[QueryReviewResponse] = Field(default_factory=list)
    plan_reviews: list[PlanReviewResponse] = Field(default_factory=list)

    @classmethod
    def from_dict(cls, data: t.Any) -> t.Self:
        """Read a stored preparation part. The review lists are not read back, so a stored review
        never makes a state unreadable."""
        agent_messages = data.get('agent_messages', []) if isinstance(data, dict) else []
        return cls(prep_state=data, agent_messages=messages_from_dict(agent_messages))

    def to_dict(self) -> dict[str, t.Any]:
        return {
            **self.prep_state.model_dump(mode="json"),
            'agent_messages': messages_to_dict(self.agent_messages),
            'query_reviews': [review.model_dump(mode="json") for review in self.query_reviews],
            'plan_reviews': [review.model_dump(mode="json") for review in self.plan_reviews],
        }


def reconstruct_prep_agent_history(request: Request) -> list[BaseMessage]:
    """Walk `request.messages` and rebuild the history fed to the preparation agent.

    For each message:
    - USER -> `HumanMessage`;
    - ASSISTANT whose state carries `preparation.agent_messages` -> those messages, decoded;
    - ASSISTANT without them -> a single `AIMessage(content=…)` of its native content: a turn
      without state, a state that fails validation, or a state saved before the preparation
      agent's messages were kept apart from research's.

    An assistant message whose state carries the failure flag is followed by the
    fixed failed-turn note as a `SystemMessage`, so the agent and both checks
    learn the turn failed. The note sits at the failed turn's position, so the
    history before it stays the same from turn to turn. A research record is never read
    here: research-agent's messages and their images never reach preparation, so no file is
    downloaded.

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
            if state and state.agent_messages:
                history.extend(state.agent_messages)
            else:
                history.append(AIMessage(content=extract_text_from_content(message.content)))
            if (raw := raw_dial_state(message)) is not None and raw.get(FAILURE_STATE_KEY) is True:
                history.append(SystemMessage(content=FAILED_TURN_NOTE))
    return history


def is_failed_turn_note(message: BaseMessage) -> bool:
    """Whether `message` is the failed-turn note `reconstruct_prep_agent_history` inserts."""
    return message.type == "system" and message.content == FAILED_TURN_NOTE


def raw_dial_state(message: Message) -> dict | None:
    """The message's `custom_content.state` as a dict, unparsed; `None` when it has none."""
    if (cc := message.custom_content) is None or not isinstance(cc.state, dict):
        return None
    return cc.state


def create_dial_state(
    preparation: PreparationDialState,
    *,
    research: dict[str, t.Any] | None = None,
    turn_failed: bool = False,
) -> dict[str, t.Any]:
    """The whole state a turn saves: its preparation part, its research record when research ran,
    and the failure flag when the turn failed."""
    state: dict[str, t.Any] = {PREPARATION_STATE_KEY: preparation.to_dict()}
    if research is not None:
        state[SNAPSHOT_STATE_KEY] = research
    if turn_failed:
        state[FAILURE_STATE_KEY] = True
    return state


def _parse_dial_state(message: Message) -> PreparationDialState | None:
    # The first two are routine fallbacks (legacy or plain-text assistant turns), so they
    # log at DEBUG; a state that fails validation is unexpected but handled (the turn
    # continues on visible text), so it logs at WARNING — structure only, because the
    # rendered pydantic error embeds persisted conversation content.
    if not (cc := message.custom_content):
        logger.debug("No custom content found in message")
        return None
    if not isinstance(state := cc.state, dict):
        logger.debug("Custom content state is not a dictionary. Got: %s", type(state))
        return None
    try:
        return PreparationDialState.from_dict(state.get(PREPARATION_STATE_KEY, {}))
    except ValidationError as exc:
        logger.warning("Failed to validate DIAL state: %s", validation_error_summary(exc))
        return None
    except (KeyError, TypeError, ValueError) as exc:
        # `messages_from_dict` raises these for an agent message it cannot decode, such as a
        # message type a later release writes.
        logger.warning(
            "Failed to decode the DIAL state's agent messages: error=%s", type(exc).__name__
        )
        return None


def load_last_prep_state(request: Request) -> CrossTurnPrepState:
    """Load `CrossTurnPrepState` from the latest assistant message that carries one.

    Returns a fresh `CrossTurnPrepState` when no prior assistant message has one (the first
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
        return state.prep_state
    return CrossTurnPrepState()
