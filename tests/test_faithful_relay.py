"""The faithful-relay rules in every step's prompt, and report review's grounded review."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from dial_deep_research.app.preparation.prompts import PREP_AGENT_SYSTEM
from dial_deep_research.app.research import nodes
from dial_deep_research.app.research import prompts as research_prompts
from dial_deep_research.app.research.faithful_relay import FAITHFUL_RELAY_RULES
from dial_deep_research.app.research.nodes import (
    ReportReviewOutcome,
    grounded_review_messages,
    parse_review_items,
)
from dial_deep_research.app.research.prompts import (
    FAITHFUL_RELAY_POLICY,
    GROUNDED_REVIEW_SYSTEM_MESSAGE,
    NO_CALCULATIONS_WRITER_RULE,
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_REVIEW_SYSTEM_PROMPT,
    GenericPolicy,
    ReportReview,
    render_blind_review_system_prompt,
    render_generic_rules,
    render_grounded_review_prompt,
    render_policy,
    render_report_system_prompt,
    render_rules,
    render_source_kinds,
)
from dial_deep_research.app.research.source_selection import (
    SOURCE_SELECTION_RULES,
    SOURCE_SELECTION_TERMS,
)
from dial_deep_research.app_properties import (
    DEFAULT_REPORT_STRUCTURE,
    QualityRule,
    RuleStep,
)
from tests.citation_fakes import no_lookups
from tests.mcp_fakes import BOTH_SOURCE_KINDS

_HEADINGS = {
    RuleStep.RESEARCH_AGENT: ("## Source selection", "## Faithful relay"),
    RuleStep.RESEARCH_REVIEW: ("## Source selection", "## Faithful relay"),
    RuleStep.REPORT_WRITER: ("## Source selection", "## Faithful relay"),
    RuleStep.REPORT_REVIEW_BLIND: ("## Source-selection checks", "## Faithful-relay checks"),
    RuleStep.REPORT_REVIEW_GROUNDED: (
        "## Source selection, judged against the findings",
        "## Faithful relay, judged against the findings",
    ),
}


def _words(text: str) -> str:
    """The text with every run of whitespace made one space, so a test is blind to line wraps."""
    return " ".join(text.split())


def _writer_prompt(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "source_kinds": BOTH_SOURCE_KINDS,
        "today_date": "d",
        "rules": "",
        "protected_sections": "Overview",
        "data_sources": "Datasets:\n[]",
        "glossary": False,
        "client_rules": [],
    }
    return render_report_system_prompt(**(kwargs | overrides))


def _review_prompt() -> str:
    return render_blind_review_system_prompt(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="d",
        data_sources="Datasets:\n[]",
        glossary=False,
        glossary_check=False,
        glossary_tool_results=[],
        client_rules=[],
    )


# --- The policy mechanism ---


@pytest.mark.parametrize("step", list(RuleStep))
def test_every_step_gets_source_selection_then_faithful_relay(step: RuleStep) -> None:
    block = render_generic_rules(step, source_kinds=BOTH_SOURCE_KINDS, glossary=False)
    source_selection, faithful_relay = _HEADINGS[step]
    assert block.index(source_selection) < block.index(faithful_relay)
    # The kinds-of-source statement opens the source-selection block only.
    statement = render_source_kinds(BOTH_SOURCE_KINDS)
    assert block.count(statement) == 1
    assert block.index(statement) < block.index(faithful_relay)


@pytest.mark.parametrize("step", list(RuleStep))
def test_every_step_gets_its_faithful_relay_parts(step: RuleStep) -> None:
    block = render_generic_rules(step, source_kinds=BOTH_SOURCE_KINDS, glossary=False)
    assert "### Faithful-relay terms\n\n" in block
    for rule in FAITHFUL_RELAY_RULES:
        part = rule.part(FAITHFUL_RELAY_POLICY.rule_step(step))
        if part is None:
            assert f"### {rule.name}\n" not in block
        else:
            assert f"### {rule.name}\n\n{part}" in block


def test_a_policy_with_no_part_for_a_step_adds_no_block() -> None:
    policy = GenericPolicy(
        headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
        rules=(QualityRule(name="Only writer", report_writer="Do it."),),
    )
    assert render_policy(policy, RuleStep.RESEARCH_AGENT, glossary=False) == ""
    assert "## Writing" in render_policy(policy, RuleStep.REPORT_WRITER, glossary=False)


def test_terms_alone_add_no_block() -> None:
    policy = GenericPolicy(
        headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
        rules=(QualityRule(name="Only writer", report_writer="Do it."),),
        terms_name="Terms",
        terms={RuleStep.REPORT_WRITER: "A word means this."},
    )
    assert render_policy(policy, RuleStep.RESEARCH_AGENT, glossary=False) == ""
    assert render_policy(policy, RuleStep.REPORT_WRITER, glossary=False) == (
        "## Writing\n\nWrite so.\n\n### Terms\n\nA word means this.\n\n"
        "### Only writer\n\nDo it.\n\n"
    )


def test_glossary_rules_render_only_with_a_glossary() -> None:
    policy = GenericPolicy(
        headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
        rules=(QualityRule(name="Always", report_writer="Do it."),),
        glossary_rules=(QualityRule(name="Glossary only", report_writer="Use the glossary."),),
    )
    assert "### Glossary only" not in render_policy(policy, RuleStep.REPORT_WRITER, glossary=False)
    assert "### Glossary only" in render_policy(policy, RuleStep.REPORT_WRITER, glossary=True)


def test_a_writer_parts_policy_rejects_a_grounded_part() -> None:
    with pytest.raises(ValueError, match="sets a grounded part, which its policy never renders"):
        GenericPolicy(
            headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
            rules=(QualityRule(name="Checked", report_review_grounded="Check it."),),
            grounded_by_writer_parts=True,
        )


def test_a_policy_with_terms_needs_them_for_every_step_it_renders() -> None:
    with pytest.raises(ValueError, match="no report_writer terms"):
        GenericPolicy(
            headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
            rules=(QualityRule(name="Only writer", report_writer="Do it."),),
            terms_name="Terms",
            terms={RuleStep.RESEARCH_AGENT: "A word means this."},
        )


def test_a_glossary_rule_whose_step_has_no_heading_fails_when_the_policy_is_defined() -> None:
    with pytest.raises(ValueError, match="no research_agent heading"):
        GenericPolicy(
            headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
            rules=(QualityRule(name="Only writer", report_writer="Do it."),),
            glossary_rules=(QualityRule(name="Search", research_agent="Find it."),),
        )


def test_the_source_kinds_are_stated_once_in_the_first_block_that_needs_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def policy(heading: str, *, step: RuleStep) -> GenericPolicy:
        return GenericPolicy(
            headings={step: (heading, f"{heading} intro.")},
            rules=(QualityRule(name=heading, **{step.value: f"{heading} part."}),),
            needs_source_kinds=True,
        )

    monkeypatch.setattr(
        research_prompts,
        "GENERIC_POLICIES",
        (
            # No part for the report writer, so it adds no block and states nothing there.
            policy("Research only", step=RuleStep.RESEARCH_AGENT),
            policy("First", step=RuleStep.REPORT_WRITER),
            policy("Second", step=RuleStep.REPORT_WRITER),
        ),
    )
    statement = render_source_kinds(BOTH_SOURCE_KINDS)
    block = render_generic_rules(
        RuleStep.REPORT_WRITER, source_kinds=BOTH_SOURCE_KINDS, glossary=False
    )
    assert block.count(statement) == 1
    assert block.index("First intro.") < block.index(statement) < block.index("## Second")


def test_a_rule_whose_step_has_no_heading_fails_when_the_policy_is_defined() -> None:
    with pytest.raises(ValueError, match="no research_agent heading"):
        GenericPolicy(
            headings={RuleStep.REPORT_WRITER: ("Writing", "Write so.")},
            rules=(QualityRule(name="Both", report_writer="Do it.", research_agent="Find it."),),
        )


def test_the_four_prompts_take_the_generic_rules_through_one_placeholder() -> None:
    for prompt in (RESEARCH_AGENT_SYSTEM_PROMPT, RESEARCH_REVIEW_SYSTEM_PROMPT):
        assert "{generic_rules}{client_rules}" in prompt
    assert "## Faithful relay\n" in _writer_prompt()
    assert "## Faithful-relay checks\n" in _review_prompt()


# --- The rules and the prompt text around them ---


def test_report_review_gets_no_part_of_no_distortion() -> None:
    assert "### No distortion" not in _review_prompt()
    assert "### No distortion" in _writer_prompt()


def test_no_prompt_allows_the_reports_own_inference() -> None:
    prompts = [_writer_prompt(), _review_prompt(), RESEARCH_REVIEW_SYSTEM_PROMPT]
    for prompt in prompts:
        text = _words(prompt)
        assert "own synthesis/inference" not in text
        assert "when a statement is your own inference" not in text
        assert "not flagged as the report's own inference" not in text


def test_research_review_says_nobody_calculates() -> None:
    text = _words(RESEARCH_REVIEW_SYSTEM_PROMPT)
    assert "Nobody calculates, not even the report writer, so never ask for a calculation" in text
    assert "a note or a calculation — the report writer does those" not in text


def test_the_writer_outrank_list_carries_the_faithful_relay_prohibitions() -> None:
    text = _words(_writer_prompt())
    assert (
        'the "No calculations" rule, the rules that exclude content, these three source-selection'
        " rules" in text
        and "these two faithful-relay rules: infer nothing, and keep every figure as its source"
        in text
    )
    assert 'does not override the "No calculations" rule or those two faithful-relay rules' in text
    assert "is a statement about the evidence, not an explanation of a declined request" in text


def test_the_writer_names_a_publication_series_in_words() -> None:
    assert "Such a fact names the publication series as its source in words." in _words(
        _writer_prompt()
    )


def test_the_research_agent_is_told_why_a_search_summary_is_not_evidence() -> None:
    text = _words(RESEARCH_AGENT_SYSTEM_PROMPT)
    assert "can change, distort or invent a value, a sum or a characterisation" in text
    assert "every figure comes from a page read with `get_pages`" in text
    assert "`retrieve_text_chunks` returns the documents' own text, word for word" in text


def test_the_restated_query_keeps_formatting_requests() -> None:
    assert "Keep the user's formatting requests in it, such as rounding figures" in _words(
        PREP_AGENT_SYSTEM
    )


def test_the_default_sections_ask_for_no_inference() -> None:
    descriptions = " ".join(section.description for section in DEFAULT_REPORT_STRUCTURE)
    assert "what follows from" not in descriptions
    assert "bottom line" not in descriptions


def test_source_selection_points_a_computed_figure_at_no_calculations() -> None:
    other_sources = next(r for r in SOURCE_SELECTION_RULES if r.name.startswith("Other sources"))
    assert 'this check does not cover it, and the check "No calculations" does' in _words(
        other_sources.report_review_blind or ""
    )


# --- The grounded review: its prompt and its messages ---


def _check_prompt(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "today_date": "2026-10-02",
        "data_sources": "Datasets:\n[]",
        "source_kinds": BOTH_SOURCE_KINDS,
        "glossary": False,
        "client_rules": [],
    }
    return render_grounded_review_prompt(**(kwargs | overrides))


def test_the_check_carries_the_terms_and_the_writer_parts() -> None:
    prompt = _check_prompt()
    assert SOURCE_SELECTION_TERMS in prompt
    assert render_rules(SOURCE_SELECTION_RULES, step=RuleStep.REPORT_WRITER) in prompt
    assert render_rules(FAITHFUL_RELAY_RULES, step=RuleStep.REPORT_WRITER) in prompt
    assert prompt.index("## Rules, judged against the findings") < prompt.index("### Terms")
    assert prompt.index("### Terms") < prompt.index("### Faithful-relay terms")
    assert "<data_sources>\nDatasets:\n[]\n</data_sources>" in prompt


def test_the_check_and_the_writer_share_the_no_calculations_rule() -> None:
    prompt = _check_prompt()
    assert f"## No calculations\n\n{NO_CALCULATIONS_WRITER_RULE}" in prompt
    assert f"## No calculations\n\n{NO_CALCULATIONS_WRITER_RULE}" in _writer_prompt()
    # The rule follows every policy block, so it never reads as part of the last one.
    assert prompt.index("## Language and style, judged") < prompt.index("## No calculations")


def test_the_check_carries_no_blind_part() -> None:
    prompt = _check_prompt()
    for rule in SOURCE_SELECTION_RULES + FAITHFUL_RELAY_RULES:
        blind_part = rule.part(RuleStep.REPORT_REVIEW_BLIND)
        if blind_part:
            assert blind_part not in prompt
    assert "<client_rules>" not in prompt
    assert "Glossary terminology" not in prompt
    assert "**Section content.**" not in prompt
    assert "## Removal checks" not in prompt


def test_the_check_carries_the_grounded_parts_and_the_client_grounded_parts() -> None:
    client_rule = QualityRule(name="Units", report_review_grounded="Check the units.")
    blind_rule = QualityRule(name="Dates", report_review_blind="Check the dates.")
    prompt = _check_prompt(client_rules=[client_rule, blind_rule])
    assert "### Names, not codes\n\nA codelist code or a dataset id outside a citation" in prompt
    assert "### Accurate and consistent terms\n\nThese are violations:" in prompt
    assert "### Verbatim names\n\nA verbatim name is" in prompt
    assert "<client_rules>\n### Units\n\nCheck the units.\n</client_rules>" in prompt
    assert "Check the dates." not in prompt
    assert prompt.index("## No calculations") < prompt.index("## Client-specific checks")


def test_the_check_leaves_same_meaning_terms_to_the_channels_rules() -> None:
    text = _words(_check_prompt())
    assert "which of two terms with the same meaning the report uses for a concept" in text
    assert "When the findings hold such a value and the draft leaves it out, report it" in text
    assert "you are not shown" not in text


def test_the_answer_example_parses_into_two_items() -> None:
    prompt = _check_prompt()
    example = prompt[prompt.index("1. No inference:") : prompt.index("\n\nIf the draft breaks")]
    items = parse_review_items(example)
    assert len(items) == 2
    assert items[0].startswith("No inference:")
    assert items[1].startswith("Names, not codes:")


def test_the_checks_messages_and_their_roles() -> None:
    transcript = [HumanMessage(content="seed"), AIMessage(content="found")]
    messages = grounded_review_messages(
        transcript=transcript, instructions="the rules", request="the draft"
    )
    assert [type(m) for m in messages] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        SystemMessage,
        SystemMessage,
    ]
    assert messages[0].content == GROUNDED_REVIEW_SYSTEM_MESSAGE
    assert "__openai_role__" not in messages[0].additional_kwargs
    assert messages[1:3] == transcript
    assert [m.content for m in messages[3:]] == ["the rules", "the draft"]
    # Plain system messages: a trailing user message would end the cacheable prompt.
    assert all(
        isinstance(m, SystemMessage) and "__openai_role__" not in m.additional_kwargs
        for m in messages[3:]
    )


@pytest.mark.parametrize(
    ("answer", "items"),
    [
        ("No violations.", []),
        ("  no violations  ", []),
        ("1. A figure.\n2. A forecast.", ["A figure.", "A forecast."]),
        ("1) A figure\n   quoted here.\n\n2. Another.", ["A figure\n    quoted here.", "Another."]),
        ("No violations of the other rules.\n1. A figure.", ["A figure."]),
        ("The draft states 44% without a source.", ["The draft states 44% without a source."]),
        ("`No violations.`", []),
        ("**No violations.**", []),
        ("No violations;", []),
        (
            "1. A figure.\n   1. its first passage\n   2. its second passage",
            ["A figure.\n    1. its first passage\n    2. its second passage"],
        ),
        (
            "1. A forecast stated for\n2024. as observed.\n2. Another.",
            [
                "A forecast stated for\n    2024. as observed.",
                "Another.",
            ],
        ),
    ],
)
def test_parse_review_items(answer: str, items: list[str]) -> None:
    assert parse_review_items(answer) == items


def test_an_empty_answer_is_not_an_approval() -> None:
    with pytest.raises(nodes.EmptyReviewAnswerError):
        parse_review_items("  \n")


# --- The grounded review in the report-review node ---


class _Structured:
    def __init__(self, model: _Model) -> None:
        self._model = model

    def with_retry(self, **kwargs: Any) -> _Structured:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        if self._model.blind_error is not None:
            raise self._model.blind_error
        return {
            "parsed": ReportReview(report_violations=self._model.blind_violations),
            "raw": AIMessage(content=""),
            "parsing_error": None,
        }


class _Model:
    """Serves the blind review (structured) and the grounded review (plain `ainvoke`)."""

    def __init__(
        self,
        *,
        blind_violations: list[str],
        grounded_answer: str,
        blind_error: Exception | None = None,
        grounded_error: Exception | None = None,
    ) -> None:
        self.blind_violations = blind_violations
        self.grounded_answer = grounded_answer
        self.blind_error = blind_error
        self.grounded_error = grounded_error
        self.grounded_messages: list[BaseMessage] = []

    def with_structured_output(self, schema: Any, include_raw: bool = False) -> _Structured:
        return _Structured(self)

    def with_retry(self, **kwargs: Any) -> _Model:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.grounded_messages = list(messages)
        if self.grounded_error is not None:
            raise self.grounded_error
        return AIMessage(
            content=self.grounded_answer,
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "input_token_details": {"cache_read": 80},
            },
        )


def _transcript() -> list[BaseMessage]:
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    return [
        HumanMessage(content="seed"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "update_status", "args": {"status": "Reading"}, "id": "s1"},
                {"name": "get_pages", "args": {"pages": [1]}, "id": "p1"},
            ],
        ),
        nodes.ToolMessage(content="status set", tool_call_id="s1"),
        nodes.ToolMessage(content=[{"type": "text", "text": "page 1"}, image], tool_call_id="p1"),
    ]


# A draft that satisfies the app-checked rules, so the outcome holds only the two calls' items.
_DRAFT = "\n\n".join(f"## {section.name}\n\nText." for section in DEFAULT_REPORT_STRUCTURE)


async def _review(
    monkeypatch: pytest.MonkeyPatch, model: _Model, *, draft: str = _DRAFT
) -> ReportReviewOutcome:
    monkeypatch.setattr(nodes, "get_chat_model", lambda model_config: model)
    outcomes: list[ReportReviewOutcome] = []
    node = nodes.make_report_review_node(
        source_kinds=BOTH_SOURCE_KINDS,
        today_date="2026-10-02",
        sections=DEFAULT_REPORT_STRUCTURE,
        max_words=2750,
        references_name="References",
        lookups=no_lookups(),
        data_sources="Datasets:\n[]",
        glossary=None,
        glossary_fetch_listed_terms=False,
        emit_result_stage=outcomes.append,
        emit_activity=lambda _t: None,
        client_rules=[QualityRule(name="Client rule", report_writer="Write the client's way.")],
    )
    state = {
        "messages": _transcript(),
        "original_query": "q",
        "plans": [["step"]],
        "research_iteration": 1,
        "report": draft,
        "report_version": 1,
    }
    await node(state)  # type: ignore[arg-type]
    (outcome,) = outcomes
    return outcome


async def test_the_check_sees_the_writers_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model(blind_violations=[], grounded_answer="No violations.")
    await _review(monkeypatch, model)
    messages = model.grounded_messages
    assert messages[0].content == GROUNDED_REVIEW_SYSTEM_MESSAGE
    assert messages[1:-2] == nodes._strip_status_calls(_transcript())
    page = messages[-3]
    assert isinstance(page.content, list) and page.content[1]["type"] == "image_url"
    assert "status set" not in [m.content for m in messages]
    instructions, request = messages[-2], messages[-1]
    assert "## Faithful relay, judged against the findings" in str(instructions.content)
    # The client rules' writer parts reach the grounded review as context, not as checks.
    assert (
        "<client_writer_rules>\n### Client rule\n\nWrite the client's way.\n</client_writer_rules>"
        in str(instructions.content)
    )
    assert f"<draft>\n{_DRAFT}\n</draft>" in str(request.content)


async def test_the_checks_items_follow_the_review_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model(
        blind_violations=["Review item."], grounded_answer="1. Relay one.\n2. Relay two."
    )
    outcome = await _review(monkeypatch, model)
    assert outcome.violations == ["Review item.", "Relay one.", "Relay two."]
    assert outcome.blind_review_error is None and outcome.grounded_review_error is None
    assert outcome.revision_instruction is not None


async def test_the_check_alone_forces_a_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model(blind_violations=[], grounded_answer="1. A figure no page gives.")
    outcome = await _review(monkeypatch, model)
    assert outcome.violations[-1] == "A figure no page gives."
    assert outcome.revision_instruction is not None


async def test_a_clean_check_adds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model(blind_violations=[], grounded_answer="No violations.")
    outcome = await _review(monkeypatch, model)
    assert outcome.violations == []
    assert outcome.revision_instruction is None


async def test_a_failed_check_leaves_the_review_standing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    model = _Model(
        blind_violations=["Review item."], grounded_answer="", grounded_error=RuntimeError("down")
    )
    with caplog.at_level(logging.INFO):
        outcome = await _review(monkeypatch, model)
    assert outcome.violations[-1] == "Review item."
    assert outcome.grounded_review_error == "RuntimeError"
    assert outcome.blind_review_error is None
    assert any(
        r.levelno == logging.WARNING and "Grounded review failed" in r.getMessage()
        for r in caplog.records
    )


async def test_an_empty_check_answer_is_a_failed_check(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model(blind_violations=[], grounded_answer="")
    outcome = await _review(monkeypatch, model)
    assert outcome.grounded_review_error == "EmptyReviewAnswerError"
    assert outcome.violations == []


async def test_a_failed_check_with_an_approving_review_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Model(blind_violations=[], grounded_answer="", grounded_error=RuntimeError("down"))
    outcome = await _review(monkeypatch, model)
    assert outcome.revision_instruction is None
    assert outcome.grounded_review_error == "RuntimeError"


async def test_a_failed_review_call_leaves_the_checks_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Model(
        blind_violations=[], grounded_answer="1. Relay one.", blind_error=RuntimeError("down")
    )
    outcome = await _review(monkeypatch, model)
    assert outcome.blind_review_error == "RuntimeError"
    assert outcome.violations[-1] == "Relay one."
    assert outcome.revision_instruction is not None


async def test_the_grounded_reviews_record_carries_counts_and_no_item_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    model = _Model(blind_violations=[], grounded_answer="1. The secret figure 44% is unsourced.")
    with caplog.at_level(logging.INFO):
        await _review(monkeypatch, model)
    (record,) = [r for r in caplog.records if r.getMessage().startswith("Report grounded-reviewed")]
    message = record.getMessage()
    assert "draft=1" in message and "items=1" in message and "error=None" in message
    assert "cache_read:80" in message
    assert all("secret figure" not in r.getMessage() for r in caplog.records)


async def test_each_review_logs_its_own_record_and_the_node_its_summary(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    model = _Model(blind_violations=["Blind item."], grounded_answer="1. Grounded one.")
    with caplog.at_level(logging.INFO):
        await _review(monkeypatch, model)
    messages = [r.getMessage() for r in caplog.records]
    (blind,) = [m for m in messages if m.startswith("Report blind-reviewed")]
    (grounded,) = [m for m in messages if m.startswith("Report grounded-reviewed")]
    (summary,) = [m for m in messages if m.startswith("Report reviewed")]
    assert "items=1" in blind and "messages=2" in blind and "tokens=" in blind
    assert "items=1" in grounded and "tokens=" in grounded
    assert "violations=2" in summary and "outcome=revise" in summary
    # The summary describes the node, not a call: each call's own record carries these.
    assert "messages=" not in summary and "tokens=" not in summary and "error=" not in summary


def test_both_calls_receive_the_glossary_forms() -> None:
    writer = _words(_writer_prompt(glossary=True))
    review = _words(
        render_blind_review_system_prompt(
            source_kinds=BOTH_SOURCE_KINDS,
            today_date="d",
            data_sources="Datasets:\n[]",
            glossary=True,
            glossary_check=True,
            glossary_tool_results=[],
            client_rules=[],
        )
    )
    for sentence in (
        "may be written as any one of those names; the whole slash form is not required",
        "its first use is written as the full form followed by the abbreviation in parentheses",
        "In mid-sentence, a glossary term's first letter may be written in lower case.",
    ):
        assert sentence in writer
        assert sentence in review
