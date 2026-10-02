## MODIFIED Requirements

### Requirement: A quality rule is one bundle of step instructions

A quality rule SHALL be one named bundle of up to four instructions, one for each research step:
the research agent, research review, the report writer and report review. The application's
generic rules and a channel's client rules (see **application-config-schema**) SHALL have the same
shape.

Each step's system prompt SHALL carry that step's part of every rule, each under its rule's name,
in the order the rules are defined. A rule with no part for a step SHALL add nothing to that
step's prompt, not even its name.

The parts of one rule SHALL fit together: a step SHALL NOT be asked to check or to present what
the earlier steps were not asked to produce, and no step SHALL be asked for what it cannot do.
Three constraints follow from what the steps can do:

- **A part about one kind of source applies only where the channel has it.** A channel may
  configure datasets only, or documents only. Each step's generic block SHALL state which kinds of
  source the channel has, taken from its configured servers: a document server gives it
  publications, and a dataset server gives it datasets. When the channel lacks one kind, the
  statement SHALL say that the parts about that kind do not apply. A part that concerns datasets,
  or publications, SHALL apply only where the channel has that kind, and no part SHALL require a
  retrieval from a kind of source the channel does not have. The model is told the kinds rather
  than left to infer them from the data-sources text, whose descriptions an admin writes.

- **The research agent's part only ever asks for retrievals.** The research agent can only call
  tools; it writes no notes, summaries or comparisons. A part SHALL NOT ask it to record, note,
  summarise, compare or calculate anything. Where a rule needs a fact to be on record, the part
  asks the agent to make sure a tool result in the findings carries it.
- **Research review asks only for steps the research agent can take.** Research review's prompt
  SHALL say that every next step it writes is a retrieval — which source to search, list, query or
  read, and for what — and never a summary, a comparison or a note, which the report writer does
  from the findings, nor a calculation, which nobody does (see **research-execution**, "Research
  looks for a stated figure rather than planning to compute one").

#### Scenario: A rule's part reaches only its step

- **WHEN** a rule defines a research-agent part and a report-writer part only
- **THEN** the research agent's and the report writer's system prompts SHALL each carry their
  part under the rule's name, and the research review and report review prompts SHALL carry
  neither the rule's name nor any of its text

#### Scenario: One edit changes the rule for every step

- **WHEN** the generic rule for dates is changed
- **THEN** the change SHALL be made in one definition, from which all four steps' prompts are
  rendered

#### Scenario: Research review asks for a retrieval, not a summary

- **WHEN** research review finds that two editions of a forecast were read but their difference
  was not explained
- **THEN** its next step SHALL ask for the pages or the methodology that could explain the
  difference, and SHALL NOT ask the research agent to compare or summarise the two values

#### Scenario: A channel with documents only

- **WHEN** a channel configures a document server and no dataset server
- **THEN** no step's part SHALL require a dataset query, and research review SHALL NOT report a
  missing dataset query or a missing dataset release as a gap

#### Scenario: Each step is told the channel's kinds of source

- **WHEN** a channel configures a dataset server and no document server
- **THEN** each step's generic block SHALL say that the channel has datasets and no publications,
  and that the parts about publications do not apply

### Requirement: Client rules follow the generic rules in a tagged block

A channel's client rules SHALL reach each step whose part they set, after the generic rules, in a
`<client_rules>` block. Inside the block each part SHALL appear under its rule's name. The text
around the block SHALL say that these rules come from the channel's configuration, that they add
to the rules above them, and that where a client rule is more specific than a generic rule the
client rule is followed, with one exception: the rule that nobody calculates (see
**research-execution**, "Research looks for a stated figure rather than planning to compute one",
and **report-composition**, "Reports contain no calculations") has the highest priority of all the
rules, and no client rule overrides it. The text SHALL state that exception at every step whose
prompt carries the block.

When no client rule has a part for a step, that step's prompt SHALL carry neither the block nor
the text around it.

The generic rules SHALL name no client, no client dataset, no client publication and no client
domain. What a client's sources contain SHALL be said only in that channel's client rules: whether
its datasets document their methodology or keep earlier releases, where its publications document
methodology, which metadata key carries a publication's date, and which tool lists its documents.

#### Scenario: A client rule for one step

- **WHEN** a channel configures one client rule, "Dataset methodology", with only a research-agent
  part
- **THEN** the research agent's system prompt SHALL carry a `<client_rules>` block with that part
  under "Dataset methodology", after the generic rules, and no other step's prompt SHALL carry a
  `<client_rules>` block

#### Scenario: A channel without client rules

- **WHEN** a channel configures no client rules
- **THEN** no step's prompt SHALL carry a `<client_rules>` block or the text that introduces one,
  and every step's prompt SHALL still carry its part of the generic rules

#### Scenario: A client rule asks for a calculation

- **WHEN** a channel's client rule asks the writer to give the year-on-year change of each series
- **THEN** the text around the `<client_rules>` block SHALL say that no client rule overrides the
  rule that nobody calculates, and the report SHALL NOT compute the changes
