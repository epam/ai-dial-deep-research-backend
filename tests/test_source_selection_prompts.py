"""Which step's prompt carries which part of the source-selection rules and of a channel's rules.

The two review calls judge those rules with reasoning, so the tests also pin their model settings.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.prompts import (
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    SOURCE_SELECTION_POLICY,
    ReportReview,
    ResearchReview,
    render_blind_review_system_prompt,
    render_client_rules,
    render_policy,
    render_report_system_prompt,
    render_rules,
    render_source_kinds,
)
from dial_deep_research.app.research.source_selection import SOURCE_SELECTION_RULES
from dial_deep_research.app_properties import (
    DEFAULT_REPORT_STRUCTURE,
    QualityRule,
    RuleStep,
    SourceKind,
)
from dial_deep_research.utils.llm import LLMModelConfig, ReasoningEffortEnum
from tests.citation_fakes import no_lookups
from tests.mcp_fakes import BOTH_SOURCE_KINDS


def render_source_selection(step: RuleStep, source_kinds: set[SourceKind]) -> str:
    """The source-selection block of `step`'s prompt."""
    return render_policy(
        SOURCE_SELECTION_POLICY,
        step,
        glossary=False,
        source_kinds_statement=render_source_kinds(source_kinds),
    )


_WRITER_ONLY = QualityRule(name="Writer rule", report_writer="Write it this way.")
_CLIENT_RULE = QualityRule(
    name="Dataset methodology", research_agent="Search the methodology pages only."
)


def test_a_part_reaches_only_its_step() -> None:
    rule = QualityRule(name="Two steps", research_agent="Agent text.", report_writer="Writer text.")
    assert render_rules([rule], RuleStep.RESEARCH_AGENT) == "### Two steps\n\nAgent text."
    assert render_rules([rule], RuleStep.REPORT_WRITER) == "### Two steps\n\nWriter text."
    assert render_rules([rule], RuleStep.RESEARCH_REVIEW) == ""
    assert render_rules([rule], RuleStep.REPORT_REVIEW_BLIND) == ""
    assert render_rules([rule], RuleStep.REPORT_REVIEW_GROUNDED) == ""


def test_no_client_rule_for_a_step_renders_no_block() -> None:
    assert render_client_rules([], RuleStep.RESEARCH_AGENT) == ""
    assert render_client_rules([_WRITER_ONLY], RuleStep.REPORT_REVIEW_BLIND) == ""
    assert render_client_rules([_WRITER_ONLY], RuleStep.REPORT_REVIEW_GROUNDED) == ""


def test_a_client_rule_is_tagged_after_its_introduction() -> None:
    block = render_client_rules([_CLIENT_RULE], RuleStep.RESEARCH_AGENT)
    assert block.startswith("## Client-specific rules\n\n")
    assert "where\none is more specific than a rule above, follow it" in block
    assert (
        "<client_rules>\n### Dataset methodology\n\nSearch the methodology pages only.\n"
        "</client_rules>"
    ) in block


@pytest.mark.parametrize("step", [RuleStep.REPORT_REVIEW_BLIND, RuleStep.REPORT_REVIEW_GROUNDED])
def test_both_reviews_read_client_rules_as_checks(step: RuleStep) -> None:
    rule = QualityRule(name="Dates", **{step.value: "Check the dates."})
    assert render_client_rules([rule], step).startswith("## Client-specific checks\n\n")


@pytest.mark.parametrize("step", list(RuleStep))
def test_every_step_gets_the_terms_and_its_parts(step: RuleStep) -> None:
    block = render_source_selection(step, source_kinds=BOTH_SOURCE_KINDS)
    assert "### Terms" in block
    assert "**Supersede**" in block
    assert "**Qualifying context**" in block
    for rule in SOURCE_SELECTION_RULES:
        part = rule.part(SOURCE_SELECTION_POLICY.rule_step(step))
        assert (part is not None) == (f"### {rule.name}\n\n{part}" in block)


