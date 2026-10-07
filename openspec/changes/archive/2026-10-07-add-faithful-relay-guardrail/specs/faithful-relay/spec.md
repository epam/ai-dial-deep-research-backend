## Purpose

How the report relays what the retrieved sources say and nothing else: it invents, infers and
computes nothing, keeps every figure as its source gives it, and never states a finding more firmly
or more broadly than its source does. The capability owns the faithful-relay terms and rules, each
research step's part of them, and the grounded review: the report-review call that judges a draft
against the sources.

## ADDED Requirements

### Requirement: The faithful-relay rules are a generic policy of quality rules

The faithful-relay rules SHALL be generic quality rules (see **source-selection**), rendered as a
block of their own in each step's system prompt, under a heading that names faithful relay, after
the source-selection block and before the client rules. Report review's block SHALL present the
rules' parts as checks. The rules SHALL name no client, dataset, publication or tool.

The block SHALL open with the definitions of the terms the rules use, under a name distinct from
the source-selection terms, presented as definitions rather than as a rule, and every step SHALL
receive them. The definitions SHALL say that the source-selection terms, such as value, stated date
and described period, apply here too, which is why the faithful-relay block comes after the
source-selection block that defines them.

- **Source**: the result of a research tool call, or the data sources the prompt carries, such as
  the knowledge base's descriptions and what the application fetched from the dataset server. A
  search tool's answer is not a source: it summarises pages, and a summary can change, distort or
  invent what the pages say, such as a value, a sum or a characterisation that no page states. It
  only points at where the evidence lives, and the page is read instead. A page read as text or as
  an image, and a chunk a retrieval tool returns word for word, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say and
  adds nothing to them.
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic or modelling that produces a number no source gives: a growth rate
  derived from two levels, a difference or a gap in percentage points, a ratio, a multiple such as
  "twice as large", a share, a sum, an average, an elasticity or a regression estimate. A comparison
  is not a calculation, and neither is writing a value in another notation, such as a fraction as a
  percentage, or rounding a value given with more digits than a reader can use. This is the
  definition of **report-composition**, "Reports contain no calculations", in the terms' own
  wording.
- **Inference**: a conclusion no source states: a causal link, a forecast, an extrapolated trend,
  an implication, a recommendation, or a position attributed to an organisation.
- **Forecast** and **estimate**: a value its source calls a forecast, a projection, an outlook, an
  estimate or a preliminary figure, or a value for a period that had not ended when the source
  stated it, such as a figure "for 2023" in a note of December 2023, or growth "in 2026" in a report
  of April 2026.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario.
- **Statement about the evidence**: a sentence that says what the research covered, as a section's
  description may ask, that the sources do not give some evidence, or that the report does not
  cover a topic. It states no fact from a source, so it needs no citation.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent, research review, the report writer and report
  review SHALL each carry the faithful-relay block, opening with the definitions above, after the
  source-selection block

#### Scenario: Report review reads the rules as checks

- **WHEN** report review's system prompt is rendered
- **THEN** its faithful-relay block SHALL introduce the parts below it as checks to judge the draft
  against, and SHALL come before its "Not your job" section

### Requirement: Rule 1 — everything the report states comes from a source

The model's own knowledge SHALL add no fact, figure or finding to the report, and where it differs
from a source, the source wins. The report SHALL carry no general background, labelled or not.

- **Research agent:** a search tool's answer summarises pages, and a summary can change, distort or
  invent what they say, so the agent uses it only to find which pages to read, and reads the page
  before using anything the answer says. Every value, finding and characterisation the report may
  use is taken from a page read as text or as an image, or from a chunk returned word for word.
- **Research review:** a value, a finding or a characterisation that the findings hold only in a
  search answer, on no page read and in no chunk returned word for word, is a gap: the page must be
  read.
- **Report writer:** never takes a value, a finding or a characterisation from a search tool's
  answer, because a summary can change, distort or invent what the pages say; it takes it from the
  page that was read. It cites the source of every claim. A summary or a comparison carries the
  citations of the claims it rests on, or stands directly after them; a summary elsewhere, such as
  in an opening overview or a conclusion, repeats their citations. A sentence that can be
  neither cited nor built from cited claims, and is not a statement about the evidence, is left
  out. A fact from the description of a publication series, which has no citation form, names the
  series as its source in words.
