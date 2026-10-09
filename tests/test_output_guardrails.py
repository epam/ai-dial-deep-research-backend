"""The terminology, language-and-style and removal policies, and the app's emoji check."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from dial_deep_research.app.research import nodes
from dial_deep_research.app.research.prompts import (
    GENERIC_POLICIES,
    LANGUAGE_AND_STYLE_POLICY,
    REMOVAL_POLICY,
    TERMINOLOGY_POLICY,
    ReportReview,
    render_blind_review_system_prompt,
    render_generic_rules,
    render_grounded_review_prompt,
    render_policy,
)
from dial_deep_research.app.research.report_rules import ReportEmojiRule
from dial_deep_research.app_properties import (
    DEFAULT_REPORT_STRUCTURE,
    GlossaryTools,
    QualityRule,
    RuleStep,
)
from tests.citation_fakes import no_lookups
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_GLOSSARY = GlossaryTools.model_validate(
    {
        "list_terms_tool": "list_terms",
        "definitions_tool": "define_terms",
        "max_terms_per_definitions_call": 10,
        "references_table": {"title": "Glossary", "columns": [{"heading": "T", "key": "term"}]},
    }
)

_REPORT_STEPS = (
    RuleStep.REPORT_WRITER,
    RuleStep.REPORT_REVIEW_BLIND,
    RuleStep.REPORT_REVIEW_GROUNDED,
)


def _words(text: str) -> str:
    return " ".join(text.split())


def test_the_policies_render_in_order() -> None:
    assert [policy.headings[RuleStep.REPORT_WRITER][0] for policy in GENERIC_POLICIES] == [
        "Source selection",
        "Faithful relay",
        "Terminology",
        "Language and style",
        "Removed content",
    ]
    block = render_generic_rules(
        RuleStep.REPORT_WRITER, source_kinds=BOTH_SOURCE_KINDS, glossary=True
    )
    indexes = [
        block.index(f"## {heading}\n")
        for heading in (
            "Source selection",
            "Faithful relay",
            "Terminology",
            "Language and style",
            "Removed content",
        )
    ]
    assert indexes == sorted(indexes)


@pytest.mark.parametrize("step", [RuleStep.RESEARCH_AGENT, RuleStep.RESEARCH_REVIEW])
def test_the_research_steps_get_no_language_or_removal_block(step: RuleStep) -> None:
    for policy in (LANGUAGE_AND_STYLE_POLICY, REMOVAL_POLICY):
        assert render_policy(policy, step, glossary=True) == ""


def test_language_and_style_reaches_the_report_steps_with_its_terms() -> None:
    for step in _REPORT_STEPS:
        block = render_policy(LANGUAGE_AND_STYLE_POLICY, step, glossary=False)
        assert "### Verbatim names\n\nA verbatim name is a publication title" in block
    writer = render_policy(LANGUAGE_AND_STYLE_POLICY, RuleStep.REPORT_WRITER, glossary=False)
    blind = render_policy(LANGUAGE_AND_STYLE_POLICY, RuleStep.REPORT_REVIEW_BLIND, glossary=False)
    grounded = render_policy(
        LANGUAGE_AND_STYLE_POLICY, RuleStep.REPORT_REVIEW_GROUNDED, glossary=False
    )
    assert "### Neutral register" in writer and "### Neutral register" in blind
    assert "### Neutral register" not in grounded
    assert "### Names, not codes" in writer and "### Names, not codes" in grounded
    assert "### Names, not codes" not in blind
    assert "These checks are rules, not wording preferences." in _words(blind)


def test_removal_reaches_the_writer_and_the_blind_review_only() -> None:
    assert "### Removal" in render_policy(REMOVAL_POLICY, RuleStep.REPORT_WRITER, glossary=False)
    assert "### Removal" in render_policy(
        REMOVAL_POLICY, RuleStep.REPORT_REVIEW_BLIND, glossary=False
    )
    assert render_policy(REMOVAL_POLICY, RuleStep.REPORT_REVIEW_GROUNDED, glossary=False) == ""


def test_the_removal_rule_never_mentions_an_excluded_topic() -> None:
    writer = _words(render_policy(REMOVAL_POLICY, RuleStep.REPORT_WRITER, glossary=False))
    assert "do not say that the report does not cover it" in writer
    assert "leave that part out. Say nothing about it." in writer


def test_terminology_reaches_its_steps() -> None:
    agent = render_policy(TERMINOLOGY_POLICY, RuleStep.RESEARCH_AGENT, glossary=True)
    assert "### Glossary terms in searches" in agent
    writer = render_policy(TERMINOLOGY_POLICY, RuleStep.REPORT_WRITER, glossary=True)
    assert "### Accurate and consistent terms" in writer
    assert "### Glossary terms and source terms" in writer
    grounded = render_policy(TERMINOLOGY_POLICY, RuleStep.REPORT_REVIEW_GROUNDED, glossary=True)
    assert "### Accurate and consistent terms\n\nThese are violations:" in grounded
    assert render_policy(TERMINOLOGY_POLICY, RuleStep.REPORT_REVIEW_BLIND, glossary=True) == ""


def test_a_channel_without_a_glossary_hears_nothing_of_one_from_the_new_policies() -> None:
    for policy in (TERMINOLOGY_POLICY, LANGUAGE_AND_STYLE_POLICY, REMOVAL_POLICY):
        for step in RuleStep:
            assert "glossary" not in render_policy(policy, step, glossary=False).lower()
    assert render_policy(TERMINOLOGY_POLICY, RuleStep.RESEARCH_AGENT, glossary=False) == ""


def test_a_glossary_term_is_a_verbatim_name_on_a_glossary_channel() -> None:
    for step in (RuleStep.REPORT_WRITER, RuleStep.REPORT_REVIEW_BLIND):
        block = render_policy(LANGUAGE_AND_STYLE_POLICY, step, glossary=True)
        assert "A glossary term is also a verbatim name." in block


def test_the_blind_review_is_told_the_app_checks_emojis() -> None:
    prompt = render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        data_sources="x",
        glossary=False,
        glossary_check=False,
        glossary_tool_results=[],
        client_rules=[],
    )
    assert "- whether the draft carries an emoji" in prompt
    assert "The app checks the last five itself" in _words(prompt)


# --- The emoji check ---


@pytest.mark.parametrize(
    ("draft", "found"),
    [
        ("- ✅ Growth held up.", ["✅"]),
        ("🇺🇸 United States and 1️⃣ First", ["🇺🇸", "1️⃣"]),
        ("A trend ↗ and a warning ⚠️.", ["↗", "⚠️"]),
        ("👨‍👩‍👧 one family emoji", ["👨‍👩‍👧"]),
        ("✅ twice ✅", ["✅"]),
    ],
)
def test_the_emoji_check_quotes_each_emoji_once(draft: str, found: list[str]) -> None:
    (violation,) = ReportEmojiRule().violations(draft)
    assert violation.startswith(
        "The draft contains these emojis: " + ", ".join(f"`{emoji}`" for emoji in found) + "."
    )


@pytest.mark.parametrize(
    "draft", ["A product name™ and a brand®, © 2026.", "Plain text → with ✓ and ★.", ""]
)
def test_the_emoji_check_passes_a_draft_without_emojis(draft: str) -> None:
    assert ReportEmojiRule().violations(draft) == []


def test_the_writer_is_told_the_emoji_rule() -> None:
    instruction = ReportEmojiRule().writer_instruction()
    assert instruction.startswith("## No emojis\n\n")
    assert "↗, ⬆, ✔ and ⚠" in instruction


@pytest.mark.parametrize(
    ("draft", "found"),
    [
        ("A lone 🏽 swatch.", ["🏽"]),
        ("Thumbs 👍🏽 up.", ["👍🏽"]),
        ("A 👩🏽‍💻 coder.", ["👩🏽‍💻"]),
        ("England 🏴󠁧󠁢󠁥󠁮󠁧󠁿 flag.", ["🏴󠁧󠁢󠁥󠁮󠁧󠁿"]),
    ],
)
def test_the_emoji_check_quotes_modifiers_and_tag_flags_whole(draft: str, found: list[str]) -> None:
    (violation,) = ReportEmojiRule().violations(draft)
    assert violation.startswith(
        "The draft contains these emojis: " + ", ".join(f"`{emoji}`" for emoji in found) + "."
    )


def test_the_blind_review_is_told_the_allowed_forms_of_a_glossary_term() -> None:
    block = render_policy(LANGUAGE_AND_STYLE_POLICY, RuleStep.REPORT_REVIEW_BLIND, glossary=True)
    assert "Its allowed forms are not violations" in _words(block)
    assert 'The part "Verbatim names" defines the words the checks use.' in _words(block)


# --- The node wiring ---


class _RecordingModel:
    """A chat model for both reviews: records the blind call's messages through structured output
    and the grounded call's through `ainvoke`."""

    def __init__(self) -> None:
        self.blind_calls: list[list[Any]] = []
        self.grounded_calls: list[list[Any]] = []

    def with_structured_output(self, _schema: Any, *, include_raw: bool = False) -> Any:
        async def call(messages: list[Any]) -> Any:
            self.blind_calls.append(list(messages))
            return {
                "parsed": ReportReview(report_violations=[]),
                "parsing_error": None,
                "raw": AIMessage(""),
            }

        return RunnableLambda(call)

    async def ainvoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.grounded_calls.append(list(messages))
        return AIMessage("No violations.")


