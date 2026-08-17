"""The `update_status` tool: what it answers the model, and what it never shows the user.

The tool researches nothing. It reports the call, and the runner turns that into the open
activity stage. All it decides for itself is whether the calling message broke one of the two
rules it can see, which it judges from the assistant message carrying its own call.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_core.tools import tool as make_tool

from dial_deep_research.app.research.prompts import RESEARCH_AGENT_SYSTEM_PROMPT
from dial_deep_research.app.research.tools import (
    HOW_TO_WRITE_STATUS,
    RULE_NEVER_ALONE,
    RULE_ONCE_PER_TURN,
    UPDATE_STATUS_RESULT,
    UPDATE_STATUS_TOOL_NAME,
    build_update_status_tool,
)


def _invoke(tool: BaseTool, *, status: str, siblings: list[dict[str, Any]]) -> str:
    """Run the tool with the assistant message that requested it, as the tools node would.

    The injected argument is excluded from the schema the model sees but is still part of the
    tool's own, so a direct call supplies it in the input.
    """
    calls = [{"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": status}, "id": "c1"}, *siblings]
    ai = AIMessage(content="", tool_calls=calls)
    return str(tool.invoke({"status": status, "state": {"messages": [ai]}}))


def test_a_status_beside_a_research_tool_is_simply_acknowledged() -> None:
    tool = build_update_status_tool()

    content = _invoke(
        tool,
        status="Looking for US GDP forecasts",
        siblings=[{"name": "rag_search", "args": {}, "id": "c2"}],
    )

    assert content == UPDATE_STATUS_RESULT


def test_a_status_alone_is_told_it_must_not_be() -> None:
    tool = build_update_status_tool()

    content = _invoke(tool, status="Looking for forecasts", siblings=[])

    assert RULE_NEVER_ALONE in content
    assert RULE_ONCE_PER_TURN not in content


def test_repeated_statuses_are_told_to_be_one() -> None:
    tool = build_update_status_tool()

    content = _invoke(
        tool,
        status="Looking for forecasts",
        siblings=[
            {"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": "And inflation"}, "id": "c2"},
            {"name": "rag_search", "args": {}, "id": "c3"},
        ],
    )

    assert RULE_ONCE_PER_TURN in content
    assert RULE_NEVER_ALONE not in content


def test_both_misuses_at_once_are_both_reported() -> None:
    tool = build_update_status_tool()

    content = _invoke(
        tool,
        status="Looking for forecasts",
        siblings=[
            {"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": "And inflation"}, "id": "c2"}
        ],
    )

    assert RULE_ONCE_PER_TURN in content
    assert RULE_NEVER_ALONE in content


def test_the_argument_carries_how_to_write_a_status() -> None:
    """What to put in the argument is documented on the argument, where the model fills it in."""
    schema = build_update_status_tool().tool_call_schema.model_json_schema()

    assert schema["properties"]["status"]["description"] == HOW_TO_WRITE_STATUS
    assert "state" not in schema["properties"]


def test_the_correction_repeats_the_wording_the_prompt_showed() -> None:
    """The two catchable rules are shared for exactly this reason: the model is corrected with the
    same sentence it was instructed with. The rules govern the shape of a turn, so the prompt states
    them and the tool's description does not."""
    prompt = RESEARCH_AGENT_SYSTEM_PROMPT.format(
        today_date="2026-08-14",
        client_name="ACME",
        rule_once_per_turn=RULE_ONCE_PER_TURN,
        rule_never_alone=RULE_NEVER_ALONE,
    )
    description = build_update_status_tool().description

    for rule in (RULE_ONCE_PER_TURN, RULE_NEVER_ALONE):
        assert rule in prompt
        assert rule not in description
    # The third rule has no second reader, so the prompt owns its wording outright.
    assert "Never call update_status together with finish_iteration" in prompt


class _FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


@make_tool
def _search(query: str) -> str:
    """Search the knowledge base."""
    return "hits"


async def test_the_agent_supplies_the_calling_message_as_injected_state() -> None:
    """The misuse check rests on this: run inside a real agent, the tool's injected state ends
    with the `AIMessage` carrying its own call, so that call's siblings are visible to it.

    Asserted through the tool's answer rather than by peeking: here the status shares its
    message with a research tool, which is correct usage, so no correction comes back — and it
    only can be judged correct if the sibling call was visible.
    """

    def _script() -> Iterator[AIMessage]:
        yield AIMessage(
            content="",
            tool_calls=[
                {"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": "Looking"}, "id": "c1"},
                {"name": "_search", "args": {"query": "x"}, "id": "c2"},
            ],
        )
        while True:
            yield AIMessage(content="done")

    agent = create_agent(
        model=_FakeToolCallingModel(messages=_script()),
        tools=[build_update_status_tool(), _search],
    )
    result = await agent.ainvoke({"messages": [("user", "go")]})

    [answer] = [
        m for m in result["messages"] if getattr(m, "name", None) == UPDATE_STATUS_TOOL_NAME
    ]
    assert answer.content == UPDATE_STATUS_RESULT


async def test_a_status_alone_is_corrected_inside_a_real_agent() -> None:
    """The mirror of the test above: with no sibling call, the same visibility produces the
    correction, so a passing pair rules out the tool simply never seeing anything."""

    def _script() -> Iterator[AIMessage]:
        yield AIMessage(
            content="",
            tool_calls=[
                {"name": UPDATE_STATUS_TOOL_NAME, "args": {"status": "Looking"}, "id": "c1"}
            ],
        )
        while True:
            yield AIMessage(content="done")

    agent = create_agent(
        model=_FakeToolCallingModel(messages=_script()),
        tools=[build_update_status_tool(), _search],
    )
    result = await agent.ainvoke({"messages": [("user", "go")]})

    [answer] = [
        m for m in result["messages"] if getattr(m, "name", None) == UPDATE_STATUS_TOOL_NAME
    ]
    assert RULE_NEVER_ALONE in str(answer.content)