- **Report review:** a claim without a citation is a violation, unless it is a summary or a
  comparison standing directly after the cited claims it rests on, a fact that names a publication
  series as its source, or a statement about the evidence. A sentence the draft labels as its own
  inference, synthesis or general background is a violation too.

#### Scenario: A figure only a search answer states is a gap

- **WHEN** a search answer says that the G7 economies "together produced 44%" of world output, and
  no page read and no chunk returned states 44%
- **THEN** research review SHALL return a next step that reads the page the answer cites

#### Scenario: A labelled inference is sent back

- **WHEN** a draft carries the sentence "Our own inference: the slowdown will likely persist into
  2027" with no citation
- **THEN** report review SHALL report it as a violation

#### Scenario: A statement of missing evidence needs no citation

- **WHEN** a draft says "the sources do not give the gap between the two growth rates" with no
  citation
- **THEN** report review SHALL NOT report it as an uncited claim

#### Scenario: A summary of cited claims stands

- **WHEN** a draft's Key Findings says "both sources expect growth to slow in 2026" directly after
  the two cited forecasts it summarises
- **THEN** report review SHALL NOT report the summary as uncited

#### Scenario: A summary away from its claims repeats their citations

- **WHEN** a draft's Overview answers the question in one sentence that summarises two forecasts
  the Detailed Analysis cites, and the sentence carries no citation
- **THEN** report review SHALL report it as an uncited claim, and the writer's part SHALL have asked
  for the two citations to be repeated

### Requirement: Rule 2 — the report infers nothing

The report MAY summarise and compare what the sources say, and SHALL infer nothing.

- **Research agent:** when the question asks why something happened or what it will lead to, looks
  for sources that state the cause or the effect. A movement in the data is not its own
  explanation.
- **Research review:** a cause or an effect the question asks about, with no search in the findings
  for a source that states it, is a gap. Research review never asks for a summary, a comparison or
  a conclusion.
- **Report writer:** states no causal link, forecast, extrapolated trend, implication,
  recommendation or position of an organisation that the sources do not state. A cause, a driver or
  an effect is given only as a source states it, and attributed to that source. Where the question
  asks for an explanation the sources do not give, the report says that they do not give it.
- **Report review:** a cause, a driver, an effect or a forecast stated without a citation is a
  violation. Whether a cited claim goes beyond its source is not the blind review's to judge: the
  grounded review judges it against the sources.

#### Scenario: A why-question with no stated cause

- **WHEN** the question asks why exports fell in a year, and the findings hold the figures but no
  source that states a cause
- **THEN** the report SHALL say that the sources do not give the cause, and SHALL NOT offer one of
  its own

#### Scenario: Research review asks for a stated cause

- **WHEN** the question asks what drove a change and the findings show no search for a source that
  states the driver
- **THEN** research review SHALL return a next step that searches for it

### Requirement: Rule 3 — the grounded review judges the "No calculations" rule

The rule that neither research nor the report calculates is owned by **research-execution**,
"Research looks for a stated figure rather than planning to compute one", by
**clarification-and-plan-alignment**, "The plan never asks for a calculation", and by
**report-composition**, "Reports contain no calculations". It SHALL NOT be a faithful-relay quality
rule, so the faithful-relay block SHALL carry no part of it at any step.

The grounded review SHALL judge the draft against the writer's "No calculations" rule as well as
against the faithful-relay rules: its instructions SHALL carry the writer's "No calculations"
section in the one wording the writer receives, after the faithful-relay rules' writer parts. The
blind review's "No calculations" check can judge only a number the draft presents as computed;
the grounded review can also find a computed number the draft presents as stated, because it sees
that no source gives it.

#### Scenario: The grounded review and the writer share the rule's wording

- **WHEN** the grounded review's instructions and the writer's system prompt are rendered
- **THEN** both SHALL carry the writer's "No calculations" section in the same wording

#### Scenario: A computed gap presented as stated is found

- **WHEN** a draft says that one region grew 1.2 percentage points faster than another, citing a
  page that gives only the two growth rates
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: Rule 4 — figures keep their source's value, unit and period

Every figure SHALL keep its source's value, unit, currency and period, and SHALL say whether it is
nominal or real where the source says so. Three changes are allowed, and none of them is a
calculation:

- **One notation.** Values from different sources may be brought to one notation: a scale word, a
  currency symbol or code, a thousands separator, or a fraction written as a percentage. A
  conversion that needs a rate, such as into another currency, is a calculation.
