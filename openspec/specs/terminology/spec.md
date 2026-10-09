# terminology Specification

## Purpose

How the report names concepts: each technical term with the meaning its source gives it, a glossary
term only where it names exactly the same concept, one term per concept throughout, and a research
search that finds a glossary concept under either of its phrasings. The glossary-terminology rule
itself stays owned by **report-composition**.

## Requirements

### Requirement: The terminology rules are a generic policy

The terminology rules SHALL be generic quality rules (see **source-selection**), rendered as a
block of their own in the prompt of each step that has a part of them. A rule that concerns the
glossary SHALL be rendered only on a channel that configures a glossary, and on a channel without
one no part of this policy SHALL mention a glossary.

The generic rules SHALL NOT refer to client rules. A client rule that has to override a generic
rule SHALL say so in its own text.

#### Scenario: A channel without a glossary

- **WHEN** a channel configures no glossary
- **THEN** no step's prompt SHALL carry the glossary search rule, and the writer's and the grounded
  review's prompts SHALL still carry the rule on accurate and consistent terms, with no mention of a
  glossary

### Requirement: Rule 1 — research searches under both phrasings of a glossary term

On a channel that configures a glossary, when a plan item refers to a concept that a glossary term
names, the research agent SHALL search for it in two ways: by the term's name, and by a short phrase
of a few words from its definition, because a question or a source can use either one. It SHALL NOT
search with the whole definition, because a long query matches too many unrelated pages. The rule
SHALL point at the `Glossary terms:` part of the data sources and the terms the glossary tools
returned, and SHALL say nothing about whether to call a glossary tool: when to call one is the
data-sources instruction's (see **data-sources-discovery**).

#### Scenario: A question phrased by a definition

- **WHEN** the glossary defines "real GDP" as "GDP adjusted for inflation", and a plan item asks for
  GDP adjusted for inflation
- **THEN** the research agent's prompt SHALL tell it to search under "real GDP" too

#### Scenario: The glossary fetch failed

- **WHEN** the channel configures a glossary and the app's fetch of its terms failed
- **THEN** the research agent's prompt SHALL carry the glossary search rule and the instruction to
  call the list-terms tool, and no sentence of the rule SHALL tell it not to call a glossary tool

### Requirement: Rule 2 — terms are accurate and consistent

The report SHALL use each technical term with the meaning its source gives it, SHALL NOT replace a
term with a synonym that changes its meaning, and SHALL use one term for one concept in all
sections. Where two sources use different terms for one concept, the report SHALL use one of them
in all sections. A full form and the abbreviation it introduces SHALL count as one term. A glossary
term SHALL replace a source's term only when both name exactly the same concept; when that is not
sure, the source's term SHALL stay, because a substitution can change the meaning.

- **Report writer:** keeps the source's term; uses no synonym that changes the meaning, such as
  "exports" for "net exports" or "unemployment" for "the unemployment rate"; uses one term for one
  concept in all sections; uses a glossary term in place of a source's term only when both name
  exactly the same concept, and keeps the source's term when not sure. The glossary sentence is
  rendered only on a channel that configures a glossary.
- **Grounded review:** a term used with another meaning than its source gives it, a synonym that
  changes the source's meaning, and two different terms for one concept are violations; the
  violation names the term and the source's term. One source's term used for a concept that
  another source names differently, a full form with the abbreviation it introduces, and a term
  inside a verbatim name, such as a publication title or a quotation, are not violations. The
  grounded review judges this rule, because only it sees the sources, and a rule is
  judged by one review.

#### Scenario: A synonym changes the meaning

- **WHEN** a source gives a figure for net exports and the draft calls it "exports"
- **THEN** the grounded review SHALL report it, naming both terms

#### Scenario: Two sources name one concept differently

- **WHEN** one source says "jobless rate" and another "unemployment rate" for the same figure, and
  the draft uses "unemployment rate" throughout
- **THEN** the grounded review SHALL NOT report it

#### Scenario: An abbreviation introduced with its full form

- **WHEN** a draft writes "gross domestic product (GDP)" once and "GDP" afterwards
- **THEN** the grounded review SHALL NOT report two terms for one concept

#### Scenario: Two terms for one concept

- **WHEN** a draft calls the same figure "unemployment rate" in one section and "jobless rate" in
  another
- **THEN** the grounded review SHALL report the inconsistency
