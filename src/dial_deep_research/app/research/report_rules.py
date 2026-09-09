"""The report rules the app enforces itself, without asking a model.

Each rule owns three things that must never drift apart: the instruction the report writer is
given, the check over a finished draft, and the wording of the violation a revision acts on. They
live together in one class, so changing a rule means editing one place and the writer can never be
told something different from what the draft is judged against.

The rules are built once per turn — some from the instance's configuration (the section
structure, the word ceiling), some from nothing at all (the no-hyperlink rule) — and used at two
points: the report node renders their instructions into its system prompt, and
the report-review node runs their checks and prepends the violations to the review model's own
list. The review model is told nothing about them — it judges what needs judgment.

Only what is decidable from the draft text belongs here. Whether a section is padded with
unsupported text, whether a citation matches the source it came from, whether an annotation is a
banned rating — those need a reader, and stay with the review model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from dial_deep_research.app_properties import ReportSection

from .citations import find_hyperlinks
from .prompts import render_length_exemptions, render_report_structure
from .report_length import (
    SECTION_HEADING_LEVEL,
    SECTION_HEADING_PREFIX,
    count_report_words,
    iter_headings,
)


class ReportRule(ABC):
    """One deterministic report rule: what the writer is told, and what the draft is checked for."""

    @abstractmethod
    def writer_instruction(self) -> str:
        """The rule's section of the report writer's system prompt."""

    @abstractmethod
    def violations(self, draft: str) -> list[str]:
        """What this draft breaks, each entry naming what to change. Empty when the rule holds."""


def build_report_rules(
    *, sections: Sequence[ReportSection], max_words: int
) -> tuple[ReportRule, ...]:
    """The rules for one instance's configuration, in the order they appear in the prompt."""
    return (
        ReportStructureRule(sections=sections),
        ReportLengthRule(sections=sections, max_words=max_words),
        ReportHyperlinkRule(),
    )


def render_writer_instructions(rules: Sequence[ReportRule]) -> str:
    """The rules' instructions, for the report writer's system prompt."""
    return "\n\n".join(rule.writer_instruction() for rule in rules)


class ReportStructureRule(ReportRule):
    """Every configured section is present, named as configured, in order, as a `##` heading.

    One comparison covers every way that can fail — a missing, extra, renamed, reordered or
    decorated section, and one written at another level — because each of them changes the list of
    `##` headings the draft carries. The violation states both lists and lets the writer find the
    difference, rather than the rule enumerating which kind of mismatch it was.

    The comparison is exact, down to case and decoration, because the app parses these headings:
    the length measure finds the references section by its heading. That measure is deliberately
    lenient about the same decoration, so a `## **References**` heading is reported here without
    also costing the draft its length exemption.
    """

    def __init__(self, *, sections: Sequence[ReportSection]) -> None:
        self._sections = list(sections)

    def writer_instruction(self) -> str:
        return _STRUCTURE_INSTRUCTION.format(
            report_structure=render_report_structure(self._sections)
        )

    def violations(self, draft: str) -> list[str]:
        sections_expected = [section.name for section in self._sections]

        headings_found = list(iter_headings(draft))
        headings_found_top_level = [h for h in headings_found if h.level == SECTION_HEADING_LEVEL]
        sections_found = [h.text for h in headings_found_top_level]

        if sections_found == sections_expected:
            return []
        # The lists are rendered as lists: the brackets bound them and the quotes bound each
        # name, so a stray space or a decorated heading is visible in the message.
        return [
            f"The report must carry exactly these `{SECTION_HEADING_PREFIX}` sections, in this"
            f" order, worded exactly this way: {sections_expected}."
            f" It carries: {sections_found}."
        ]


class ReportLengthRule(ReportRule):
    """The report's measured length stays within the configured ceiling.

    The measure is `count_report_words`, so the citations and the references section are outside
    it. The check is the app's alone: an over-long draft is revised whatever the review model
    said, and a review that failed to answer at all still leaves this violation behind.
    """

    def __init__(self, *, sections: Sequence[ReportSection], max_words: int) -> None:
        self._sections = list(sections)
        self._max_words = max_words

    def writer_instruction(self) -> str:
        return _LENGTH_INSTRUCTION.format(
            max_words=self._max_words,
            length_exemptions=render_length_exemptions(self._sections),
        )

    def violations(self, draft: str) -> list[str]:
        word_count = count_report_words(draft, sections=self._sections)
        if word_count <= self._max_words:
            return []
        return [
            _LENGTH_VIOLATION.format(
                word_count=word_count,
                max_words=self._max_words,
                length_exemptions=render_length_exemptions(self._sections),
            )
        ]