- **Usable precision.** A value with more digits than a reader can use, such as `0.0473918265`, is
  rounded to a usable precision: the precision the publications use for the same indicator, or what
  the context needs, such as 4.74%.
- **Requested rounding.** A figure is rounded as the research question or the plan asks.

Otherwise the report SHALL keep each figure's precision.

The preparation agent keeps the user's formatting requests, such as rounding, in the restated
query, so that the writer and report review can see them (see
**clarification-and-plan-alignment**). This is a sentence of the preparation prompt, not a part of
the rule, because quality rules have no preparation step.

- **Report writer:** keeps each figure as its source gives it, apart from the three changes.
- **Report review:** a figure without its unit or its currency is a violation, and so is a figure
  with more digits than a reader can use, and a figure not rounded as the research question or the
  plan asks. Whether a figure matches its source is not the blind review's to judge.

#### Scenario: An over-precise dataset value is rounded

- **WHEN** a data query returns a growth rate of `2.156555` percent
- **THEN** the report SHALL give it at a usable precision, such as 2.2% or 2.16%, and report review
  SHALL report a draft that prints all six decimals

#### Scenario: A requested rounding is followed

- **WHEN** the research question asks for figures rounded to whole percentages
- **THEN** report review SHALL report a figure the draft gives with a decimal

### Requirement: Rule 5 — forecasts and estimates are named as such

A forecast or an estimate SHALL be named as one, in the source's own terms, and never presented as
an observed value. A dataset's stated date is its last update, so its values for any later period
are forecasts.

- **Report writer:** names a forecast as a forecast and an estimate as an estimate, such as "the
  publication forecasts" or "a preliminary estimate". A dataset's values for any period after its
  last update are named as forecasts and written in the future or conditional tense, such as "the
  dataset's forecast for 2030", never "grew by 3% in 2030".
- **Report review:** a value for a period that had not ended by its stated date, or has not ended
  today, stated as observed, such as "exports grew 3% in 2027", is a violation. Where the draft
  states a dataset's last update, a value from that dataset for a later period is a forecast, and
  stating it as observed is a violation. A forecast named as a forecast is correct wording, never
  speculative wording. A table names its values as forecasts or estimates when its title, the
  sentence introducing it, a column label or a note says so; each cell needs no label of its own.

#### Scenario: A future value stated as observed

- **WHEN** today is in 2026 and a draft says "exports grew 3% in 2027"
- **THEN** report review SHALL report it as a violation

#### Scenario: A forecast table needs no label per cell

- **WHEN** a draft introduces a table as "the publication's forecasts" and its columns are years up
  to 2027
- **THEN** report review SHALL NOT report its cells as values stated as observed

#### Scenario: A value for the current year stated as observed

- **WHEN** today is 30 September 2026 and a draft says "exports grew 3% in 2026", citing a source
  published in April 2026
- **THEN** report review SHALL report it as a violation, because the year has not ended today

#### Scenario: A dataset value after its last update is a forecast

- **WHEN** a draft says that a dataset was last updated in April 2025 and, citing it, that
  "real GDP grew 3.1% in 2026"
- **THEN** report review SHALL report it as a value stated as observed, and the writer's part SHALL
  have asked for "the dataset's forecast for 2026" in the future or conditional tense

### Requirement: Rule 6 — a finding keeps its source's certainty

A hypothetical or conditional finding SHALL stay hypothetical or conditional, a view a source states
as its own SHALL stay attributed to that source, and no finding SHALL be stated more firmly than its
source states it.

- **Report writer:** keeps a finding's hedging, its conditions and its scenario, and names the
  scenario of a scenario value. A view a source states as its own, such as "in our view" or "we
  expect", stays attributed to that source and keeps its tense: a view about what will happen is
  never written as what happened. "Inflation will ease next year, in our view" is relayed as "the
  publication expected inflation to ease the following year", never as "inflation eased". The writer
  adds no promissory or guarantee-style wording that the source does not use, such as "will
  certainly" or "is guaranteed". Relaying a source's own hedging is not a certainty label, which the
  "never include" list bans.
- **Report review:** wording that promises or guarantees an outcome is a violation, and so is a
  value the draft calls conditional or a scenario in one place and states as an established fact in
  another. A source's hedging relayed in prose, such as "the publication expects", is correct
  wording, and is neither speculative wording nor a certainty label.

