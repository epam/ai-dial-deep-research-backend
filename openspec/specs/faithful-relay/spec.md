# faithful-relay Specification

## Purpose

How the report relays what the retrieved sources say and nothing else: it invents, infers and
computes nothing, keeps every figure as its source gives it, and never states a finding more firmly
or more broadly than its source does. The capability owns the faithful-relay terms and rules, each
research step's part of them, and the grounded review: the report-review call that judges a draft
against the sources.

## Requirements

### Requirement: The faithful-relay rules are a generic policy of quality rules

The faithful-relay rules SHALL be generic quality rules (see **source-selection**), rendered as a
block of their own in each step's system prompt, under a heading that names faithful relay, after
the source-selection block and before the other generic policies and the client rules. The blind
review's block SHALL present the rules' parts as checks. The grounded review's block SHALL carry
the rules' report-writer parts (see "The grounded review checks the draft against the sources"). The
rules SHALL name no client, dataset, publication or tool. The terms MAY name a search tool and a
retrieval tool as examples, such as `rag_search` and `retrieve_text_chunks`.

The block SHALL open with the definitions of the terms the rules use, under a name distinct from
the source-selection terms, presented as definitions rather than as a rule, and every step, the
grounded review included, SHALL receive them. The terms are the policy's terms, not one of its
rules (see **source-selection**, "A quality rule is one bundle of step instructions"). The
definitions SHALL say that the source-selection terms, such as value, stated date
and described period, apply here too, which is why the faithful-relay block comes after the
source-selection block that defines them.

- **Source**: the result of a research tool call, or the data sources every prompt carries: the
  knowledge base's descriptions, and the list of datasets and their structures. The answer of a
  search tool that summarises pages, such as `rag_search`, is not a source. A model that follows
  none of these rules writes it, and it can state a sum or a characterisation that the pages do
  not state. It only points at where the evidence lives. A page read as text or as an image, and a
  chunk a retrieval tool returns word for word, such as `retrieve_text_chunks`, are sources.
- **Claim**: a sentence or a table cell of the report that states a fact, a figure or a finding.
- **Summary**: a claim that restates, condenses or groups what cited claims of the report say and
  adds nothing to them, such as "both sources expect growth to slow in 2026".
- **Comparison**: a claim that relates figures the sources give and produces no new number: which
  value is larger, which series grew faster, a rank, whether a value is above or below another, or
  the direction of a change.
- **Calculation**: arithmetic that produces a number no source gives: a growth rate derived from
  two levels, a difference or a gap in percentage points, a ratio, a multiple such as "twice as
  large", a share, a sum or an average. A comparison is not a calculation. Writing a value in the
  unit its source states for it, such as a fraction written as the percentage its series name
  states, is not a calculation either.
- **Inference**: a conclusion no source states: a causal link, a forecast, an extrapolated trend,
  an implication, a recommendation, or a position attributed to an organisation.
- **Forecast**: a value that its source labels as a forecast, a projection or an outlook. A value
  for a period that ends on or after the stated date of its source is also a forecast, unless its
  source labels it as observed. For example, a publication dated 20 November 2025 that says
  exports "reached USD 250 billion in 2025" gives a forecast, because 2025 was not over. The past
  tense does not make the value observed.
- **Statement about the evidence**: a sentence that says what the research covered, as a section's
  description may ask, that the sources do not give some evidence, or that the report does not
  cover a topic. It states no fact from a source, so it needs no citation.
- **Certainty**: how firmly a source states a finding: as an established fact, a forecast, an
  expectation, a possibility, a condition or a scenario.

#### Scenario: Every step receives the terms

- **WHEN** a research turn runs
- **THEN** the system prompts of the research agent, research review, the report writer, the blind
  review and the grounded review SHALL each carry the faithful-relay block, opening with the
  definitions above, after the source-selection block

#### Scenario: The blind review reads the rules as checks

- **WHEN** the blind review's system prompt is rendered
- **THEN** its faithful-relay block SHALL introduce the parts below it as checks to judge the draft
  against, and SHALL come before its "Not your job" section

