## Why

The prompts were rewritten to follow the current Deep Research quality policies: source selection,
faithful relay, language and style, terminology and the report format. The main specs still
describe the earlier prompts. They name rules that no longer exist, give the old default report
structure, and state behaviour the prompts no longer ask for. This change records the implemented
behaviour in the specs, so that the specs again own each requirement.

## What Changes

- **Source selection has ten rules.** Two rules are new: "Every requested fact, each on its own"
  and "Supporting context and omitted content". The other eight are renamed and reordered, and
  most of them change:
  - Research no longer reads earlier editions for context, and stops looking for more sources once
    it has searched each kind of source.
  - The datasets are searched through their structures and availability queries.
  - Only the nearest matches are given when no exact match exists.
  - The writer gives each current value with its own citation and writes a stated date only when
    the answer needs it.
  - A statement that evidence is missing is made only for what the user asked for.
- **The source-selection terms are a new list.** "Requested fact" has named parts, "Supersede" is
  defined for each pair of kinds of source, and "Reasonable attempt" says nothing about a failed
  tool.
- **Faithful relay renames its rules and changes four of them.**
  - "Estimate" is no longer a term of its own. A value is a forecast when its source labels it so,
    or when the date test says so.
  - "Forecasts named as such" has no blind-review part.
  - Requested rounding is no longer an allowed change to a figure.
  - A new writer rule, "Qualifying context next to its value", takes over the writer part of the
    source-selection qualifying-context rule.
- **Language and style splits "Names, not codes".** The split gives "Codelist values by name" and
  a new rule, "Datasets by name, cited once", which cites a dataset value only by its data-query
  marker. Neutral register also forbids dramatising wording.
- **The writer's "No calculations" rule is renamed** "No calculation by research or the report",
  and the glossary rule is renamed "Glossary terms". Every spec that names a renamed rule uses the
  new name.
- **The default report structure is Overview, Key Findings and Additional context**, with Key
  Findings protected. Key Findings carries the direct answer and the table rules, and Additional
  context carries the supporting context.
- **The report writer and the plan.**
  - The report writer runs at medium reasoning effort.
  - It never shortens a draft by dropping a value.
  - It keeps sub-headings short.
  - It is told which plan is the approved one.
- **Preparation.**
  - The research plan covers each part of the query, keeps what the user asked for, and leaves
    out the report format unless the user asks for one.
  - The restated query keeps a requested unit and adds no formatting request of its own.
  - With no time preference, the defaults are the last 10 years for past values and the next 3
    years for forecasts.
  - A question about how a value was revised needs the date range of the revisions.
- **A figure no source states.** When the query names only a measure, such as an index, research
  looks for a source that states how to compute it. The report says when no source gives the
  figure or the method.
- **Research review** counts a cited page as read.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `source-selection`: the terms, the ten rules and their step parts, the prompt-agreement and
  client-rule requirements, and the eval requirement.
- `faithful-relay`: the terms, the rule names, rules 1 and 4 to 8, the new qualifying-context
  rule, the grounded review's instructions and the prompt-agreement requirement.
- `language-and-style`: the neutral-register rule, the split of the codelist and dataset rule, and
  the rule names.
- `terminology`: the name of the glossary rule.
- `prohibited-content`: the rule names it cites and the wording of the report request.
- `report-composition`: the default report structure, the report writer's rules and reasoning
  effort, the review's checks, and the rule names.
- `application-config-schema`: the default value of `default_report_structure`.
- `research-execution`: a figure computed from a named measure, the dataset marker, the plan
  label and the report call's reasoning effort in the LLM-call inputs, and the rule names.
- `clarification-and-plan-alignment`: what the plan keeps from the query, the report format in the
  plan, the formatting requests the restated query keeps, the default time spans and the date
  range of a revision question.
- `data-sources-discovery`: the name of the glossary rule, if the spec names it.

## Impact

- Specs only. The code this change describes is already in `src/dial_deep_research/app/` and
  `src/dial_deep_research/app_properties.py`, with its tests.
- No API, setting or dependency changes. A deployment that does not set
  `default_report_structure` gets the new default sections.