#### Scenario: Guarantee wording is sent back

- **WHEN** a draft says export growth "will certainly recover in 2027"
- **THEN** report review SHALL report it as a violation

#### Scenario: Relayed hedging stands

- **WHEN** a draft says "the publication expects growth to recover in 2027", citing it
- **THEN** report review SHALL NOT report it under this rule or under the "never include" list

#### Scenario: A source's expectation is not turned into an outcome

- **WHEN** a publication says inflation "will ease next year, in our view", and a draft says
  "inflation eased", citing it
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: Rule 7 — the report does not distort a source

The report SHALL NOT exaggerate or distort what a source says.

- **Report writer:** relays each finding with the weight and the scope its source gives it. It
  keeps the direction of a source's verdict: where a source calls something slight, low or limited,
  the report does not describe it with a word that points the other way, such as "sharp",
  "high" or "significant", with or without a qualifier. It does not strengthen a finding with an
  intensifier the source does not use, such as "dramatic" or "unprecedented", and does not widen it
  beyond its scope, such as a finding for one region stated for the whole country, or a figure for
  one sector or product line stated for a whole industry.

Report review's system prompt SHALL carry no part of this rule, because a distortion shows only
against the source. The grounded review, which sees the sources, judges it.

#### Scenario: Only the writer and the grounded review are told

- **WHEN** the prompts of a research turn are rendered
- **THEN** the writer's faithful-relay block and the grounded review's instructions SHALL carry
  this rule, and report review's system prompt SHALL NOT

#### Scenario: A reversed verdict is sent back

- **WHEN** a source calls a rise in unemployment "slight", and a draft calls it "a moderately
  significant rise", citing that source
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: Rule 8 — missing evidence is stated, not filled

Where the sources lack the evidence, the report SHALL state the limitation instead of filling the
gap.

- **Report writer:** says what is missing and what therefore cannot be concluded, and never fills
  the gap with its own knowledge or an inference.
- **Report review:** a part of the research question that the draft neither answers nor declares
  unavailable is a violation. A sentence saying that the report does not cover a topic declares
  it.

#### Scenario: An unanswered part of the question

- **WHEN** the question asks for a forecast for two regions and the draft covers one region and says
  nothing of the other
- **THEN** report review SHALL report the missing region as a violation

### Requirement: The grounded review checks the draft against the sources

Report review SHALL make two model calls for every draft it reviews. The **blind review** sees the
draft, the configured sections, the question and the plan, but not the research findings (see
**report-composition**). The **grounded review** judges the draft against the research transcript.
The two SHALL run concurrently, so the review takes as long as the slower of the two.

Its messages SHALL be, in this order:

1. a system message saying that the messages after it are the research the assistant did for the
   question, and that the last messages say what to do with it — and nothing else;
2. the research transcript exactly as the report writer receives it: every message of the turn,
   tool results and their images included, with the status announcements removed;
3. a system message with the grounded review's instructions;
4. a system message with the review request: the configured report structure with each section's
   description, the protected sections, the aligned research question, the approved preparation
   plan, and the draft, last.

**Why this order.** Each message's position has its own reason:

- **The neutral first message.** It is a fixed text with no date, data source or rule, so it is the
  same in every round and every turn. The grounded review does not open with the research agent's
  system prompt; why is given below.
- **The instructions after the transcript.** They come right before the draft they are applied to,
  so the rules the model applies stand next to the text it judges rather than ahead of a transcript
  that can run to tens of thousands of tokens. That is the motive; the benefit to the model is not
  measured, but this is the layout whose recall and precision were measured offline, and the same
  instructions in the first message were not. Their position does not affect the cache: they are
  fixed for the whole turn.
- **The request with the draft, last.** The draft is the only part that changes between rounds, so
  everything before it can be read from the cache.
- **System messages, never user messages, after the transcript,** for the cache (below). The plain
  system role is used: a trailing `developer` message measured no different.

**How the layout keeps a cache hit likely.** The internal cache ablations of the report loop
measured how the provider caches on the DIAL route:

- It caches a prompt only at a point where an earlier request's prompt ended, and a later request
  reuses the longest such earlier prompt that is a prefix of its own.
- A trailing system message is not an end: the cache entry of a request that ends with system
  messages lies at the end of the message before them. A trailing user message is an end, and a
  later request whose last message differs cannot match past it; with a changed closing user
  message no try read anything from the cache.
