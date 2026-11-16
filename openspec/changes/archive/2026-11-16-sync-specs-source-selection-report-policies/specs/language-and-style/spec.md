## RENAMED Requirements

- FROM: `### Requirement: Rule 3 — codelist values and datasets are named by their names`
- TO: `### Requirement: Rule 3 — codelist values are named by their names`

## MODIFIED Requirements

### Requirement: The language-and-style rules are a generic policy for the report steps

The language-and-style rules SHALL be generic quality rules (see **source-selection**) with parts
for the report writer, the blind review and the grounded review only, rendered as a block of their
own in those steps' prompts. The research agent's and research review's prompts SHALL carry no part
of them. The blind review's block SHALL say that its checks are rules, not wording preferences, so
that its instruction never to ask for wording it would prefer does not cancel them.

A **verbatim name** is a publication title, a dataset or series name, the name of an organisation,
or a quotation from a source, and, on a channel that configures a glossary, a glossary term. The
report writes a verbatim name as its source does, and no rule of this policy applies inside it,
except the app's emoji check, which applies everywhere. The definition SHALL be the policy's
terms (see **source-selection**), so the writer, the blind review and the grounded review all
receive it. The sentence that a glossary term is a verbatim name SHALL be a glossary-only rule for
the writer and the blind review. It SHALL say that a glossary term is written in one of the forms
that the rule "Glossary terms" allows (see **report-composition**), such as a lower-case first
letter in mid-sentence. On a channel without a glossary, no part of this policy SHALL
mention a glossary.

#### Scenario: Only the report steps receive the rules

- **WHEN** the prompts of a research turn are rendered
- **THEN** the writer's, the blind review's and the grounded review's prompts SHALL carry the
  language-and-style block, and the research agent's and research review's SHALL NOT

#### Scenario: The grounded review does not report a code inside a quoted title

- **WHEN** a draft quotes a publication title that contains a code
- **THEN** the grounded review's instructions SHALL have defined a publication title as a verbatim
  name, to which "Codelist values by name" does not apply

#### Scenario: A glossary term is a verbatim name on a glossary channel only

- **WHEN** the writer's prompt is rendered on a channel that configures a glossary, and again on
  one that does not
- **THEN** the first SHALL say that a glossary term is a verbatim name, and the second SHALL NOT
  mention a glossary in its language-and-style block

### Requirement: Rule 1 — the register is neutral

The rule is named "Neutral register". The report SHALL describe what the sources say in precise,
neutral terms, and SHALL use no informal, persuasive, promotional, dramatising or speculative
wording.

- **Report writer:** describes what the sources say in precise, neutral terms; uses no informal
  wording and no wording that sells, persuades or dramatises, such as "remarkable",
  "game-changing" or "a must"; does not speculate. A forecast that the writer names as a forecast,
  and a source's own hedging such as "the publication expects", are correct wording, not
  speculation.
- **Blind review:** informal, persuasive, promotional, dramatising or speculative wording is a
  violation, and the violation names the passage. A forecast that the draft names as a forecast,
  and a source's own hedging such as "the publication expects", are correct wording, not
  speculation.

#### Scenario: Promotional wording is sent back

- **WHEN** a draft calls a market's growth "a remarkable, game-changing surge"
- **THEN** the blind review SHALL report the passage as a violation

#### Scenario: A named forecast is not speculation

- **WHEN** a draft says "the publication forecasts growth of 2% in 2026", citing it
- **THEN** the blind review SHALL NOT report it under this rule

### Requirement: Rule 3 — codelist values are named by their names

The rule is named "Codelist values by name". The report SHALL refer to a codelist value, such as a
country or an indicator, by its name, never by its code. A code SHALL NOT stand beside its name
either. The dataset tools return codelist codes and dataset ids, and this is where codes reach a
report. Where the catalogue or a tool reports no name, the app's own label falls back to the id or
the code. That fallback is not a violation, because the writer does not write it.