def test_the_grounded_review_reads_the_writer_parts() -> None:
    block = render_source_selection(RuleStep.REPORT_REVIEW_GROUNDED, source_kinds=BOTH_SOURCE_KINDS)
    assert block.startswith("## Source selection, judged against the findings\n\n")
    for rule in SOURCE_SELECTION_RULES:
        if rule.report_writer is not None:
            assert rule.report_writer in block
        if rule.report_review_blind is not None:
            assert rule.report_review_blind not in block


def test_only_the_research_steps_get_the_reasonable_attempt() -> None:
    assert "**Reasonable attempt**" in render_source_selection(
        RuleStep.RESEARCH_AGENT, source_kinds=BOTH_SOURCE_KINDS
    )
    assert "**Reasonable attempt**" in render_source_selection(
        RuleStep.RESEARCH_REVIEW, source_kinds=BOTH_SOURCE_KINDS
    )
    assert "**Reasonable attempt**" not in render_source_selection(
        RuleStep.REPORT_WRITER, source_kinds=BOTH_SOURCE_KINDS
    )
    for step in (RuleStep.REPORT_REVIEW_BLIND, RuleStep.REPORT_REVIEW_GROUNDED):
        assert "**Reasonable attempt**" not in render_source_selection(
            step, source_kinds=BOTH_SOURCE_KINDS
        )


@pytest.mark.parametrize(
    ("source_kinds", "statement"),
    [
        ({"document", "dataset"}, "This channel's sources are publications and datasets."),
        (
            {"document"},
            "This channel's sources are publications. It has no datasets, so the parts below"
            " about datasets do not apply.",
        ),
        (
            {"dataset"},
            "This channel's sources are datasets. It has no publications, so the parts below"
            " about publications do not apply.",
        ),
    ],
)
def test_every_step_is_told_the_channels_kinds_of_source(
    source_kinds: set[SourceKind], statement: str
) -> None:
    assert render_source_kinds(source_kinds) == statement
    for step in RuleStep:
        assert statement in render_source_selection(step, source_kinds=source_kinds)


def test_a_channel_needs_a_kind_of_source() -> None:
    with pytest.raises(ValueError, match="at least one kind of source"):
        render_source_kinds(set())


def test_a_kind_of_source_without_a_name_is_an_error() -> None:
    with pytest.raises(ValueError, match="no name for the kind"):
        render_source_kinds({"web"})  # type: ignore[arg-type]


def test_the_writer_and_the_reviewer_are_told_the_channels_kinds_of_source() -> None:
    writer = render_report_system_prompt(
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources="x",
        glossary=False,
        source_kinds={"dataset"},
        client_rules=(),
    )
    reviewer = render_blind_review_system_prompt(
        today_date="d",
        data_sources="x",
        glossary=False,
        glossary_check=False,
        glossary_tool_results=[],
        source_kinds={"dataset"},
        client_rules=(),
    )
    for prompt in (writer, reviewer):
        assert render_source_kinds({"dataset"}) in prompt


def _words(text: str) -> str:
    """The text with every run of whitespace collapsed, so an assertion ignores line wrapping."""
    return " ".join(text.split())


def test_research_review_can_resolve_the_failed_tool_reference() -> None:
    """The term's failed-tool clause relies on a rule research review's own prompt states."""
    block = _words(
        render_source_selection(RuleStep.RESEARCH_REVIEW, source_kinds=BOTH_SOURCE_KINDS)
    )
    assert "once that tool has failed for it and may not be called again for it" in block
    assert "Research-agent has already retried it as far as it is allowed" in _words(
        RESEARCH_REVIEW_SYSTEM_PROMPT
    )


