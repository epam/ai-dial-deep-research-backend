"""The fixed report the annotations spike replies with, and its citation offsets.

The report is authored with inline `[[cN]]` markers placed right after each cited sentence.
`build_report` strips them and reports where each one sat, so the offsets can never drift from
the wording: editing a sentence moves its marker with it.

DIAL Chat injects a citation pill *after* the character at `target.selector.end`, so a marker's
offset is the index of the last character before it.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# Markers are stripped before the text is sent, so their syntax only has to be unambiguous
# against the report's own markdown.
_MARKER_PATTERN = re.compile(r"\[\[(c\d+)\]\]")

_REPORT_SOURCE = """\
## Overview

Two lines of work ask the same question from opposite ends: how much of a model's competence
should be spent before it answers, and how much while it answers.

## When planning pays off

Planning is not uniformly useful. It earns its cost on tasks whose steps depend on each other,
and is close to wasted on tasks that decompose cleanly.[[c1]] The interesting cases sit between
those extremes, where the decision of whether to plan is itself the hard part.

An agent that decides per task, rather than planning always or never, keeps most of the benefit
at a fraction of the cost.[[c2]]

## Spending compute at answer time

Test-time compute is the other lever. Allocating more of it to a smaller model can beat a much
larger model given the same total budget, provided the allocation adapts to how hard the prompt
is.[[c3]] The gain disappears when the budget is spread uniformly, which is why the allocation
policy matters more than the raw amount.[[c4]]

## Taken together

Both results point the same way: the decision of where to spend effort is worth more than the
effort itself. Deciding when to plan is the training-time version of that question, and deciding
how long to think is the inference-time version.[[c5]]
"""


class ReportWithOffsets(BaseModel):
    """The report as sent, plus the character offset each citation marker left behind."""

    text: str
    # marker id -> index of the last character before the marker sat
    offsets: dict[str, int]


def build_report() -> ReportWithOffsets:
    """Strip the `[[cN]]` markers and record where each one sat.

    Raises:
        ValueError: if a marker id repeats, which would make its offset ambiguous, or if a
            marker sits at the very start of the text, where there is no preceding character
            to anchor a pill to.
    """
    parts: list[str] = []
    offsets: dict[str, int] = {}
    clean_length = 0
    cursor = 0

    for match in _MARKER_PATTERN.finditer(_REPORT_SOURCE):
        marker_id = match.group(1)
        if marker_id in offsets:
            raise ValueError(f"duplicate citation marker {marker_id!r} in the spike report")

        parts.append(_REPORT_SOURCE[cursor : match.start()])
        clean_length += match.start() - cursor
        if clean_length == 0:
            raise ValueError(f"citation marker {marker_id!r} has no text before it")

        offsets[marker_id] = clean_length - 1
        cursor = match.end()

    parts.append(_REPORT_SOURCE[cursor:])
    return ReportWithOffsets(text="".join(parts), offsets=offsets)