- A trailing `developer` message behaved like a trailing system message, within the noise of the
  measurement.
- Calls that share a prefix must also share the model, the reasoning effort, the tool list and the
  output schema; `tool_choice` may differ.

The first round therefore leaves an entry at the end of the transcript, and each later round of the
turn can read up to it, as long as:

- both trailing messages are system messages, never user messages;
- the transcript is passed exactly as the writer receives it, and is the same in every round:
  research is over when the report loop starts, and neither the report node nor report review
  writes to it, so drafts and review items never enter it;
- every round uses the same model and reasoning effort, with no tools and no output schema.

Even then a round reads the cache only when DIAL sends it to the upstream that holds the entry: in
the measurement an unpinned trailing system message hit in about half of the tries. Nothing SHALL
depend on the cache being used; the `cache_read` count in the grounded review's log record shows
whether it was.

**Why the grounded review does not reuse the research agent's cached prefix.** The last call of the
research agent leaves a cache entry at the end of its prompt: its system prompt, its tools and the
transcript up to its last tool result. A call that opened with the same system prompt and tools and
then the transcript could read that entry in its first round as well, and the internal ablations
measured calls laid out that way doing so. The grounded review is not laid out that way, because
of these premises. If one of them stops holding, the decision SHALL be reconsidered:

1. **The reasoning effort differs.** The research agent runs at `none`, the grounded review at
   `medium`, and a different effort was measured to lose the cache. At `none` the grounded review
   found well under half of the severe violations, at about a third precision, so it cannot drop to
   the research agent's effort. Reconsider when the research agent runs at the grounded review's
   effort.
2. **The tools differ, but that alone does not block the reuse.** The research agent binds the
   research tools with `tool_choice` forcing a call; the grounded review binds none. To share the
   prefix it would bind the same tools and forbid calling them programmatically through
   `tool_choice`: `none` forbids every call, and a selection of allowed tools forbids the rest. The
   API enforces that choice, so the model is not trusted to refrain, and the tool list stays the
   same, which is what the cache needs: `tool_choice` was measured to differ between calls that
   share a prefix without losing the cache, and the end-to-end cache runs bound the research tools
   with `tool_choice` `none`. Its cost is the tool definitions in every review request, which the
   cache serves on a hit.
3. **A hit is not certain anyway.** Even an exact shared prefix is read only when DIAL routes the
   call to the upstream that holds the entry: about half of the unpinned tries hit, and pinned calls
   still missed a few times in about 55. Reconsider when routing makes a hit close to certain.
4. **The research agent's instructions would come first.** Its system prompt tells the model that
   it is the research agent, that every step is a tool call and that it never writes prose. A
   review opening with it would have to override those instructions with later ones in the same
   request. How that affects the review is not measured.
5. **The measured quality is the neutral layout's.** The grounded review's recall and precision
   were measured with the neutral first message only.

The grounded review's instructions SHALL carry, in this order:

- that it is the report check of a deep-research assistant, today's date, and that it judges the
  draft against the rules below and nothing else;
- that it works claim by claim: every sentence and table cell that states a figure, a forecast or
  an estimate, a comparison, a cause or a characterisation of what a source found is compared with
  the source passage it relays, and every claim its source does not support as written is reported
  — such as a figure no source gives or one for another scope than the source's, a comparison or a
  finding that reverses or outweighs the source, a forecast, an estimate or a source's own view
  written as an observed fact, and a conclusion, a cause or an explanation no source states — and
  that it then checks the rest of the rules against the whole draft before answering;
- the source-selection terms as the report writer receives them, presented as definitions — not the
  source-selection rules;
- the faithful-relay rules' **report-writer** parts, as what the report must do, introduced as
  rules judged against the findings, because the report-review parts assume a reviewer who cannot
  see the sources, followed by the writer's "No calculations" section (see Rule 3);
- the turn's data-sources string in a `<data_sources>` block, which counts as a source;
- that the transcript before the instructions is the findings, to be used for every check that
  compares the report with its sources, and that a claim the findings hold only in a search tool's
  summarising answer is not supported by a source;
- what is not its job: whether the research was thorough; whether a claim carries a citation or
  where a citation stands, which the blind review judges; which term or name the report uses for a
  concept, which the channel's own rules may set and the grounded review does not see; the report's
  sections, headings, Markdown and citation format, which the blind review judges; the length,
  hyperlinks, and whether a cited identifier exists, which the app checks itself; it never asks for
  more research, more sources, a different analysis, a rewrite or wording it would prefer;