def test_the_latest_value_rule_holds_on_a_channel_with_one_kind_of_source() -> None:
    """A channel may configure datasets only or documents only, so the publication search is
    required only where publications exist."""
    latest = next(rule for rule in SOURCE_SELECTION_RULES if rule.name == "The latest value")
    assert "Where it has both publications and datasets, a dataset value does not make" in _words(
        latest.part(RuleStep.RESEARCH_AGENT) or ""
    )
    assert "Where the channel has publications, every fact" in _words(
        latest.part(RuleStep.RESEARCH_REVIEW) or ""
    )


def test_the_research_agent_is_never_asked_to_write() -> None:
    """The research agent only calls tools, so its parts ask for retrievals alone."""
    for rule in SOURCE_SELECTION_RULES:
        part = (rule.part(RuleStep.RESEARCH_AGENT) or "").lower()
        for verb in ("record", "note ", "summaris", "summariz", "write "):
            assert verb not in part, (rule.name, verb)


def test_the_generic_rules_name_no_tool() -> None:
    for rule in SOURCE_SELECTION_RULES:
        for step in RuleStep:
            assert "list_documents" not in (rule.part(step) or "")


class _RecordingLLM:
    """A chat model and a structured-output model in one, recording every call's messages."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[list[Any]] = []

    def with_structured_output(self, _schema: Any, *, include_raw: bool = False) -> Any:
        async def call(messages: list[Any]) -> Any:
            self.calls.append(list(messages))
            return self._result

        return RunnableLambda(call)


def _state() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="seed")],
        "original_query": "q",
        "plans": [["step"]],
        "research_iteration": 1,
        "report": "## Overview\n\nA draft.",
        "report_version": 1,
    }


def test_the_research_agent_prompt_carries_both_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(nodes, "create_agent", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: None)
    nodes.build_research_agent(
        source_kinds=BOTH_SOURCE_KINDS,
        tools=[],
        today_date="2026-09-29",
        client_name="ACME",
        data_sources="Datasets:\n[]",
        data_sources_instructions="",
        client_rules=[_CLIENT_RULE],
        glossary=None,
    )
    prompt = captured["system_prompt"]
    assert (
        render_source_selection(RuleStep.RESEARCH_AGENT, source_kinds=BOTH_SOURCE_KINDS) in prompt
    )
    assert render_client_rules([_CLIENT_RULE], RuleStep.RESEARCH_AGENT) in prompt
    assert prompt.index("## Source selection") < prompt.index("## Data sources")
    assert "A\n  publication's stated date is the exception" in prompt
    assert "checks on the plan's items and on the rule sections" in prompt


async def test_research_review_prompt_carries_both_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = QualityRule(name="Dataset releases", research_review="A release is never a gap.")
    llm = _RecordingLLM(
        {"parsed": ResearchReview(assessment="ok"), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    node = nodes.make_research_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="2026-09-29",
        max_research_iterations=3,
        data_sources="Datasets:\n[]",
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        client_rules=[rule, _WRITER_ONLY],
        glossary=None,
    )

    await node(_state())  # type: ignore[arg-type]

    system = llm.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert (
        render_source_selection(RuleStep.RESEARCH_REVIEW, source_kinds=BOTH_SOURCE_KINDS)
        in system.content
    )
    assert "<client_rules>\n### Dataset releases\n\nA release is never a gap." in system.content
    assert "Writer rule" not in system.content
    assert "so never ask for a calculation either." in system.content


def test_the_research_review_schema_names_the_rules_gaps() -> None:
    schema = ResearchReview.model_json_schema()
    assert "rule sections" in schema["description"]
    assert "rule sections" in schema["properties"]["assessment"]["description"]
    assert "rule sections" in schema["properties"]["next_steps"]["description"]


def test_the_writer_prompt_carries_both_blocks_and_the_prohibitions() -> None:
    prompt = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources="Datasets:\n[]",
        glossary=False,
        client_rules=[_WRITER_ONLY],
    )
    assert render_source_selection(RuleStep.REPORT_WRITER, source_kinds=BOTH_SOURCE_KINDS) in prompt
    assert "<client_rules>\n### Writer rule\n\nWrite it this way." in prompt
    assert "never average or merge differing values" in prompt
    assert (
        "say in one sentence that they are given separately because the sources differ"
        in _words(prompt)
    )


def test_the_report_review_prompt_places_the_checks_before_not_your_job() -> None:
    rule = QualityRule(name="Dates", report_review_blind="Check the dates.")
    prompt = render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        data_sources="Datasets:\n[]",
        glossary=False,
        glossary_check=False,
        glossary_tool_results=[],
        client_rules=[rule],
    )
    assert prompt.index("## Source-selection checks") < prompt.index("## Not your job")
    assert prompt.index("## Client-specific checks") < prompt.index("## Not your job")
    assert "together with the checks of every rule section below" in _words(prompt)
    assert "right one to use" not in prompt


def test_no_client_rules_leave_no_client_block() -> None:
    writer = render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources="x",
        glossary=False,
    )
    reviewer = render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        client_rules=(),
        today_date="d",
        data_sources="x",
        glossary=False,
        glossary_check=False,
        glossary_tool_results=[],
    )
    for prompt in (writer, reviewer):
        assert "<client_rules>" not in prompt
        assert "this deployment's configuration" not in prompt
        assert "### Terms" in prompt


async def test_report_review_node_passes_its_client_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = QualityRule(name="Dates", report_review_blind="Check the dates.")
    llm = _RecordingLLM(
        {"parsed": ReportReview(report_violations=[]), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    node = nodes.make_report_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="2026-09-29",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources="x",
        glossary=None,
        glossary_fetch_listed_terms=False,
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        client_rules=[rule],
    )

    await node(_state())  # type: ignore[arg-type]

    assert "<client_rules>\n### Dates\n\nCheck the dates." in llm.calls[0][0].content


async def test_research_review_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    configs: list[LLMModelConfig] = []
    llm = _RecordingLLM(
        {"parsed": ResearchReview(assessment="ok"), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(
        nodes, "get_chat_model", lambda model_config: configs.append(model_config) or llm
    )
    node = nodes.make_research_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="2026-09-29",
        max_research_iterations=3,
        data_sources="Datasets:\n[]",
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        client_rules=[],
        glossary=None,
    )

    await node(_state())  # type: ignore[arg-type]

    assert [c.reasoning_effort for c in configs] == [ReasoningEffortEnum.MEDIUM]


async def test_report_review_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    configs: list[LLMModelConfig] = []
    llm = _RecordingLLM(
        {"parsed": ReportReview(report_violations=[]), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(
        nodes, "get_chat_model", lambda model_config: configs.append(model_config) or llm
    )
    node = nodes.make_report_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="2026-09-29",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources="x",
        glossary=None,
        glossary_fetch_listed_terms=False,
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        client_rules=[],
    )

    await node(_state())  # type: ignore[arg-type]

    # The blind review and the grounded review.
    assert [c.reasoning_effort for c in configs] == [ReasoningEffortEnum.MEDIUM] * 2


def test_the_research_agent_is_told_the_channels_kinds_of_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(nodes, "create_agent", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: None)
    nodes.build_research_agent(
        tools=[],
        today_date="2026-09-29",
        client_name="ACME",
        data_sources="x",
        data_sources_instructions="",
        source_kinds={"document"},
        client_rules=(),
        glossary=None,
    )
    assert render_source_kinds({"document"}) in captured["system_prompt"]


async def test_research_review_is_told_the_channels_kinds_of_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _RecordingLLM(
        {"parsed": ResearchReview(assessment="ok"), "parsing_error": None, "raw": AIMessage("")}
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: llm)
    node = nodes.make_research_review_node(
        today_date="2026-09-29",
        max_research_iterations=3,
        data_sources="Datasets:\n[]",
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        source_kinds={"dataset"},
        client_rules=(),
        glossary=None,
    )

    await node(_state())  # type: ignore[arg-type]

    assert render_source_kinds({"dataset"}) in llm.calls[0][0].content