#### Scenario: The forecast term carries a generic example

- **WHEN** the faithful-relay terms are rendered
- **THEN** the forecast term SHALL give as its example a publication dated 20 November 2025 that
  says exports "reached USD 250 billion in 2025", and SHALL define no estimate term

### Requirement: Rule 1 — everything the report states comes from a source

The rule is named "Facts only from the sources". The model's own knowledge SHALL add no fact,
figure or finding to the report, and where it differs from a source, the source wins. The report
SHALL carry no general background, labelled or not, and no sentence that it labels as its own
inference or synthesis.

- **Research agent:** a search tool's answer summarises pages, and a summary can change, distort or
  invent what they say, so the agent uses it only to find which pages to read, and reads the page
  before using anything the answer says. Every value, finding and characterisation the report may
  use is taken from a page read as text or as an image, or from a chunk returned word for word.
- **Research review:** a value, a finding or a characterisation that the findings hold only in a
  search answer, on no page read and in no chunk returned word for word, is a gap: the page must be
  read. A search answer cites the page of each statement. When research has read the cited page,
  the statement is not a gap. This holds even when the page text that research review sees does
  not contain the statement, because the page can give it only in its image, which research review
  does not see.
- **Report writer:** never takes a value, a finding or a characterisation from a search tool's
  answer, because a summary can change, distort or invent what the pages say; it takes it from the
  page that was read. It cites the source of every claim. A summary or a comparison carries the
  citations of the claims it rests on, or stands directly after them; a summary elsewhere, such as
  in an opening overview or a conclusion, repeats their citations. A sentence that can be
  neither cited nor built from cited claims, and is not a statement about the evidence, is left
  out. A fact from the description of a publication series, which has no citation form, names the
  series as its source in words. A cell of a table that combines sources needs no citation when a
  passage next to the table cites its sources, as the source-selection rule "Every current value,
  with its own source" allows. A cell of a table that holds values from one source needs no
  citation when the title of the table cites that source.
- **Report review:** a claim without a citation is a violation, with these exceptions:
  - a summary or a comparison of cited claims beside it;
  - a fact that names a publication series as its source;
  - a statement about the evidence;
  - a cell of a table whose sources a passage right before or right after the table cites;
  - a cell of a table that holds values from one source and cites that source in its title.

  A sentence the draft labels as its own inference, synthesis or general background is a violation
  too.

#### Scenario: A figure only a search answer states is a gap

- **WHEN** a search answer says that the G7 economies "together produced 44%" of world output, and
  no page read and no chunk returned states 44%
- **THEN** research review SHALL return a next step that reads the page the answer cites

#### Scenario: A statement from a cited page that was read is not a gap

- **WHEN** a search answer attributes a figure to a page, research has read that page, and the page
  text that research review sees does not contain the figure
- **THEN** research review SHALL NOT report the figure as a gap

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
  that a later section cites, and the sentence carries no citation
- **THEN** report review SHALL report it as an uncited claim, and the writer's part SHALL have asked
  for the two citations to be repeated

#### Scenario: A table of one source is cited in its title

- **WHEN** a draft's table holds values from one data query, its title ends with
  `[data_query dq_0123abcd45]`, and its cells carry no citation
- **THEN** report review SHALL NOT report the cells as uncited claims

### Requirement: Rule 2 — the report infers nothing

The rule is named "No conclusion that no source states". The report MAY summarise and compare what
the sources say, and SHALL infer nothing.

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

### Requirement: Rule 3 — the grounded review judges the "No calculation by research or the report" rule

The rule that neither research nor the report calculates is owned by **research-execution**,
"Research looks for a stated figure rather than planning to compute one", by
**clarification-and-plan-alignment**, "The plan never asks for a calculation", and by
**report-composition**, "Reports contain no calculations". The writer's section that states it is
named "No calculation by research or the report". It SHALL NOT be a faithful-relay quality rule, so
the faithful-relay block SHALL carry no part of it at any step.

