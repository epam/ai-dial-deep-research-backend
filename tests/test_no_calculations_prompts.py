"""Every step's prompt carries its part of the rule that nobody calculates."""

from __future__ import annotations

from dial_deep_research.app.preparation.prompts import PREP_AGENT_SYSTEM, QUERY_REVIEW_SYSTEM
from dial_deep_research.app.research.prompts import (
    CALCULATION_DEFINITION,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    render_client_rules,
    render_report_review_system_prompt,
    render_report_system_prompt,
)
from dial_deep_research.app_properties import QualityRule, RuleStep
from tests.mcp_fakes import BOTH_SOURCE_KINDS
from tests.test_source_selection_prompts import _words


def _writer() -> str:
    return render_report_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        rules="",
        protected_sections="Overview",
        data_sources="Datasets:\n[]",
        glossary=False,
        client_rules=(),
    )


def _reviewer(*, glossary_check: bool) -> str:
    return render_report_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        data_sources="Datasets:\n[]",
        glossary=glossary_check,
        glossary_check=glossary_check,
        glossary_tool_results=[],
        client_rules=(),
    )


def test_the_plan_never_asks_for_a_calculation() -> None:
    prompt = _words(PREP_AGENT_SYSTEM)
    assert "The plan NEVER asks to calculate, compute, derive, estimate or model a figure" in prompt
    assert "look for a source that states the figure itself" in prompt


def test_query_review_never_asks_how_to_compute() -> None:
    assert "Never ask how a figure should be computed" in _words(QUERY_REVIEW_SYSTEM)


def test_the_research_agent_looks_for_a_stated_figure() -> None:
    prompt = _words(RESEARCH_AGENT_SYSTEM_PROMPT)
    assert "Nobody calculates, not even the report writer" in prompt
    assert "look for a source that states the figure itself" in prompt


def test_research_review_never_hands_a_calculation_to_the_writer() -> None:
    prompt = _words(RESEARCH_REVIEW_SYSTEM_PROMPT)
    assert "a note or a calculation" not in prompt
    assert "never ask for a calculation either" in prompt
    assert "is covered once the findings show a reasonable attempt" in prompt


def test_the_writer_computes_nothing_whatever_the_request() -> None:
    prompt = _words(_writer())
    assert "## No calculations" in prompt
    assert "say that the sources do not give the computed figure" in prompt
    assert 'the citation format, the "No calculations" rule' in prompt


def test_report_review_checks_for_calculations_before_the_glossary() -> None:
    prompt = _reviewer(glossary_check=True)
    assert "7. **No calculations.**" in prompt
    assert "8. **Glossary terminology.**" in prompt
    assert prompt.index("7. **No calculations.**") < prompt.index("8. **Glossary terminology.**")


def test_report_review_checks_for_calculations_without_a_glossary() -> None:
    prompt = _reviewer(glossary_check=False)
    assert "7. **No calculations.**" in prompt
    assert "Glossary terminology" not in prompt


def test_the_writer_and_the_reviewer_share_one_definition() -> None:
    """Rounding and the precedence over section descriptions and client rules reach both."""
    definition = _words(CALCULATION_DEFINITION)
    assert "rounding a value given with more digits than a reader can use" in definition
    assert (
        "This rule has the highest priority of all the rules: no client-specific rule" in definition
    )
    assert definition in _words(_writer())
    assert definition in _words(_reviewer(glossary_check=False))


def test_no_client_rule_overrides_the_rule_that_nobody_calculates() -> None:
    """Every step that hears client rules is told they never override the rule."""
    rule = QualityRule(
        name="Changes",
        research_agent="a",
        research_review="b",
        report_writer="c",
        report_review="d",
    )
    for step in RuleStep:
        block = _words(render_client_rules([rule], step=step))
        assert (
            "it has the highest priority of all the rules, and no rule below overrides it" in block
        )
    for prompt in (RESEARCH_AGENT_SYSTEM_PROMPT, RESEARCH_REVIEW_SYSTEM_PROMPT):
        assert "no client-specific rule overrides it" in _words(prompt)
