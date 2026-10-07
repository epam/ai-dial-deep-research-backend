"""Which prompts carry the data-sources string, and which carry each instruction about it."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from dial_deep_research.app.data_sources import DatasetsFetch, DataSources
from dial_deep_research.app.glossary import GlossaryFetch
from dial_deep_research.app.preparation import prompts as prep_prompts
from dial_deep_research.app.preparation.agent import render_prep_agent_system
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.prompts import (
    GLOSSARY_TERMINOLOGY_RULE,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    ReportReview,
    render_blind_review_system_prompt,
    render_data_sources_instructions,
    render_report_system_prompt,
)
from dial_deep_research.app_properties import DEFAULT_REPORT_STRUCTURE, GlossaryTools
from tests.citation_fakes import no_lookups
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_LIST_TOOL = "list_datasets"
_STRUCTURE_TOOL = "describe_dataset"
_TERMS_TOOL = "list_terms"
_DEFINITIONS_TOOL = "define_terms"
_TEXT = "## Publications\n\nMarket Outlook 2025.\n\nDatasets:\n[]"
_GLOSSARY = GlossaryTools.model_validate(
    {
        "list_terms_tool": _TERMS_TOOL,
        "definitions_tool": _DEFINITIONS_TOOL,
        "max_terms_per_definitions_call": 10,
        "references_table": {"title": "Glossary", "columns": [{"heading": "T", "key": "term"}]},
    }
)
_ALL_BOUND = {_LIST_TOOL, _STRUCTURE_TOOL, _TERMS_TOOL, _DEFINITIONS_TOOL}


def _sources(
    *,
    list_failed: bool = False,
    structures: bool = False,
    structures_failed: int = 0,
    glossary: GlossaryFetch | None = None,
) -> DataSources:
    return DataSources(
        text=_TEXT,
        datasets=DatasetsFetch(
            section="Datasets:\n...",
            catalogue=None if list_failed else {},
            structures_rendered=structures,
            structures_failed=structures_failed,
        ),
        glossary=glossary,
    )


def _instructions(
    data_sources: DataSources,
    *,
    bound: set[str] = _ALL_BOUND,
    structure_tool: str | None = _STRUCTURE_TOOL,
    glossary: GlossaryTools | None = None,
    failed_calls_only: bool = False,
) -> str:
    return render_data_sources_instructions(
        data_sources=data_sources,
        bound_tools=bound,
        list_datasets_tool=_LIST_TOOL,
        dataset_structure_tool=structure_tool,
        glossary=glossary,
        failed_calls_only=failed_calls_only,
    )


# --- preparation -------------------------------------------------------------------------------


def test_the_preparation_agent_carries_the_data_sources_string() -> None:
    prompt = render_prep_agent_system(
        agent_name="ACME", today_date="2026-09-27", data_sources=_sources()
    )
    assert f"<data_sources>\n{_TEXT}\n</data_sources>" in prompt
    assert prep_prompts.DATASET_LIST_FAILED_INSTRUCTION not in prompt


def test_a_failed_list_gives_the_preparation_agent_the_planning_instruction() -> None:
    prompt = render_prep_agent_system(
        agent_name="ACME", today_date="2026-09-27", data_sources=_sources(list_failed=True)
    )
    assert prep_prompts.DATASET_LIST_FAILED_INSTRUCTION in prompt
    assert "Search the available datasets for" in prompt
    assert "does not\n  apply to the datasets" in prompt


def test_a_channel_without_a_dataset_server_gives_no_planning_instruction() -> None:
    prompt = render_prep_agent_system(
        agent_name="ACME", today_date="2026-09-27", data_sources=DataSources(text=_TEXT)
    )
    assert prep_prompts.DATASET_LIST_FAILED_INSTRUCTION not in prompt


def test_no_preparation_prompt_tells_the_model_to_call_a_dataset_tool() -> None:
    agent_prompt = render_prep_agent_system(
        agent_name="ACME", today_date="2026-09-27", data_sources=_sources(list_failed=True)
    )
    clarity_prompt = prep_prompts.QUERY_REVIEW_SYSTEM.format(
        today_date="2026-09-27", data_sources=_TEXT
    )
    for prompt in (agent_prompt, clarity_prompt):
        assert _LIST_TOOL not in prompt
        assert _STRUCTURE_TOOL not in prompt
        assert "call the list" not in prompt.lower()


def test_the_plan_approval_check_receives_no_data_sources() -> None:
    assert "{data_sources" not in prep_prompts.PLAN_REVIEW_SYSTEM
    assert "<data_sources>" not in prep_prompts.PLAN_REVIEW_SYSTEM


# --- the dataset-tools instruction -------------------------------------------------------------


def test_both_tools_succeeded_and_bound_are_not_to_be_called() -> None:
    text = _instructions(_sources(structures=True))
    assert f"Do not call `{_LIST_TOOL}`." in text
    assert f"Do not call `{_STRUCTURE_TOOL}` for\nsuch a dataset." in text
    assert "failed to obtain dataset structure" not in text


def test_a_failed_list_tells_the_agent_to_call_both_tools_at_most_three_times() -> None:
    text = _instructions(_sources(list_failed=True))
    assert f"Call `{_LIST_TOOL}` when you need to know which\ndatasets exist" in text
    assert f"at most three `{_LIST_TOOL}` calls" in text
    assert f"Call `{_STRUCTURE_TOOL}` for each dataset whose structure" in text
    assert "Do not call" not in text


def test_a_failed_list_without_the_list_tool_gives_no_structure_part() -> None:
    text = _instructions(_sources(list_failed=True), bound={_STRUCTURE_TOOL})
    assert text == ""


def test_a_failed_structure_tells_the_agent_to_request_it() -> None:
    text = _instructions(_sources(structures=True, structures_failed=1))
    assert '"failed to obtain dataset structure"' in text
    assert f"at most three `{_STRUCTURE_TOOL}` calls for that dataset" in text
    assert f"Do not call `{_STRUCTURE_TOOL}`" in text


def test_a_filtered_out_structure_tool_gets_no_part() -> None:
    text = _instructions(_sources(structures=True, structures_failed=1), bound={_LIST_TOOL})
    assert _STRUCTURE_TOOL not in text
    assert f"Do not call `{_LIST_TOOL}`." in text


def test_the_playground_gets_only_the_failed_call_parts() -> None:
    assert _instructions(_sources(structures=True), failed_calls_only=True) == ""
    text = _instructions(_sources(structures=True, structures_failed=2), failed_calls_only=True)
    assert "Do not call" not in text
    assert '"failed to obtain dataset structure"' in text


def test_a_channel_without_a_dataset_server_gets_no_instruction() -> None:
    assert _instructions(DataSources(text=_TEXT)) == ""


# --- the glossary instruction ------------------------------------------------------------------


def test_a_failed_terms_list_tells_the_agent_to_list_and_define_the_terms() -> None:
    text = _instructions(
        _sources(glossary=GlossaryFetch(text="Glossary terms:\n...", records=None)),
        glossary=_GLOSSARY,
    )
    assert f"Call `{_TERMS_TOOL}` to obtain them" in text
    assert f"`{_DEFINITIONS_TOOL}` for the terms without a definition" in text


def test_unresolved_terms_are_re_requested_without_listing_again() -> None:
    fetch = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}] * 25, unresolved=2)
    text = _instructions(_sources(glossary=fetch), glossary=_GLOSSARY)
    assert _TERMS_TOOL not in text
    assert f"`{_DEFINITIONS_TOOL}`" in text
    assert "at most three calls" in text


def test_a_complete_glossary_tells_the_research_agent_not_to_call_the_glossary_tools() -> None:
    fetch = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}] * 25)
    text = _instructions(_sources(glossary=fetch), bound=_ALL_BOUND, glossary=_GLOSSARY)
    assert f"Do not call `{_TERMS_TOOL}` or `{_DEFINITIONS_TOOL}`." in text
    assert f"Call `{_TERMS_TOOL}`" not in text
    assert "without a definition" not in text


def test_a_complete_glossary_names_only_the_bound_glossary_tool() -> None:
    fetch = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}] * 25)
    text = _instructions(_sources(glossary=fetch), bound={_DEFINITIONS_TOOL}, glossary=_GLOSSARY)
    assert f"Do not call `{_DEFINITIONS_TOOL}`." in text
    assert _TERMS_TOOL not in text
    assert _instructions(_sources(glossary=fetch), bound=set(), glossary=_GLOSSARY) == ""


def test_the_playground_is_never_told_not_to_call_a_glossary_tool() -> None:
    fetch = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}] * 25)
    text = _instructions(
        _sources(glossary=fetch),
        bound={_TERMS_TOOL, _DEFINITIONS_TOOL},
        glossary=_GLOSSARY,
        failed_calls_only=True,
    )
    assert text == ""
    unresolved = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}], unresolved=1)
    text = _instructions(_sources(glossary=unresolved), glossary=_GLOSSARY, failed_calls_only=True)
    assert f"`{_DEFINITIONS_TOOL}` for the terms without a definition" in text


def test_a_filtered_out_definitions_tool_gets_no_part() -> None:
    fetch = GlossaryFetch(text="Glossary terms:\n...", records=[{"term": "a"}], unresolved=1)
    text = _instructions(_sources(glossary=fetch), bound=set(), glossary=_GLOSSARY)
    assert text == ""


# --- the research graph's prompts --------------------------------------------------------------


def test_the_research_agent_carries_the_data_sources_and_the_instruction() -> None:
    prompt = RESEARCH_AGENT_SYSTEM_PROMPT.format(
        today_date="2026-09-27",
        client_name="ACME",
        data_sources=_TEXT,
        data_sources_instructions="\nThe instruction.\n",
        rule_once_per_turn="r1",
        rule_never_alone="r2",
        verdict_retry_now="v1",
        verdict_retry_later="v2",
        verdict_will_not_help="v3",
        generic_rules="",
        client_rules="",
    )
    assert (
        f"<data_sources>\n{_TEXT}\n</data_sources>\n\nThe instruction.\n\n## Tools usage" in prompt
    )


class _RecordingLLM:
    """A chat model and a structured-output model in one, recording every call's messages.

    The grounded review, a plain call, approves and is not recorded.
    """

    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[list[Any]] = []

    def with_retry(self, **kwargs: Any) -> _RecordingLLM:
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content="No violations.")

    def with_structured_output(self, _schema: Any, *, include_raw: bool = False) -> Any:
        async def call(messages: list[Any]) -> Any:
            self.calls.append(list(messages))
            return self._result

        return RunnableLambda(call)


def _state(messages: list[Any] | None = None) -> dict[str, Any]:
    return {
        "messages": messages or [HumanMessage(content="seed")],
        "original_query": "q",
        "plans": [["step"]],
        "research_iteration": 1,
        "report": "## Overview\n\nA draft.",
        "report_version": 1,
    }


async def test_research_review_carries_the_data_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    from dial_deep_research.app.research.prompts import ResearchReview

    llm = _RecordingLLM(
        {"parsed": ResearchReview(assessment="ok"), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    node = nodes.make_research_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="2026-09-27",
        max_research_iterations=3,
        data_sources=_TEXT,
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
    )

    await node(_state())  # type: ignore[arg-type]

    system = llm.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert f"<data_sources>\n{_TEXT}\n</data_sources>" in system.content


def _review_node(monkeypatch: pytest.MonkeyPatch, *, listed: bool) -> tuple[Any, _RecordingLLM]:
    llm = _RecordingLLM(
        {"parsed": ReportReview(report_violations=[]), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    node = nodes.make_report_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="2026-09-27",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources=_TEXT,
        glossary=_GLOSSARY,
        glossary_fetch_listed_terms=listed,
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
    )
    return node, llm


def _tool_message(name: str, text: str, *, status: str = "success") -> ToolMessage:
    return ToolMessage(content=text, tool_call_id=f"call-{name}-{text}", name=name, status=status)


async def test_the_report_reviewer_receives_the_successful_glossary_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node, llm = _review_node(monkeypatch, listed=False)
    messages = [
        HumanMessage(content="seed"),
        _tool_message(_TERMS_TOOL, "the listed terms"),
        _tool_message(_DEFINITIONS_TOOL, "a failure", status="error"),
        _tool_message("query_datasets", "some data"),
        _tool_message(_DEFINITIONS_TOOL, "the definitions"),
    ]

    await node(_state(messages))  # type: ignore[arg-type]

    system = llm.calls[0][0].content
    assert (
        "<glossary_tool_results>\nthe listed terms\n\nthe definitions\n</glossary_tool_results>"
        in system
    )
    assert "a failure" not in system
    assert "some data" not in system
    assert "Glossary terminology" in system
    assert f"<data_sources>\n{_TEXT}\n</data_sources>" in system


async def test_a_failed_list_and_no_agent_result_give_the_reviewer_no_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node, llm = _review_node(monkeypatch, listed=False)

    await node(_state())  # type: ignore[arg-type]

    system = llm.calls[0][0].content
    assert "Glossary terminology" not in system
    assert "<glossary_tool_results>" not in system
    assert "[glossary <term>]" in system, "the reviewer still knows the citation form"


async def test_a_listed_glossary_gives_the_reviewer_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node, llm = _review_node(monkeypatch, listed=True)

    await node(_state())  # type: ignore[arg-type]

    assert "Glossary terminology" in llm.calls[0][0].content


def test_the_writer_and_the_reviewer_share_the_terminology_wording() -> None:
    writer = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources=_TEXT,
        glossary=True,
    )
    reviewer = render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        data_sources=_TEXT,
        glossary=True,
        glossary_check=True,
        glossary_tool_results=[],
    )
    # The reviewer's copy is indented as a list item, so the wording is compared, not the layout.
    rule = " ".join(GLOSSARY_TERMINOLOGY_RULE.split())
    assert rule in " ".join(writer.split())
    assert rule in " ".join(reviewer.split())
    assert "may lack terms or definitions" in writer
    assert "`[glossary <term>]`" in writer
    assert "four citation forms" in writer


def test_the_terminology_rule_makes_the_glossary_the_only_source_of_terms() -> None:
    """Both calls read the rule, so it both limits what counts as a glossary term and leaves other
    terms free to use."""
    rule = " ".join(GLOSSARY_TERMINOLOGY_RULE.split())
    assert "The glossary is the only source of glossary terms and definitions." in rule
    assert "such as in a dataset description, a document or a data-query result" in rule
    assert "A term the glossary does not list may be used freely" in rule


def test_the_terminology_rule_accepts_every_form_a_glossary_term_gives() -> None:
    """A slash term may be written as any of its names, and a term with an abbreviation in either
    form, the abbreviation spelled out at its first use, and a first letter may be lower case in
    mid-sentence; the citation keeps the whole term."""
    rule = " ".join(GLOSSARY_TERMINOLOGY_RULE.split())
    assert "may be written as any one of those names; the whole slash form is not required" in rule
    assert (
        "where the report uses the abbreviation, its first use is written as the full form followed"
        " by the abbreviation in parentheses"
    ) in rule
    assert "In mid-sentence, a glossary term's first letter may be written in lower case." in rule
    assert (
        "A `[glossary <term>]` citation still writes the whole term, as the glossary spells it."
        in rule
    )


def test_the_writer_is_told_the_data_sources_count_as_retrieved_sources() -> None:
    writer = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources=_TEXT,
        glossary=False,
    )
    assert f"<data_sources>\n{_TEXT}\n</data_sources>" in writer
    assert "counts as grounded in a retrieved source" in writer
    assert "description of a publication series is never cited" in writer


def test_no_prompt_on_a_channel_without_a_glossary_mentions_the_glossary() -> None:
    writer = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources=_TEXT,
        glossary=False,
    )
    reviewer = render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        data_sources=_TEXT,
        glossary=False,
        glossary_check=False,
        glossary_tool_results=["ignored without a glossary"],
    )
    for prompt in (writer, reviewer):
        assert "glossary" not in prompt.lower()
    assert "three citation forms" in writer