def _state() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="seed")],
        "original_query": "q",
        "plans": [["step"]],
        "research_iteration": 1,
        "report": "## Overview\n\nA draft.",
        "report_version": 1,
    }


async def test_the_report_review_node_routes_each_client_check_to_its_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _RecordingModel()
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
    monkeypatch.setattr(nodes, "with_stream_drop_retry", lambda runnable: runnable)
    rules = [
        QualityRule(name="Dates", report_review_blind="Check the dates."),
        QualityRule(name="Units", report_review_grounded="Check the units."),
    ]
    node = nodes.make_report_review_node(
        source_kinds={"document"},
        today_date="2026-10-08",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources="x",
        glossary=_GLOSSARY,
        glossary_fetch_listed_terms=False,
        emit_result_stage=lambda _o: None,
        emit_activity=lambda _t: None,
        client_rules=rules,
    )

    await node(_state())  # type: ignore[arg-type]

    blind = model.blind_calls[0][0].content
    grounded = model.grounded_calls[0][-2]
    assert isinstance(grounded, SystemMessage)
    assert "<client_rules>\n### Dates\n\nCheck the dates." in blind
    assert "Check the units." not in blind
    assert "<client_rules>\n### Units\n\nCheck the units." in grounded.content
    assert "Check the dates." not in grounded.content
    # The node passes the channel's kinds of source to the grounded instructions too.
    assert "This channel's sources are publications." in grounded.content


