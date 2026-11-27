"""Every step's prompt carries its part of the rule that nobody calculates."""

from __future__ import annotations

from dial_deep_research.app.preparation.prompts import PREP_AGENT_SYSTEM, QUERY_REVIEW_SYSTEM
from dial_deep_research.app.research.prompts import (
    CALCULATION_DEFINITION,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    render_blind_review_system_prompt,
    render_client_rules,
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
    return render_blind_review_system_prompt(
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
    assert (
        "The plan never asks to calculate, compute, derive, estimate or model a figure." in prompt
    )
    assert "A plan step asks research to look for a source that states the figure." in prompt
    assert "the step asks research to find the figures that it is computed from" in prompt
    assert "When the query names only a measure, such as an index" in prompt
    assert "A comparison is not a calculation." in prompt


def test_the_rule_holds_when_the_user_insists() -> None:
    prompt = _words(PREP_AGENT_SYSTEM)
    assert "This holds for every request, also when the user insists." in prompt
    assert "Never promise or offer an operation." in prompt


def test_approval_is_checked_only_for_a_clear_approval() -> None:
    prompt = _words(PREP_AGENT_SYSTEM)
    assert "Call `approve_plan` only when the message clearly approves the plan" in prompt


def test_query_review_never_asks_how_to_calculate_or_convert() -> None:
    prompt = _words(QUERY_REVIEW_SYSTEM)
    assert "a figure in a unit or a currency that the user names, are clear subjects" in prompt
    assert "Do not ask how to calculate or convert a figure" in prompt
    assert "Do not ask which figure or unit to report instead." in prompt


def test_the_research_agent_looks_for_a_stated_figure() -> None:
    prompt = _words(RESEARCH_AGENT_SYSTEM_PROMPT)
    assert "Nobody calculates, not even the report writer" in prompt
    assert "Then look for a source that states the figure" in prompt
    assert "Never take a formula from your own knowledge" in prompt


def test_research_review_never_hands_a_calculation_to_the_writer() -> None:
    prompt = _words(RESEARCH_REVIEW_SYSTEM_PROMPT)
    assert "a note or a calculation" not in prompt
    assert "never ask for a calculation either" in prompt
    assert "is covered in these cases: - A source states the figure." in prompt


def test_the_writer_computes_nothing_whatever_the_request() -> None:
    prompt = _words(_writer())
    assert "## No calculation by research or the report" in prompt
    assert "Say that the sources do not give the computed figure" in prompt
    assert "Say that the sources give neither the figure nor how to compute it" in prompt
    assert '- the citation forms in "Citations"; - "No calculation by research or the report";' in (
        prompt
    )


def test_report_review_checks_for_calculations_before_the_glossary() -> None:
    prompt = _reviewer(glossary_check=True)
    assert "7. **No calculation by research or the report.**" in prompt
    assert "8. **Glossary terms.**" in prompt
    assert prompt.index("7. **No calculation by research or the report.**") < prompt.index(
        "8. **Glossary terms.**"
    )


def test_report_review_checks_for_calculations_without_a_glossary() -> None:
    prompt = _reviewer(glossary_check=False)
    assert "7. **No calculation by research or the report.**" in prompt
    assert "Glossary terms." not in prompt


def test_the_writer_and_the_reviewer_share_one_definition() -> None:
    """The referral to "Each figure with its source's value, unit and period" reaches both."""
    definition = _words(CALCULATION_DEFINITION)
    assert "and a rounding are not calculations either, but the rule" in definition
    assert "A conversion that needs a rate, such as into another currency, is a calculation" in (
        definition
    )
    assert "stay allowed" not in definition
    assert (
        "This rule has the highest priority of all the rules: no client-specific rule" in definition
    )
    assert definition in _words(_writer())
    assert definition in _words(_reviewer(glossary_check=False))


def test_no_client_rule_overrides_the_rule_that_nobody_calculates() -> None:
    """Every step that hears client rules is told they never override the rule."""
    rules = [
        QualityRule(
            name="Changes",
            research_agent="a",
            research_review="b",
            report_writer="c",
            report_review_blind="d",
        ),
        QualityRule(name="Grounded changes", report_review_grounded="e"),
    ]
    for step in RuleStep:
        block = _words(render_client_rules(rules, step=step))
        assert (
            "it has the highest priority of all the rules, and no rule below overrides it" in block
        )
    for prompt in (RESEARCH_AGENT_SYSTEM_PROMPT, RESEARCH_REVIEW_SYSTEM_PROMPT):
        assert "No client-specific rule overrides it" in _words(prompt)