- that it answers with a numbered list, one item per wrong claim, naming the rule it breaks, the
  passage quoted exactly, what the source says instead and what to change, where a claim the draft
  repeats in several places is one item that quotes every place; or with exactly `No violations.`
  when the draft breaks none; and that it calls no tool.

The grounded review SHALL NOT receive the client rules, the blind review's numbered checks, the
glossary rule, the source-selection rules or any other policy's rules. No tool SHALL be bound and no
output schema SHALL be set. It SHALL use the default chat model at reasoning effort `medium`.

Its answer SHALL be read as a numbered list: each numbered item is one violation, and the lines
under an item belong to it. A line SHALL open a new item only when it starts, unindented, with the
next number in sequence, so an indented sub-list or a line that starts with a year stays inside the
item above it. An answer that is `No violations.`, ignoring case, surrounding whitespace, Markdown
wrapping such as backticks, asterisks or quotes, and trailing punctuation, SHALL add no item. A
non-empty answer with no numbered line SHALL be one item, so a violation is never dropped silently.
An empty answer SHALL count as a failed grounded review, not as an approval.

#### Scenario: The grounded review's messages and roles

- **WHEN** report review judges a draft
- **THEN** the grounded review SHALL receive a system message, then the writer's transcript,
  then two more system messages: the instructions, then the request ending in the draft

#### Scenario: The grounded review sees the transcript the writer saw

- **WHEN** research-agent fetched a page in image mode and announced steps with `update_status`
- **THEN** the grounded review's transcript SHALL carry the page's image and SHALL NOT carry the
  status calls or their acknowledgements, exactly as the report writer's transcript does

#### Scenario: The grounded review carries the writer parts and the terms, not other rules

- **WHEN** the grounded review's instructions are rendered on a channel with client rules and a
  glossary
- **THEN** they SHALL carry the source-selection terms and the faithful-relay rules' report-writer
  parts, and SHALL carry no client rule, no source-selection rule, no glossary rule and none of
  the blind review's numbered checks

#### Scenario: A term set by a channel rule is not a violation

- **WHEN** a channel's own rule makes the writer use another term than a source's for one concept,
  and the draft does so
- **THEN** the grounded review's instructions SHALL have said that the term a report uses for a
  concept is not its to judge

#### Scenario: An empty answer is a failed grounded review

- **WHEN** the grounded review's call returns no text
- **THEN** the grounded review SHALL add no item, a warning SHALL record the failure, and the stage
  SHALL record that the grounded review failed rather than that the draft satisfies every check

#### Scenario: A wrapped approval is an approval

- **WHEN** the grounded review answers `` `No violations.` `` or `**No violations.**`
- **THEN** it SHALL add no item

#### Scenario: A clean draft

- **WHEN** the grounded review answers `No violations.`
- **THEN** it SHALL add no item to the review's violations

#### Scenario: An answer that opens with "No violations" but lists one keeps it

- **WHEN** the grounded review answers "No violations of the other rules." followed by one numbered
  item
- **THEN** that item SHALL join the review's violations

#### Scenario: A figure no source gives is found

- **WHEN** a draft states a 44% share, citing a page that does not give it, and only a search
  answer in the transcript says 44%
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: The grounded review's items join the review's violations

The grounded review's items SHALL be appended after the blind review's violations, which come
after the app-checked rules' violations, in one list. The list SHALL drive the loop as before: an
empty list delivers the draft, and any item forces a revision. The grounded review SHALL NOT change
the loop's routing, its version budget or its revision request.

A failed grounded review SHALL NOT fail the turn: when its call fails after its transient-drop
retries, or answers with no text, the failure SHALL be logged as a warning naming the failure kind,
the grounded review SHALL add no item, and the app-checked violations and the blind review's
violations SHALL still stand. A failed blind review SHALL leave the grounded review's items standing
in the same way.

#### Scenario: Both calls report violations

- **WHEN** the app-checked rules report a length violation, the blind review reports two violations
  and the grounded review reports three
- **THEN** the revision request SHALL carry six numbered items: the length violation, then the blind
  review's two, then the grounded review's three

#### Scenario: The grounded review fails