The grounded review SHALL judge the draft against the writer's "No calculation by research or the
report" rule as well as against the faithful-relay rules. Its instructions SHALL carry the writer's
"No calculation by research or the report" section in the one wording the writer receives, as a
section of its own after the generic policy blocks and before the client rules, which never
override it. The blind review's "No calculation by research or the report" check can judge only a
number the draft presents as computed. The grounded review can also find a computed number that the
draft presents as stated, because it sees that no source gives it.

#### Scenario: The grounded review and the writer share the rule's wording

- **WHEN** the grounded review's instructions and the writer's system prompt are rendered
- **THEN** both SHALL carry the writer's "No calculation by research or the report" section in the
  same wording

#### Scenario: A computed gap presented as stated is found

- **WHEN** a draft says that one region grew 1.2 percentage points faster than another, citing a
  page that gives only the two growth rates
- **THEN** the grounded review SHALL report the sentence as a violation

### Requirement: Rule 4 — figures keep their source's value, unit and period

The rule is named "Each figure with its source's value, unit and period". Every figure SHALL keep
its source's value, unit, currency and period, and SHALL say whether it is nominal or real where the
source says so. Two changes are allowed, and neither of them is a calculation:

- **One notation.** Values from different sources may be brought to one notation: a scale word, a
  currency symbol or code, a thousands separator, or a fraction written as a percentage. A
  conversion that needs a rate, such as into another currency, is a calculation.
- **Usable precision.** A value with more digits than a reader can use, such as `0.0473918265`, is
  rounded to a usable precision: the precision the publications use for the same indicator, or what
  the context needs, such as 4.74%.

Otherwise the report SHALL keep each figure's precision. This holds also when the research question
or the plan asks to round figures or to give a number of decimals.

The preparation agent keeps the user's formatting requests, such as a unit, in the restated query,
because the report is written from that query (see **clarification-and-plan-alignment**). This is
a sentence of the preparation prompt, not a part of the rule, because quality rules have no
preparation step.

- **Report writer:** keeps each figure as its source gives it, apart from the two changes, whatever
  rounding the research question or the plan asks for.
- **Report review:** a figure without its unit or its currency is a violation, and so is a figure
  with more digits than a reader can use. Whether a figure matches its source is not the blind
  review's to judge.

#### Scenario: An over-precise dataset value is rounded

- **WHEN** a data query returns a growth rate of `2.156555` percent
- **THEN** the report SHALL give it at a usable precision, such as 2.2% or 2.16%, and report review
  SHALL report a draft that prints all six decimals

#### Scenario: A requested rounding does not change the precision

- **WHEN** the research question asks for figures rounded to whole percentages, and a source gives
  a growth rate of 2.4%
- **THEN** the report SHALL give 2.4%, and report review SHALL NOT report the decimal

### Requirement: Rule 5 — forecasts are named as such

The rule is named "Forecasts named as such". A forecast SHALL be named as a forecast and SHALL NOT
be written as what happened.

- **Report writer:**
  - Names a forecast as a forecast. When its source labels it, the writer uses the source's own
    word, such as "the publication forecasts" or "projects".
  - When a source labels a value as observed or as a forecast, the writer uses that label. A label
    is an explicit word, such as "actual", "historical", "forecast" or "projection", or an
    observation status of a dataset value that says that the value is observed or a forecast. The
    tense of a sentence is not a label, and the word "estimate" is not a label either.
  - For a value that its source does not label, the date test decides. The value is a forecast
    when its period ends on or after the stated date of its source. When neither the findings nor
    the data sources give a stated date for the source, today's date takes its place. A dataset's
    stated date is its last update, as the source-selection terms define it.
  - Writes a forecast so that it reads as a forecast, such as "the forecast for 2030", "is
    expected to grow by 3% in 2030" or "the publication expected growth of 3% in 2025". It never
    writes a forecast as what happened, such as "grew by 3% in 2030".
  - Names the type of a forecast, such as "baseline" or "scenario", only when a source names it.
  - Names the values of a table as forecasts in its title, the sentence that introduces it, a
    column label or a note. Each cell then needs no label of its own.

