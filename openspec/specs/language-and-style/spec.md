# language-and-style Specification

## Purpose

How the report is worded: a precise, neutral and descriptive register, no exclamation marks, emojis
or slang, and every codelist value and dataset named by its name rather than by its code or id. A
channel's own language, spelling and abbreviation rules are its client rules.

## Requirements

### Requirement: The language-and-style rules are a generic policy for the report steps

The language-and-style rules SHALL be generic quality rules (see **source-selection**) with parts
for the report writer, the blind review and the grounded review only, rendered as a block of their
own in those steps' prompts. The research agent's and research review's prompts SHALL carry no part
of them. The blind review's block SHALL say that its checks are rules, not wording preferences, so
that its instruction never to ask for wording it would prefer does not cancel them.

A **verbatim name** is a publication title, a dataset or series name, an organisation's name, or a
quotation from a source, and, on a channel that configures a glossary, a glossary term. The report
writes a verbatim name exactly as its source writes it, and no rule of this policy applies inside
it, except the app's emoji check, which applies everywhere. The definition SHALL be the policy's
terms (see **source-selection**), so the writer, the blind review and the grounded review all
receive it. The sentence that a glossary term is a verbatim name SHALL be a glossary-only rule for
the writer and the blind review, and SHALL say that a glossary term is written in one of the forms
the glossary-terminology rule allows (see **report-composition**), such as a lower-case first
letter in mid-sentence. On a channel without a glossary, no part of this policy SHALL
mention a glossary.

#### Scenario: Only the report steps receive the rules

- **WHEN** the prompts of a research turn are rendered
- **THEN** the writer's, the blind review's and the grounded review's prompts SHALL carry the
  language-and-style block, and the research agent's and research review's SHALL NOT

#### Scenario: The grounded review does not report a code inside a quoted title

- **WHEN** a draft quotes a publication title that contains a code
- **THEN** the grounded review's instructions SHALL have defined a publication title as a verbatim
  name, to which "Names, not codes" does not apply

#### Scenario: A glossary term is a verbatim name on a glossary channel only

- **WHEN** the writer's prompt is rendered on a channel that configures a glossary, and again on
  one that does not
- **THEN** the first SHALL say that a glossary term is a verbatim name, and the second SHALL NOT
  mention a glossary in its language-and-style block

### Requirement: Rule 1 — the register is neutral

The report SHALL describe what the sources say in precise, neutral terms, and SHALL use no informal,
persuasive, promotional or speculative wording.

- **Report writer:** describes what the sources say in precise, neutral terms; uses no informal
  wording and no wording that sells, persuades or dramatises, such as "remarkable",
  "game-changing" or "a must"; does not speculate.
- **Blind review:** informal, persuasive, promotional or speculative wording is a violation, and the
  violation names the passage. A forecast that the draft names as a forecast, and a source's own
  hedging such as "the publication expects", are correct wording, not speculation.

#### Scenario: Promotional wording is sent back

- **WHEN** a draft calls a market's growth "a remarkable, game-changing surge"
- **THEN** the blind review SHALL report the passage as a violation

#### Scenario: A named forecast is not speculation

- **WHEN** a draft says "the publication forecasts growth of 2% in 2026", citing it
- **THEN** the blind review SHALL NOT report it under this rule

### Requirement: Rule 2 — no exclamation marks, emojis or slang

The report SHALL contain no exclamation mark outside a verbatim name, no emoji and no slang.

- **Report writer:** writes no exclamation mark and no slang; a verbatim name keeps its own
  punctuation. The writer is also told that the report carries no emoji anywhere: not in prose,
  headings, lists or tables.
- **App check:** the app SHALL report every emoji in a draft as a deterministic violation (see
  **report-composition**).
- **Blind review:** an exclamation mark outside a verbatim name is a violation, and so is slang.

#### Scenario: An exclamation mark in a quoted title stands

- **WHEN** a draft quotes a publication whose title ends with an exclamation mark
- **THEN** the blind review SHALL NOT report that exclamation mark

#### Scenario: Slang is sent back

- **WHEN** a draft says that exports "went through the roof"
- **THEN** the blind review SHALL report the passage as a violation

### Requirement: Rule 3 — codelist values and datasets are named by their names

The report SHALL refer to a codelist value, such as a country or an indicator, by its name, never by
its code, and to a dataset by its name, never by its id. These are where codes reach a report: the
dataset tools return codelist codes and dataset ids. A code SHALL NOT stand beside its name either.
A dataset id SHALL appear only inside a citation marker, such as `[dataset IMF:WEO(1.0.0)]`, which
the app replaces with a pill labelled by the dataset's name. Where the catalogue or a tool reports
no name, the app's own label falls back to the id or the code; that fallback is not a violation,
because the writer does not write it.

- **Report writer:** names each codelist value and each dataset by its name, with examples such as
  "United States" rather than `USA` and "World Economic Outlook" rather than `IMF:WEO(1.0.0)`;
  writes no code beside a name; puts a dataset id only inside a citation marker.
- **Grounded review:** a codelist code or a dataset id outside a citation marker is a violation;
  the violation names the code or the id and gives its name from the findings or the data sources.
  The grounded review judges this rule, not the blind review, because only it sees the findings,
  which hold the name behind a code.

#### Scenario: A country code is replaced by its name

- **WHEN** a draft's table lists growth for `USA`, and the findings give the name "United States"
  for that code
- **THEN** the grounded review SHALL report it, naming the code and the name

#### Scenario: A dataset id in prose is replaced by its name

- **WHEN** a draft says "according to IMF:WEO(1.0.0), growth slowed"
- **THEN** the grounded review SHALL report it, naming the id and the dataset's name

#### Scenario: A citation marker keeps its id

- **WHEN** a draft cites a dataset as `[dataset IMF:WEO(1.0.0)]`
- **THEN** no review SHALL report the id inside the marker
