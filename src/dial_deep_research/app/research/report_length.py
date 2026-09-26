"""Reading a report draft's Markdown: its section headings, and how long it is.

Two jobs that share one definition of "this line is a section heading" (`##` and its text), so the
rule that checks the headings and the count that measures the draft can never disagree about what
they are looking at.

The length the ceiling bounds is layered on `count_words`: it leaves out the one part whose size
the writer does not really choose, the inline citations. What remains is the report's prose. The
references section needs no exemption, being no part of a draft: the app writes it after the
report loop settles (see `references.py`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

from dial_deep_research.utils.content import count_words

# The three inline citation forms the report prompt defines: `[doc 150, page 3]`,
# `[dataset IMF:WEO]` and `[data_query dq_0123abcd45]`, the document keyword written either way so
# this agrees with the citation parser about what a citation is — otherwise
# `[document 150, page 3]` would become a pill and be counted as three report words. Case- and
# spacing-tolerant because a model's output is not byte-exact, and bounded to a single line carrying
# no nested bracket, so ordinary Markdown is left alone. The spaces before a citation go with it, so
# `2.1% [doc 150, page 3].` leaves `2.1%.` — one word — rather than a stray `.` token of its own.
# One collision is accepted: a Markdown link written `[dataset overview](url)` has a matching label
# and loses its two words from the count. A Markdown parser is not worth it for a budget this
# approximate.
_CITATION_RE = re.compile(
    r"[ \t]*\[\s*(?:doc(?:ument)?|dataset|data_query)\b[^\]\n]*\]", re.IGNORECASE
)

# Any Markdown ATX heading, with its level in group 1 and its text in group 2. Sections are the
# level-two ones; the rest are the sub-headings a section may carry.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# What `count_report_words` leaves out, as a noun phrase for the prompts and the review stage. A
# constant rather than something rendered per instance: the references section is written by the
# app after the loop settles, so a draft's citations are the only thing the measure can exempt.
LENGTH_EXEMPTIONS = "the inline citations"

SECTION_HEADING_LEVEL = 2

# The hashes a section heading starts with, for the places that render or quote one.
SECTION_HEADING_PREFIX = "#" * SECTION_HEADING_LEVEL


def strip_inline_citations(text: str) -> str:
    """Remove the inline `[doc …]`, `[dataset …]` and `[data_query …]` citations from text."""
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


def count_report_words(draft: str) -> int:
    """The report length the word ceiling bounds.

    The one definition, used wherever a report length is stated — the revision instruction, the
    over-ceiling gate, the review stage, the log records — so those can never disagree. Markdown
    syntax inside the counted text still scores as words, as `count_words` describes.

    Only the inline citations are left out. The references section is not: the app writes it after
    the loop settles, so no draft carries one, and a draft that writes one anyway is a structure
    violation whose words count like any other — a violation must not also earn length budget.
    """
    return count_words(strip_inline_citations(draft))