The rule SHALL have no blind-review part. The grounded review judges it against the writer part,
because the label and the stated date of a value show only in the findings.

#### Scenario: A past-tense value for an unfinished period is a forecast

- **WHEN** a publication dated 20 November 2025 says that exports "reached USD 250 billion in
  2025", and a draft says "exports reached USD 250 billion in 2025", citing it
- **THEN** the grounded review SHALL report the sentence as a forecast written as what happened

#### Scenario: A dataset value after its last update is a forecast

- **WHEN** a dataset was last updated on 2026-06-15, its values carry no observation status, and a
  draft says "real GDP grew 3.1% in 2026", citing it
- **THEN** the grounded review SHALL report it, and the writer's part SHALL have asked for wording
  that reads as a forecast, such as "the forecast for 2026"

#### Scenario: An observation status labels a value as observed

- **WHEN** a dataset was last updated on 2026-06-15, and its value for 2026 carries an observation
  status that says that the value is observed
- **THEN** the writer SHALL state the value as observed, and the grounded review SHALL NOT report it

#### Scenario: The word "estimate" is not a label

- **WHEN** a publication dated 2025-03-10 calls its value for 2025 a "preliminary estimate"
- **THEN** the date test SHALL decide, and the writer SHALL name the value as a forecast

#### Scenario: A forecast table needs no label per cell

- **WHEN** a draft introduces a table as "the publication's forecasts" and its columns are years up
  to 2027
- **THEN** the grounded review SHALL NOT report its cells as values stated as observed

#### Scenario: No baseline that the source does not name

- **WHEN** a publication gives one forecast and does not call it a baseline
- **THEN** the writer SHALL NOT call it "the baseline forecast"

#### Scenario: The blind review carries no part of the rule

- **WHEN** the blind review's system prompt is rendered
- **THEN** it SHALL NOT carry the rule "Forecasts named as such"

### Requirement: Rule 6 — a finding keeps its source's certainty

The rule is named "No finding stated more firmly than its source". A hypothetical or conditional
finding SHALL stay hypothetical or conditional, a view a source states as its own SHALL stay
attributed to that source, and no finding SHALL be stated more firmly than its source states it.

- **Report writer:** keeps a finding's hedging, its conditions and its scenario, and names the
  scenario of a scenario value. A view a source states as its own, such as "in our view" or "we
  expect", stays attributed to that source. A forecast, as Rule 5 decides, is never written as what
  happened, even when its source writes it in the past tense. "Inflation will ease next year, in
  our view" is relayed as "the publication expected inflation to ease the following year", never as
  "inflation eased". The writer adds no promissory or guarantee-style wording that the source does
  not use, such as "will certainly" or "is guaranteed". Relaying a source's own hedging is not a
  certainty label, which the "never include" list bans.
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

The rule is named "No exaggeration or distortion of a source". The report SHALL NOT exaggerate or
distort what a source says.

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

The rule is named "The limitation stated where evidence is missing". Where a source-selection rule
requires a statement that evidence is missing, the report SHALL also state what cannot be concluded,
and SHALL NOT fill the gap.

- **Report writer:** where the source-selection rule "When to say that evidence is missing"
  requires a statement that evidence is missing (see **source-selection**), also says what the
  reader therefore cannot conclude. It never fills the gap with its own knowledge or an inference.
- **Blind review:** a fact that the research question or the approved plan asks for, and that the
  draft neither answers nor declares unavailable, is a violation. A plan item that names a source is
  answered when its fact is answered, from that source or from another. A fact that a rule excludes
  from the report is the exception: leaving it out without comment is correct, and mentioning it is
  a violation of the removal rule (see **prohibited-content**). The blind review judges this
  because it sees the client rules that exclude content. For excluded content, a sentence saying
  that the report does not cover it is a violation of the removal rule (see **prohibited-content**).
  The source-selection rule "When to say that evidence is missing" makes the blind review accept a
  statement that the sources do not give an item.

#### Scenario: An unanswered part of the question

- **WHEN** the question asks for a forecast for two regions and the draft covers one region and says
  nothing of the other