- **Report writer:** names each codelist value by its name, with examples such as "United States"
  rather than `USA`, and "Gross domestic product, constant prices, percent change" rather than
  `NGDP_RPCH`; writes no code beside a name.
- **Grounded review:** a codelist code in the draft is a violation, and so is a dataset id outside
  a citation marker. The violation names the code or the id, and gives its name from the findings
  or the data sources. The grounded review judges this rule, not the blind review, because only it
  sees the findings, which hold the name behind a code. The rule on naming a dataset in the text is
  Rule 4.

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

## ADDED Requirements

### Requirement: Rule 4 — datasets are named by their names and cited once

The rule is named "Datasets by name, cited once". It SHALL have a report-writer part and a
blind-review part. The report SHALL refer to a dataset by its name, never by its id. A dataset id
SHALL appear only inside a citation marker, which the app replaces with a pill labelled by the
dataset's name. The report SHALL cite a value from a dataset only by the data query that gave it.

- **Report writer:**
  - Refers to a dataset by its name, such as "World Economic Outlook", not by its id, such as
    `IMF:WEO(1.0.0)`. A dataset id appears only inside a citation marker.
  - Names a dataset in the text only when the reader needs its name. Two examples: the query asks
    which datasets cover a topic; or one sentence gives values from two or more sources, so the
    source-selection rule "Every current value, with its own source" asks for the source of each
    value. In other cases, the writer writes "the dataset" and lets the citation identify it.
  - Cites a value from a dataset only with the `[data_query <id>]` marker of its query. The pill of
    that marker names the dataset. The writer adds no `[dataset <urn>]` marker to the same
    statement.
  - Uses `[dataset <urn>]` only to cite a general statement about the dataset, or about its series,
    that no data query supports. Examples: when the dataset was last updated, which periods the
    dataset as a whole covers, or what the dataset gives for each part in which its series differs
    from a requested fact.
  - Cites the periods that one series covers with the `[data_query <id>]` marker of the query that
    gave them. When no data query gave them, for example when an availability query showed them,
    the writer cites the dataset.
  - Names the dataset that a statement comes from in plain text, without a marker. The prompt
    shows a right example and a wrong one, in which a `[dataset <urn>]` marker is the subject of
    the sentence.
  - Puts each citation marker after the statement that it supports.
- **Blind review:** a figure that has no citation to a publication or a `[data_query <id>]` marker
  is a violation. A `[dataset <urn>]` marker alone does not cite a figure.

#### Scenario: A dataset value carries only its query marker

- **WHEN** a draft states that inflation in the United States is 2%, cited
  `[data_query dq_0123abcd45] [dataset IMF:WEO(1.0.0)]`
- **THEN** the writer's part SHALL have asked for the `[data_query dq_0123abcd45]` marker alone

#### Scenario: A figure cited only by a dataset marker is sent back

- **WHEN** a draft states a growth rate and cites it only as `[dataset IMF:WEO(1.0.0)]`
- **THEN** the blind review SHALL report it as a violation

#### Scenario: A marker is not the subject of a sentence

- **WHEN** a draft writes "[dataset IMF:WEO(1.0.0)] reports inflation in the United States at 2%
  [data_query dq_0123abcd45]"
- **THEN** the writer's part SHALL have asked for "The World Economic Outlook dataset reports
  inflation in the United States at 2% [data_query dq_0123abcd45]"

#### Scenario: A dataset's last update cites the dataset

- **WHEN** a draft states when the World Economic Outlook dataset was last updated, and no data
  query gave that date
- **THEN** the writer's part SHALL have asked to cite the statement as `[dataset IMF:WEO(1.0.0)]`

#### Scenario: The grounded review carries no part of the rule

- **WHEN** the grounded review's instructions are rendered
- **THEN** they SHALL NOT carry the rule "Datasets by name, cited once"
