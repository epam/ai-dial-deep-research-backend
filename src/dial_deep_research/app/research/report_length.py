"""Reading a report draft's Markdown: its section headings, and how long it is.

Two jobs that share one definition of "this line is a section heading" (`##` and its text), so
the rule that checks the headings and the count that skips the references section can never
disagree about what they are looking at.

The length the ceiling bounds is layered on `count_words`: it leaves out the parts whose size the
writer does not really choose — the inline citations, and the references section where the
configured structure declares one. What remains is the report's prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import NamedTuple

from dial_deep_research.app_properties import ReportSection, references_section
from dial_deep_research.utils.content import count_words

# The two inline citation forms the report prompt defines: `[doc 150, page 3]` and
# `[dataset IMF:WEO]`. Case- and spacing-tolerant because a model's output is not byte-exact, and
# bounded to a single line carrying no nested bracket, so ordinary Markdown is left alone. The
# spaces before a citation go with it, so `2.1% [doc 150, page 3].` leaves `2.1%.` — one word —
# rather than a stray `.` token of its own. One collision is accepted: a Markdown link written
# `[dataset overview](url)` has a matching label and loses its two words from the count. A
# Markdown parser is not worth it for a budget this approximate.
_CITATION_RE = re.compile(r"[ \t]*\[\s*(?:doc|dataset)\b[^\]\n]*\]", re.IGNORECASE)

# Any Markdown ATX heading, with its level in group 1 and its text in group 2. Sections are the
# level-two ones; the rest are the sub-headings a section may carry.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

SECTION_HEADING_LEVEL = 2

# The hashes a section heading starts with, for the places that render or quote one.
SECTION_HEADING_PREFIX = "#" * SECTION_HEADING_LEVEL

# Leading `1.` / `1)` ordinals, which a writer may add to a heading the configuration names plain.
_ORDINAL_RE = re.compile(r"^\d+[.)]\s*")


def strip_inline_citations(text: str) -> str:
    """Remove the inline `[doc …]` and `[dataset …]` citations from report text."""
    return _CITATION_RE.sub("", text)


class Heading(NamedTuple):
    """One Markdown heading of a draft: its level and its text, as the draft wrote it."""

    level: int
    text: str


def iter_headings(draft: str) -> Iterator[Heading]:
    """Yield the draft's Markdown headings in order."""
    for line in draft.splitlines():
        match = _HEADING_RE.match(line)
        if match is not None:
            yield Heading(level=len(match.group(1)), text=match.group(2).strip())


def count_report_words(draft: str, *, sections: Sequence[ReportSection]) -> int:
    """The report length the word ceiling bounds.

    The one definition, used wherever a report length is stated — the revision instruction, the
    over-ceiling gate, the review stage, the log records — so those can never disagree. Markdown
    syntax inside the counted text still scores as words, as `count_words` describes.
    """
    return count_words(strip_inline_citations(_drop_references_section(draft, sections=sections)))


def _drop_references_section(draft: str, *, sections: Sequence[ReportSection]) -> str:
    """Return the draft up to its references-section heading, when it has one.

    Three conditions, all required, and each failing one leaves the draft whole:

    1. the configured structure declares a references section (its last one);
    2. the draft carries a `##` heading — the level every section must use — whose text is that
       section's configured name;
    3. everything from that heading to the end of the draft is the section's body.

    A draft that renamed the section, left it out, or wrote it at another heading level keeps
    every word: each of those is a structure violation report-review is about to reject, and a
    violation must not also earn length budget.
    """
    section = references_section(sections)
    if section is None:
        return draft
    wanted = normalize_heading(section.name)

    lines = draft.splitlines()
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match is None or len(match.group(1)) != SECTION_HEADING_LEVEL:
            continue
        if normalize_heading(match.group(2)) == wanted:
            return "\n".join(lines[:i])
    return draft


def normalize_heading(text: str) -> str:
    """Reduce a heading to what can be compared with a configured section name.

    Decoration a writer may add around the name — bold markers, an ordinal, a trailing colon — is
    dropped, so only a genuinely different name fails to match here. The structure rule is stricter
    and reports that decoration as a violation; being lenient here keeps a decorated heading from
    also costing the draft its length exemption.
    """
    text = _ORDINAL_RE.sub("", text.strip().strip("*_").strip())
    return text.strip().rstrip(":").strip().casefold()
