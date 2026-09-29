## Why

Deep Research answers a question about a fact from whichever sources its first searches reach. A
forecast asked about "now" can be answered from an older edition, a dataset value can be skipped
when a publication repeats it, and two sources that disagree can be merged or one of them dropped.
Nothing tells the research agent to look for the latest edition, the previous edition, the
dataset value, the methodology or the dates, nothing lets research review ask for them, and
nothing tells the writer how to present several values for one fact.

An internal policy defines the intended behavior in eight rules. Each rule says what every
pipeline step does for it: the research agent, research review, the report writer and report
review. This change implements them. Some rules depend on what a client's sources contain, for
example whether datasets document their methodology, so the change also adds the mechanism that
gives each step client-specific rules from the channel's application properties.

## What Changes

- **A quality rule is one bundle of step instructions.** A rule has a name and up to four parts:
  the instruction for the research agent, for research review, for the report writer and for
  report review. Each step's system prompt carries its own part of every rule, under the rule's
  name; a rule with no part for a step adds nothing to that step's prompt. One rule is edited in
  one place, so its four parts cannot drift apart, and a step is never asked for what an earlier
  step was not told to produce.
- **The eight source-selection rules, and the terms they use, are the app's generic rules**,
  defined in code as such bundles.
- **A channel adds its own rules through a new optional application property,
  `prompts.client_rules`**: a list of rules of the same shape, empty by default. Each step's prompt
  carries the client rules' parts in a tagged block after the generic rules, and a client rule
  takes precedence where it is more specific. The committed `applications-template.json` does not
  change, because the property has a default.
- **Each step is told the channel's kinds of source.** A channel may configure a document server,
  a dataset server or both. Each step's generic block opens with a sentence naming the kinds the
  configured servers give the channel, and saying that the parts about a missing kind do not apply,
  so no rule asks for a retrieval the channel cannot make.
- **Research agent**: its part of rules 1 to 8: look for the latest publication edition of every
  fact, including a fact a dataset answers (a dataset's entry, fetched at the start of the turn, is
  already its latest release), retrieve every value the question asks for and the previous value
  where it gives context, retrieving the previous edition itself when a later one only quotes its
  value, query a dataset
  that holds the indicator, retrieve the methodology, look for other sources and the explanation of
  a difference, make sure the findings carry the stated date and the described period of every
  value, and look for the nearest matches when no exact match exists. A publication's stated date
  is read from the document metadata a tool returns, with the documents listed once per research,
  never from the page text and never from an edition name.
- **Research review**: new gap criteria (no search of the publications for a fact's latest value,
  even when a dataset gives it, or no check for a later edition of a publication value, where a
  listing or a search confined to one publication type is not such a check; a missing value the
  question asks for; a missing previous value of a forecast, including one the findings hold only
  as a later edition's quote; a dataset indicator never queried; a documented methodology not read;
  a value without one of its dates; a fact with no exact match and no search for its nearest
  matches) and one restriction (it asks for the explanation of a difference already found, never
  for a search for further disagreeing sources). Every text of its prompt and its output schema
  that now says plan coverage alone completes research is adjusted. Evidence that does not exist
  after a reasonable attempt is not a gap, and every next step is a retrieval the research agent
  can carry out.
- **Report writer**: its part of rules 1 to 8: the most recent exact match leads, previous values
  are added where they give context, a dataset value is always cited, methodology is given where
  it changes how a value is read, every differing value is shown with its source and a reason for
  the difference, each value states its described period, forecasts and estimates state their
  stated date as a date, and near matches are labelled with how they differ. The source-selection
  prohibitions (no averaging or merging, no described period and no stated date of a forecast or
  an estimate left out, no near match passed off as exact) outrank the request.
- **Report review**: new model-judged checks, limited to what the draft shows: a range or an
  average spanning two sources' values for the same fact, or two differing values for the same fact
  without their own citations and a reason; a value without its described period, or a forecast or estimate without its stated date;
  a near match without how it differs. A statement that the sources do not give some evidence
  satisfies a check that asks for it. The item "whether a source was the right one to use" leaves
  its "Not your job" list.
- **The two review calls reason.** Research review and report review run the default model with
  reasoning effort `medium`; without it, both applied the rules' checks unreliably in the evals.
- **The length violation asks to condense, never to drop a fact.** Its text says "cut detail"
  today, which contradicts the rule that omitting a relevant value costs more than including one.
- **The generic rules name no client.** What a channel's sources contain, such as whether its
  datasets document their methodology, is said only in the channel's application properties.

## Capabilities

### New Capabilities

- `source-selection`: how each research step finds, keeps and presents values for the same fact
  from several sources and editions. It owns the quality-rule bundle, the terms, the eight rules
  and each step's part of them, and how client rules reach the steps.

### Modified Capabilities

- `application-config-schema`: `prompts` gains the optional `client_rules` list, and the
  application properties model's `prompts` bullet points at it.
- `research-execution`: the four research calls' system prompts carry their parts of the generic
  and client rules, research review's coverage judgement admits the gaps those rules define, and
  the two review calls run with reasoning effort `medium`.
- `report-composition`: the writer and report review system prompts carry their parts of the
  rules, report review loses "whether a source was the right one to use" from what it does not
  judge, and the length violation's wording asks to condense without dropping a fact.

## Impact

- `src/dial_deep_research/app_properties.py`: the `QualityRule` model, `Prompts.client_rules`, and
  `ApplicationProperties.source_kinds`, the kinds of source the configured servers give a channel.
- `src/dial_deep_research/app/research/source_selection.py` (new): the generic rules as bundles.
- `src/dial_deep_research/app/research/prompts.py`: the four system prompt templates and their
  render functions.
- `src/dial_deep_research/app/research/report_rules.py`: the length violation's wording.
- `src/dial_deep_research/utils/dial_stages.py`: the research-review stage's text for an empty
  next plan.
- `src/dial_deep_research/app/research/nodes.py`: the two review calls' reasoning effort.
- `src/dial_deep_research/app/research/nodes.py`, `graph.py` and `runner.py`: pass the client
  rules and the channel's source kinds to the four nodes.
- `docs/generated-app-schema.json`: regenerated by `make format`.
- `docs/architecture.md`: what each node's system prompt carries.
- `README.md`: the core-config snippet, if it shows `prompts`. No environment variable changes.
- `tests/`: property validation, prompt rendering, and the unchanged template.
- Specs: the four capabilities above.
- Outside this repository, not committed here: a channel's client rules go into its git-ignored
  local `dial_conf/core/applications.json` and into the private configuration repository.
- Out of scope, deferred: a lasting lookup of publication dates by document id, a fixed
  publication-date scoping of the document search, and any change to how a channel's search
  orders its results.
