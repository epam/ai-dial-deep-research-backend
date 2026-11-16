## MODIFIED Requirements

### Requirement: Rule 1 — research searches under both phrasings of a glossary term

The rule is named "Glossary terms". The writer's and the blind review's glossary rule, owned by
**report-composition**, has the same name on purpose. No prompt carries both rules: the research
agent receives only this rule, and the writer and the blind review receive only the rule of
**report-composition**.

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

#### Scenario: The research agent's prompt names the rule

- **WHEN** the research agent's prompt is rendered on a channel that configures a glossary
- **THEN** its terminology block SHALL carry the rule under the name "Glossary terms"
