## Context

Each research step's system prompt is rendered from a constant in `app/research/prompts.py`, and
the generic source-selection rules are `QualityRule` bundles in `app/research/source_selection.py`
that are rendered under a "Source selection" heading. Research review's prompt says that research
agent never writes "a summary, a comparison, a note or a calculation — the report writer does those
from the findings", which tells the model that calculating is the writer's job. The writer may keep
an uncited sentence flagged as its own synthesis, which a computed figure could use as a way in.

The planned faithful-relay change adds a group of generic rules beside source selection, "No
calculations" among them, and reworks how generic rules are rendered.

## Goals / Non-Goals

**Goals:**

- A change small enough to ship on its own, off `development`, without the faithful-relay work.
- Each step is told only what it can act on: the preparation agent writes plan items, the research
  agent retrieves, research review judges coverage, the writer presents, report review judges the
  draft alone.

**Non-Goals:**

- Telling the user during preparation that computed figures will not be given. The plan item
  already says what research will retrieve.
- A Python check for calculations in the draft. Whether a number is computed is not decidable from
  the text, so report review judges it.
- Saying how to round. Rounding is exempted from the rule so that a dataset's raw precision never
  reaches the report; the precision to round to belongs to the faithful-relay work.

## Decisions

**Plain prompt text, not a `QualityRule`.** A `QualityRule` would keep the four research-side parts
in one definition, but the generic `QualityRule`s render under the "Source selection" heading,
where a calculation rule does not belong, and a second heading for generic rules is the rendering
rework the faithful-relay work already makes. Writing the parts straight into the four prompts
keeps this change independent; when the faithful-relay work lands, its `QualityRule` replaces
these passages.

**One shared definition of a calculation.** The definition, its three exemptions and its
precedence over section descriptions and client rules are one constant, `CALCULATION_DEFINITION`,
from which both the writer's section and report review's check 7 are built, as
`GLOSSARY_TERMINOLOGY_RULE` is for the glossary. An exemption written into one prompt only would
have the reviewer flag what the writer was told is allowed.

**The highest priority, stated in two places.** The client-rules block tells the model to follow a
client rule where it is more specific than a rule above it, and section descriptions are rules that
outrank the request. The rule says it has the highest priority of all the rules where it is stated:
in the shared definition for the writer and report review, and in the research agent's and research
review's own sentences. The client-rules block also names it as its one exception, because that
block is where a model decides between a client rule and a generic one, and in the writer's prompt
the block comes before the rule's own section.

**A section of its own in the writer's prompt, beside "Never include".** The rule needs a
definition of what counts as a calculation, three allowed exceptions and a fallback for a requested
computed figure, which is too much for the "outrank" paragraph. That paragraph only names the rule.

**Report review's check is numbered 7, and the glossary check moves to 8.** The glossary check is
appended only on channels with a glossary, so it stays last and the fixed checks keep consecutive
numbers on every channel.

**The research-agent part sits in "Research strategy".** That list already tells the agent how to
decompose plan items into lookups, which is where a request for a computed figure is turned into a
search for a stated figure plus its inputs.

## Risks / Trade-offs

- [The writer may still compute when a section description or the question insists] → the rule is
  in the "outrank" list, and report review checks the draft, so a computed figure costs a revision.
- [Report review may flag a figure a source does give] → the check exempts a number that carries its
  own citation and is not presented as computed.
- [Merge conflict with the faithful-relay work] → both edit the same research-review sentence and
  "outrank" paragraph; whichever lands second keeps the faithful-relay `QualityRule` and drops the
  plain-text passages that duplicate it, keeping the preparation agent's part, which the
  faithful-relay work does not have.