- **THEN** the blind review SHALL report the missing region as a violation

#### Scenario: An unanswered plan item

- **WHEN** the approved plan has an item on import prices and the draft neither covers it nor says
  that the sources do not give it
- **THEN** the blind review SHALL report the plan item as a violation

#### Scenario: A plan item naming a source is answered from another

- **WHEN** a plan item asks to search a named publication for a 2026 forecast, the publication
  only repeats the dataset value, and the draft gives the dataset value
- **THEN** the blind review SHALL NOT report the plan item

#### Scenario: An excluded part of the question is left out

- **WHEN** the question asks for the results of named companies, a client rule excludes company
  results, and the draft leaves them out without comment
- **THEN** the blind review SHALL NOT report the omission

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
   still missed occasionally. Reconsider when routing makes a hit close to certain.
4. **The research agent's instructions would come first.** Its system prompt tells the model that
   it is the research agent, that every step is a tool call and that it never writes prose. A
   review opening with it would have to override those instructions with later ones in the same
   request. How that affects the review is not measured.
5. **The measured quality is the neutral layout's.** The grounded review's recall and precision
   were measured with the neutral first message only.

The grounded review's instructions SHALL carry, in this order:

- that it is the report check of a deep-research assistant, today's date, and that it judges the
  draft against the rules below and nothing else;
- that it works claim by claim: every sentence and table cell that states a figure, a forecast, a
  comparison, a cause or a characterisation of what a source found is compared with the source
  passage it relays, and every claim its source does not support as written is reported — such as
  a figure no source gives or one for another scope than the source's, a comparison or a finding
  that reverses or outweighs the source, a forecast or a source's own view written as an observed
  fact, and a conclusion, a cause or an explanation no source states — and that it then checks the
  rest of the rules against the whole draft before answering;
- a sentence, before every rule block, saying that each rule below says what the report must do
  or what counts as a violation, that the transcript before the instructions is the findings, and
  that the draft is judged against them and every passage that breaks a rule is reported; that
  when a rule asks the report to give a value or its context, such as both a dataset value and a
  publication value, and the findings hold it but the draft leaves it out, the grounded review
  reports it and asks for it to be added, unless a rule keeps that content out of the report; and
  that it never asks to add supporting context, because the writer decides which supporting
  context to include;
- the generic policies' blocks, in the policy order (see **source-selection**): the
  source-selection block, with the source-selection terms and every source-selection rule's
  **report-writer** part; the faithful-relay block, with the faithful-relay terms and every
  faithful-relay rule's **report-writer** part; and the **grounded** parts of the other policies'
  rules, such as "Codelist values by name" (see **language-and-style**) and "Accurate and
  consistent terms" (see **terminology**). The source-selection and faithful-relay rules are given
  in their writer parts, as what the report must do, because their blind parts assume a reviewer
  who cannot see the sources;
- the writer's "No calculation by research or the report" section, as a section of its own (see
  Rule 3);
- the grounded parts of the channel's client rules, in a `<client_rules>` block, when a client rule
  sets one;
- the writer parts of the channel's client rules, in a `<client_writer_rules>` block under its own
  heading, when a client rule sets one, introduced as context and not as checks: the grounded
  review does not report a passage under them unless a client check names it, uses them to know
  which content the report must leave out and which terms it must use, and never asks for content
  they keep out of the report. Where one of them is more specific than a rule above, the grounded
  review follows it: it does not report a passage that the client rule requires, and does not ask
  to remove it. This is how the grounded review can ask for a missing value without asking for
  content a client rule excludes; the client rules' blind parts, which judge exclusions, stay with
  the blind review;
- the turn's data-sources string in a `<data_sources>` block, which counts as a source;
- that the transcript before the instructions is the findings, to be used for every check that
  compares the report with its sources, and that a claim the findings hold only in a search tool's
  summarising answer is not supported by a source;
- what is not its job: whether the research was thorough; whether a claim carries a citation or
  where a citation stands, which the blind review judges; the report's sections, Markdown and
  citation format, which the blind review judges; the headings, the length, hyperlinks, and whether
  a cited identifier exists, which the app checks itself; it never asks for more research, more
  sources, a different analysis, a rewrite or wording it would prefer;