class ReportHyperlinkRule(ReportRule):
    """The report references a source only by an inline citation, so it carries no hyperlink.

    A hyperlink cites something the research never retrieved, which is what the rule exists to
    prevent. Every form counts: a Markdown link or image, a reference-style link and its
    definition line, a raw HTML anchor or image tag, an autolink, and a bare URL written as
    text — which a Markdown renderer turns back into a link.

    The violation asks for the **sentence** to be rewritten rather than for the URL to be
    deleted, because only the report writer can produce a sentence that still reads well
    without it. Deletion is what the delivery step does to whatever survives to it (see
    `citations.remove_hyperlinks`), and that is a guarantee rather than a repair: this rule is
    where a link is properly fixed, while a version is still available.

    The detection is `citations.find_hyperlinks` — the same function the delivery step removes
    with, so the two can never disagree about what a hyperlink is.
    """

    def writer_instruction(self) -> str:
        return _HYPERLINK_INSTRUCTION

    def violations(self, draft: str) -> list[str]:
        return [
            _HYPERLINK_VIOLATION.format(form=_HYPERLINK_FORMS[link.kind], text=link.text)
            for link in find_hyperlinks(draft)
        ]


# How each detected form is named to the report writer. The keys are `Hyperlink.kind`.
_HYPERLINK_FORMS: dict[str, str] = {
    "link": "a Markdown link",
    "image": "a Markdown image",
    "reference_link": "a reference-style link",
    "reference_definition": "a link definition line",
    "html_anchor": "a raw HTML anchor",
    "html_image": "a raw HTML image tag",
    "autolink": "an autolink",
    "bare_url": "a bare URL",
}


_STRUCTURE_INSTRUCTION = """\
## Report structure

Write exactly these sections, in this order, copying each heading exactly as written below — same
text, same level, no bold markers and no numbering added. The text under each heading is what
belongs in that section; it tells you what to write and is never copied into the report:

<report_structure>
{report_structure}
</report_structure>

Sub-headings inside sections are allowed, at `###` or deeper. No other `##` heading appears in the
report, and the report has no title above its first section.

Write every section, including one the findings barely cover. Where the findings give a section
nothing to say, say so plainly inside that section: do not invent content to fill it, and do not
leave it out."""


_LENGTH_INSTRUCTION = """\
## Length

Keep the whole report to at most **{max_words} words** (counted as whitespace-separated words,
Markdown included). The count leaves out {length_exemptions}, so shortening those frees no room
elsewhere — write them as their own rules describe. This is a ceiling, not a target: a shorter
report that answers the question is better than a padded one. Never meet it by cutting text off —
plan the report to fit, and if you must shorten, condense and rewrite so the report always ends at
a complete sentence closing a complete section."""


_LENGTH_VIOLATION = """\
The draft is {word_count} words, over the {max_words}-word ceiling — a count that already leaves \
out {length_exemptions}. Shorten it to fit by condensing and rewriting — cut detail, tighten \
prose, merge overlapping passages. Do not truncate: every section that the draft filled stays \
present, and the report still ends at a complete sentence."""


_HYPERLINK_INSTRUCTION = """\
## No links

Reference a source only through the inline citation forms specified below. The report carries no
hyperlink of any kind:

- no Markdown link, `[text](url)`, and no Markdown image, `![alt](url)`
- no reference-style link, `[text][ref]`, and no `[ref]: url` definition line
- no autolink, `<https://example.org/page>`, and no raw HTML `<a>` or `<img>` tag
- no bare URL written out as text, which a Markdown renderer turns into a link of its own

A hyperlink points the reader at something the research never retrieved, and the report answers
from the retrieved sources alone. Where a source matters, name it in words — its title, its
publisher, its date — and cite the retrieved page inline."""


_HYPERLINK_VIOLATION = """\
The draft carries {form}: `{text}`. A report references a source only by an inline citation, so \
rewrite the sentence around it — name the source in words and cite the retrieved page inline, or \
drop the reference altogether. Deleting the URL and leaving the rest of the sentence as it stands \
is not the fix: the sentence has to read correctly without it."""