- **WHEN** the grounded review's call raises after its retries and the blind review approves the
  draft
- **THEN** the draft SHALL be delivered, the turn SHALL complete, and a warning SHALL record the
  grounded review's failure kind

#### Scenario: The grounded review alone finds a violation

- **WHEN** the blind review approves the draft and the grounded review reports one violation
- **THEN** the draft SHALL be revised against that violation

### Requirement: The prompt text agrees with the faithful-relay rules

The text the prompts already carry SHALL NOT contradict the faithful-relay rules:

- **Report writer.** Its citations section SHALL NOT allow a sentence flagged as the writer's own
  synthesis or inference: an uncitable sentence stays only where rule 1 allows it, and the section
  SHALL refer to rule 1 rather than restate its exemptions. Its "never include" list SHALL NOT ask
  it to say when a statement is its own inference. Its rules that outrank the request SHALL include,
  after the "No calculations" rule of **report-composition** and the source-selection prohibitions,
  two faithful-relay rules: inferring nothing, and keeping every figure as its source gives it apart
  from the allowed changes. A statement that the sources do not give a figure or an explanation is a
  statement about the evidence, not an explanation of a declined request. A section's description,
  default or configured, SHALL NOT override the "No calculations" rule or these two rules: where a
  description asks for implications, recommendations or a computed figure, the rules win and the
  rest of the description still applies.
- **Report review.** Its section-content check SHALL accept uncited text only where rule 1's check
  accepts it, referring to that check rather than restating it, and SHALL NOT accept text flagged as
  the report's own inference.
- **Research review.** Its prompt SHALL say that the report writer does summaries and comparisons,
  and that a next step never asks for one; that nobody calculates is owned by
  **research-execution**, "Research looks for a stated figure rather than planning to compute one".
  Its gap for a figure, date or entity seen only in a search summary SHALL cover a finding and a
  characterisation too, and SHALL accept a chunk returned word for word as well as a page read.
- **Research agent.** Its tools guidance SHALL say that the search tool answers with summaries a
  model writes, which can change, distort or invent a value, a sum or a characterisation that no
  page states, so a summary is a pointer and not evidence; that the pages it points at are read,
  and every value and finding is taken from what was read; and that the retrieval tool's chunks,
  which quote the documents word for word, are evidence.

#### Scenario: No step is told it may infer

- **WHEN** the prompts of a research turn are rendered
- **THEN** no prompt SHALL carry text allowing the report's own inference or synthesis, and
  research review's prompt SHALL NOT say that the writer does calculations

#### Scenario: A configured section asking for implications

- **WHEN** a channel configures a section "Implications" whose description asks what the findings
  imply for the next year, and no source states an implication
- **THEN** the writer SHALL say in that section that the sources do not state one, and SHALL NOT
  infer one

#### Scenario: The research agent is told why a summary is not evidence

- **WHEN** the research agent's system prompt is rendered
- **THEN** its tools guidance SHALL say that a search summary can change, distort or invent a
  figure, and that every figure is taken from a page that was read

### Requirement: The default sections ask for no inference

No default section description SHALL ask for more than summaries and comparisons of what the
sources say. The default "Detailed Analysis" section SHALL ask for what the sources say and how
their findings compare, and the default "Conclusion" section for a summary of what the findings
answer and what they cannot answer, with no new facts.

#### Scenario: The defaults are rendered

- **WHEN** a channel configures no report structure
- **THEN** no section description the writer and report review receive SHALL ask for what follows
  from the sources or for a bottom line the analysis supports

### Requirement: Faithful relay is verified by evals

The faithful-relay rules and the grounded review SHALL be measured offline and on live runs before
the change is released, against the severe faithful-relay violations of a test set of judged drafts:
a number no source gives, a reversed comparison or finding, a forecast, estimate or hedged view
stated as observed, a conclusion or cause no source states, or a figure for another scope than the
source's. Report review with the grounded review SHALL find at least 70% of the severe violations,
pooled over two repeats, and at least 70% of the grounded review's items SHALL name a real
violation. The live runs SHALL report the severe violations per draft, the time per turn and per
review round, and the grounded review's cached input tokens on later rounds.

#### Scenario: The thresholds are measured

- **WHEN** the change is ready for release
- **THEN** its offline severe recall and the grounded review's precision SHALL have been measured
  against the test set, and a result under either threshold SHALL be reported with the violations
  the review missed