@pytest.mark.parametrize(("glossary", "present"), [(_GLOSSARY, True), (None, False)])
def test_the_research_agent_gets_the_glossary_search_rule_on_a_glossary_channel(
    monkeypatch: pytest.MonkeyPatch, glossary: GlossaryTools | None, present: bool
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(nodes, "create_agent", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: None)
    nodes.build_research_agent(
        source_kinds=BOTH_SOURCE_KINDS,
        tools=[],
        today_date="2026-10-08",
        client_name="ACME",
        data_sources="x",
        data_sources_instructions="",
        client_rules=[],
        glossary=glossary,
    )
    assert ("### Glossary terms in searches" in captured["system_prompt"]) is present


def test_a_figure_no_source_gives_is_not_excluded_content() -> None:
    writer = _words(render_policy(REMOVAL_POLICY, RuleStep.REPORT_WRITER, glossary=False))
    blind = _words(render_policy(REMOVAL_POLICY, RuleStep.REPORT_REVIEW_BLIND, glossary=False))
    assert (
        "A figure or a finding that the sources do not give is not excluded content, unless a rule"
        " excludes its topic." in writer
    )
    assert (
        "A statement that the sources do not give a figure or a finding is correct too, unless a"
        " rule excludes its topic." in blind
    )


def test_the_grounded_terminology_check_exempts_verbatim_names() -> None:
    grounded = _words(
        render_policy(TERMINOLOGY_POLICY, RuleStep.REPORT_REVIEW_GROUNDED, glossary=False)
    )
    assert "a term inside a verbatim name, such as a publication title or a quotation" in grounded


def test_the_grounded_review_asks_for_a_missing_value() -> None:
    prompt = _words(
        render_grounded_review_prompt(
            today_date="d",
            data_sources="x",
            source_kinds=BOTH_SOURCE_KINDS,
            glossary=False,
            client_rules=[],
        )
    )
    assert (
        "When the findings hold such a value and the draft leaves it out, report it and ask for it"
        " to be added, unless a rule keeps that content out of the report." in prompt
    )
    # Without client rules there is no context section, and nothing refers to one.
    assert "This deployment's writer rules" not in prompt
    assert "<client_writer_rules>" not in prompt


def test_the_grounded_review_reads_the_client_writer_rules_as_context() -> None:
    rules = [
        QualityRule(name="Bans", report_writer="Leave out share prices.", report_review_blind="x"),
        QualityRule(name="Dates", report_review_blind="Check the dates."),
    ]
    prompt = render_grounded_review_prompt(
        today_date="d",
        data_sources="x",
        source_kinds=BOTH_SOURCE_KINDS,
        glossary=False,
        client_rules=rules,
    )
    assert "## This deployment's writer rules" in prompt
    assert "They are context, not checks" in _words(prompt)
    assert "Never ask for content that they keep out of the report." in _words(prompt)
    assert (
        "<client_writer_rules>\n### Bans\n\nLeave out share prices.\n</client_writer_rules>"
        in prompt
    )
    assert "Check the dates." not in prompt
    assert prompt.index("## No calculations") < prompt.index("## This deployment's writer rules")
    assert prompt.index("## This deployment's writer rules") < prompt.index("## Data sources")


def test_an_exclusion_holds_against_a_reviews_request() -> None:
    writer = _words(render_policy(REMOVAL_POLICY, RuleStep.REPORT_WRITER, glossary=False))
    assert "even when the research question, the plan or a review asks for that content" in writer