- that it answers with a numbered list, one item per violation, naming the rule it breaks, the
  passage quoted exactly, what the source says instead and what to change, where a violation the
  draft repeats in several places is one item that quotes every place; or with exactly
  `No violations.` when the draft breaks none; and that it calls no tool. The answer format SHALL
  state the layout the answer is read by, below: each item starts on a new line with its number, a
  full stop and a space, with nothing before the number, and every further line of an item is
  indented. It SHALL give a short example of two items.

**Why both reviews check the source-selection and faithful-relay rules.** The blind review judges
these rules by their blind parts, and the grounded review by their writer parts. The duplication is
deliberate, and SHALL stay until an eval shows that the blind review finds nothing the grounded
review misses:

- the two checks of the faithful-relay rules were evaluated together, so dropping either one risks
  a regression;
- the blind parts carry sentences whose only job is to stop a review from flagging a correct draft,
  such as "A year column or a row label in a table gives the described period of each value in
  it", which the grounded review does not receive;
- a failed review call does not fail the turn, so the blind review still checks a draft when the
  grounded call fails.

The grounded review lacking those guarding sentences is a known risk for the source-selection
rules, whose writer parts it newly receives: it may flag a correct draft that the blind review would
pass. The eval of this change SHALL check the grounded review's source-selection items for such
mistakes. The code that renders the grounded review's instructions SHALL state the duplication and
this risk in a comment.

The grounded review SHALL NOT receive the client rules' research parts, any rule's blind part, the
blind review's numbered checks or the glossary rule. No tool SHALL be bound and no
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

#### Scenario: The grounded review carries the writer parts, the grounded parts and the terms

- **WHEN** the grounded review's instructions are rendered on a channel with a glossary and client
  rules, one of which sets a grounded part
- **THEN** they SHALL carry the source-selection and faithful-relay terms, the source-selection and
  faithful-relay rules' report-writer parts, every generic rule's grounded part, and that client
  rule's grounded part in a `<client_rules>` block, every client rule's writer part in a
  `<client_writer_rules>` block introduced as context, and SHALL carry no rule's blind part, no
  client rule's research part, no glossary rule and none of the blind review's numbered checks

#### Scenario: A term that a channel rule sets is not a violation

- **WHEN** a channel's writer rule makes the report use another term than a source's for one
  concept, with the same meaning, and the draft does so
- **THEN** the grounded review's instructions SHALL carry that rule as context, and SHALL say that
  a client writer rule more specific than a rule above is followed, and that a passage it requires
  is not reported

#### Scenario: A missing value is asked for

- **WHEN** the findings hold a publication value and a dataset value for one fact, and the draft
  gives only the dataset value
- **THEN** the grounded review SHALL report the missing publication value and ask for it to be added

#### Scenario: Supporting context is not asked for

- **WHEN** the findings hold a driver of a value that a source states, and the draft gives the
  value without that driver
- **THEN** the grounded review's instructions SHALL have said never to ask to add supporting
  context, because the writer decides which supporting context to include

#### Scenario: An excluded value is not asked for

- **WHEN** a client rule's writer part keeps some values out of the report, and the draft leaves
  such a value out although the findings hold it
- **THEN** the grounded review's instructions SHALL carry that writer part as context and SHALL say
  never to ask for content it keeps out of the report

#### Scenario: Without client writer rules there is no context section

- **WHEN** the channel configures no client rule with a writer part
- **THEN** the grounded review's instructions SHALL carry no `<client_writer_rules>` block and no
  sentence that refers to one

#### Scenario: The answer format is stated with an example

