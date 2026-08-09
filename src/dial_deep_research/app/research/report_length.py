"""How long a report is, for the ceiling `max_report_words` bounds.

Layered on `count_words`: the report's measure leaves out the parts whose size the writer does
not really choose — the inline citations, and the references section where the configured
structure declares one. What remains is the report's prose, which is what the ceiling is meant
to bound.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

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

# A section heading: exactly two hashes, the level the report prompt requires of every section
# and report-review checks. A sources listing written at any other level is not recognized here
# either — see `_drop_references_section`.
_SECTION_HEADING_RE = re.compile(r"^##\s+(.*)$")

# Leading `1.` / `1)` ordinals, which a writer may add to a heading the configuration names plain.
_ORDINAL_RE = re.compile(r"^\d+[.)]\s*")


def strip_inline_citations(text: str) -> str:
    """Remove the inline `[doc …]` and `[dataset …]` citations from report text."""
    return _CITATION_RE.sub("", text)


def count_report_words(draft: str, sections: Sequence[ReportSection]) -> int:
    """The report length the word ceiling bounds.

    The one definition, used wherever a report length is stated — the revision instruction, the
    over-ceiling gate, the review stage, the log records — so those can never disagree. Markdown
    syntax inside the counted text still scores as words, as `count_words` describes.
    """
    return count_words(strip_inline_citations(_drop_references_section(draft, sections)))


def _drop_references_section(draft: str, sections: Sequence[ReportSection]) -> str:
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
    wanted = _normalize_heading(section.name)

    lines = draft.splitlines()
    for i, line in enumerate(lines):
        heading = _SECTION_HEADING_RE.match(line)
        if heading is not None and _normalize_heading(heading.group(1)) == wanted:
            return "\n".join(lines[:i])
    return draft


def _normalize_heading(text: str) -> str:
    """Reduce a heading to what can be compared with a configured section name.

    Decoration a writer may add around the name — bold markers, an ordinal, a trailing colon — is
    dropped, so only a genuinely different name fails to match. The heading *level* is not
    decoration and is matched exactly, by `_SECTION_HEADING_RE`.
    """
    text = _ORDINAL_RE.sub("", text.strip().strip("*_").strip())
    return text.strip().rstrip(":").strip().casefold()