- **WHEN** the grounded review's instructions are rendered
- **THEN** their answer section SHALL say that each item starts on a new line with its number and a
  full stop, with further lines indented, and SHALL carry an example of two numbered items

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
after the app-checked rules' violations, in one list. The list SHALL drive the loop: an
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
  synthesis or inference: an uncitable sentence stays only where rule 1, "Facts only from the
  sources", allows it, and the section SHALL refer to rule 1 by its name rather than restate its
  exemptions. Its "never include" list SHALL NOT ask it to say when a statement is its own
  inference. Its rules that outrank the request SHALL include, after "No calculation by research or
  the report" of **report-composition**, the rules that exclude content and the source-selection
  prohibitions, two faithful-relay rules, each named in the list: inferring nothing ("No conclusion
  that no source states"), and keeping every figure as its source gives it apart from the changes
  that "Each figure with its source's value, unit and period" allows. A section's description,
  default or configured, SHALL NOT override "No calculation by research or the report" or these two
  rules: where a description asks for implications, recommendations or a computed figure, the rules
  win and the rest of the description still applies.
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

#### Scenario: The outrank list names the faithful-relay rules

- **WHEN** the writer's system prompt is rendered
- **THEN** its list of rules that outrank the request SHALL name "No conclusion that no source
  states" and "Each figure with its source's value, unit and period"

### Requirement: The default sections ask for no inference

No default section description SHALL ask for more than summaries and comparisons of what the
sources say. The default Overview SHALL ask for the question as research understood it and the
kinds of source research covered, and SHALL NOT ask for the answer. The default Key Findings SHALL
ask for the direct answer and the values for the requested facts. The default Additional context
SHALL ask for supporting context from the sources, with one clause on how each item bears on the
answer, and for no value for a requested fact.

#### Scenario: The defaults are rendered

- **WHEN** a channel configures no report structure
- **THEN** no section description the writer and report review receive SHALL ask for what follows
  from the sources or for a bottom line the analysis supports

### Requirement: Faithful relay is verified by evals

The faithful-relay rules and the grounded review SHALL have eval coverage before they are
released. The eval SHALL cover the severe faithful-relay violations: a number no source gives, a
reversed comparison or finding, a forecast or a hedged view stated as observed, a conclusion or
cause no source states, and a figure for another scope than the source's.

#### Scenario: The severe violations are covered

- **WHEN** a change to the faithful-relay rules or the grounded review is ready for release
- **THEN** the eval SHALL have covered each kind of severe faithful-relay violation

### Requirement: Rule 9 — qualifying context stands next to its value

The rule is named "Qualifying context next to its value". It SHALL have a report-writer part only.
The grounded review judges it against that part, and the blind review's prompt SHALL carry no part
of it.

- **Report writer:**
  - For each value the report gives, gives the qualifying context that its source states. The
    writer keeps it short, and keeps its figures and conditions exact. It leaves out the
    qualifying context of values that the report does not give.
  - Gives the qualifying context of a value in the same sentence or table row as the value. When
    the same qualifying context applies to every row of a table, it MAY give it one time, in the
    table title or in a note under the table. It never gives qualifying context in a separate
    section, bullet or paragraph.
  - Does not define a measure that the query names. The exception is a query or an approved plan
    that asks for the measure's definition or methodology. Then the writer gives only what the
    sources say about it, and says so when no source gives it.
  - Does not apply the methodology of one source to a value from a different source. The exception
    is a first source that says that its methodology applies to that value.

#### Scenario: Qualifying context stands in the value's sentence

- **WHEN** a source gives a growth forecast of 2.1% "assuming no further tariff increases"
- **THEN** the writer SHALL give the condition in the sentence that gives 2.1%, and SHALL NOT give
  it in a separate paragraph

#### Scenario: A measure that the query names is not defined

- **WHEN** the query asks for the current account balance and does not ask what it is
- **THEN** the writer SHALL NOT explain what the current account balance is

#### Scenario: One source's methodology is not applied to another source's value

- **WHEN** a publication describes how it adjusts its own series, and the report gives a value from
  the dataset IMF:WEO
- **THEN** the writer SHALL NOT describe the IMF:WEO value with the publication's methodology

#### Scenario: The blind review carries no part of the rule

- **WHEN** the blind review's system prompt is rendered
- **THEN** it SHALL NOT carry the rule "Qualifying context next to its value"
