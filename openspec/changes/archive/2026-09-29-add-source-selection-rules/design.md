## Context

See proposal.md for the motivation. The requirements are in the change's specs: `source-selection`
owns the rule bundle, the terms, the eight rules and the amendments to the existing prompt text;
the other three deltas say where the parts reach each call.

The state of the code this design builds on:

- **The four research-graph prompts are templates in `app/research/prompts.py`**, filled once per
  turn in `app/research/nodes.py`: `RESEARCH_AGENT_SYSTEM_PROMPT` (in `build_research_agent`),
  `RESEARCH_REVIEW_SYSTEM_PROMPT` (in `make_research_review_node`), `REPORT_SYSTEM_PROMPT` (through
  `render_report_system_prompt`, in `make_report_node`) and `REPORT_REVIEW_SYSTEM_PROMPT` (through
  `render_report_review_system_prompt`, in `make_report_review_node`). `build_research_graph`
  (`app/research/graph.py`) passes each node what it needs; `ResearchRunner` (`app/research/runner.py`)
  calls it with values from `ApplicationProperties`.
- **Only `client_name` reaches the research prompts from `prompts`**, plus the data-sources string,
  which starts with `prompts.data_sources_descriptions`.
- **`report_rules.py` already bundles one kind of rule**: each `ReportRule` owns a writer
  instruction, a Python check and a violation text. Those are the rules the app checks without a
  model. The rules of this change need a model to judge, so they are prompt text only.
- **The research agent can only call tools.** `ForceToolChoiceMiddleware` forces a tool call on
  every step. Research review reads the tool calls, their results, and any text an `AIMessage`
  carries, rendered as `NOTE:` lines (`_render_findings`); with forced tool choice the model rarely
  writes such text.
- **Research review's next steps become the research agent's next plan verbatim**
  (`render_next_instruction`), so a step the agent cannot carry out, such as "summarise the
  forecasts", reaches a model that can only call tools.
- **Several texts of the existing prompts would contradict the rules.** In
  `RESEARCH_AGENT_SYSTEM_PROMPT`, the checklist asks "Is every specific number, percentage, date, or
  named entity confirmed on the page itself?", and the failed-tool exception applies to "the last
  check". In `RESEARCH_REVIEW_SYSTEM_PROMPT`, the task is "Decide whether the findings fully cover
  every item of the plans", the gaps are "genuine gaps only" in a list of three, "If every plan
  item is covered … return an **empty** `next_steps` — research is complete", and the scope
  paragraph says "only list work needed to fulfil the EXISTING plan". The `ResearchReview` field
  descriptions say "which plan items are covered" and "steps still needed to fulfil the plan";
  `with_structured_output` sends both to the model. `REPORT_SYSTEM_PROMPT`'s "These rules outrank
  the request" names the sections, the ceiling, "No links", the never-include list and the
  citation format. `REPORT_REVIEW_SYSTEM_PROMPT` says "Check exactly these", and its "Not your job"
  refers to "the checks above".
- **Where a publication's date can come from.** On a Generic RAG server a publication's date is
  document metadata, which the document listing tool returns. The listing cannot look a document
  up by id, and how it pages, orders and filters is the channel's configuration, which the tool's
  own description states. Page text can carry a date other than the publication date.
- **The data sources carry each dataset's last update**, fetched once at the start of the turn;
  when the list was shown, the research agent is told not to call the list tool.
- **`Prompts` and `ApplicationProperties` ignore unknown fields** (no `extra="forbid"`), so an older
  image reads a configuration that sets `client_rules` without failing.

## Goals / Non-Goals

**Goals:**

- One definition per rule, from which all four prompts are rendered.
- The same shape for the app's generic rules and a channel's client rules.
- No step is asked to do what it cannot, no step checks what an earlier step was not asked to
  produce, and no existing prompt text contradicts a rule.

**Non-Goals:**

- Preparation. No rule gives the preparation agent a part, and the research-review parts define
  the gaps whatever the plan says.
- The playground agent. It is not a research step and receives none of the rules.
- A second report-review call for the new checks. Many checks in one call can lower its recall;
  this change adds three, and splitting the call is left until evals show a loss.
- Retrieval changes in Generic RAG, such as a lookup by document id or a change to how a
  channel's search orders its results.
- Other quality policies. The bundle is meant for them, but only source selection is written.

## Decisions

### 1. A rule is a pydantic model with four optional parts

`QualityRule` in `app_properties.py`: `name` and four optional strings, `research_agent`,
`research_review`, `report_writer` and `report_review`, with `extra="forbid"` and a validator that
at least one part is set. The generic rules are instances of it in code; `Prompts.client_rules` is
a list of it.

Alternatives considered:

- **Four free-form client-instruction strings on `Prompts`, one per step.** Rejected: one rule's
  parts would sit in four fields, so an admin cannot see which parts belong together, and nothing
  stops one part from being updated without the others. That drift is what the bundle prevents.
- **Separate models for generic and client rules.** Rejected: two shapes means two render paths,
  and a client rule could not be written by copying a generic one.
- **Generic rules written straight into the four templates.** Rejected for the same drift: the
  parts of rule 7 would live in four places of a 790-line file.
- **Reusing `ReportRule`.** Rejected: a `ReportRule` has a Python check, and these rules have none.
  Mixing them would give most rules an empty `violations`.

### 2. The generic rules live in `app/research/source_selection.py`

The module holds `SOURCE_SELECTION_RULES`, a tuple of `QualityRule`: first "Terms", then the eight
rules, each a triple-quoted prompt string. The "Terms" rule's parts are built from one constant:
the research agent and research review get every definition, and the writer and report review get
them without "Reasonable attempt", which is about searching and about when a failed tool may be
called again, and they do neither. Its text opens by saying these are definitions, not a rule or a check, since report
review renders its block under "Source-selection checks". A later policy gets a sibling module.

Alternatives considered:

- **In `prompts.py`.** Rejected: that file holds the templates and their render functions; the
  rules are a policy with its own reason to change.
- **Terms as a separate constant each template renders.** Rejected: it is a second render path for
  text that every step gets anyway; as a rule it shares the path and the heading style.

### 3. One render function per step, two blocks per prompt

`render_rules(rules, step)` renders, for each rule with a part for `step`, `### <name>` and the
part, joined by blank lines. `step` is a `RuleStep` string enum whose values are the four field
names. Each template gets two placeholders:

- the generic block: a `## Source selection` section with one introductory sentence, a sentence
  naming the kinds of source the channel has, and the rendered generic rules. The kinds come from
  the configured servers' source kinds (a document server gives publications, a dataset server
  gives datasets), because a channel may have only one of them and the rules' parts about the
  other must not apply; the app knows the kinds, so the model is told them rather than inferring
  them from the admin's descriptions;
- the client block: empty, or a `## Client-specific rules` section with the sentence that these
  come from the channel's configuration, add to the rules above and take precedence where more
  specific, and the rendered client rules inside `<client_rules>` tags.

The client rules are tagged because they are injected configuration text, as the section
descriptions are; the generic rules are the app's own prompt text and are not.

Where each block goes, both blocks together:

- **Research agent**: after "Research strategy", before "Data sources".
- **Research review**: after the scope paragraph, before "Data sources".
- **Report writer**: after the report rules and the glossary rule, before "Data sources".
- **Report review**: after the numbered checks and before "Data sources" and "Not your job", as
  "## Source-selection checks" and "## Client-specific checks".

Alternatives considered:

- **Numbering the report-review parts after the numbered checks.** Rejected: check 7 exists only on
  a glossary channel, so the numbers would shift per channel, and the checks already refer to each
  other by number ("check 5 governs them instead").
- **Client rules mixed into the generic section.** Rejected: the admin's text would read as the
  app's, and the precedence sentence needs a boundary to refer to.

### 4. The existing prompt text is amended where it would contradict a rule

The texts listed in Context change as follows, in the same change as the rules:

- **Research agent checklist.** "Is every specific number, percentage, date, or named entity
  confirmed on the page itself?" exempts a publication's stated date, which comes from the document
  metadata. A new item asks whether every fact of this iteration's plan was researched as the
  source-selection rules ask. The failed-tool exception names the items it applies to, the
  plan-coverage item and the new one, instead of "the last check".
- **Research review.** The task sentence, the gap list (a fourth bullet: a gap the source-selection
  rules or the client rules below define), the empty-plan sentence, the scope paragraph (decision
  6), the `ResearchReview` class docstring, which `with_structured_output` sends as the schema's
  description, and both field descriptions name the rules' gaps beside the plan items. The
  docstring keeps no developer notes, since the model reads it. The existing gap "a planned
  comparison or dimension that was only partially carried out" becomes "… whose data was only
  partly retrieved", and "a figure, date or entity that appears only in a search summary" exempts a
  stated date taken from document metadata. One sentence is added: every next step is a retrieval
  the research agent can carry out with its tools, never a summary, comparison, note or
  calculation, which the report writer does from the findings. The user-facing stage text for an
  empty next plan (`utils/dial_stages.py`, "every plan item is covered, so research is complete")
  names the rules too.
- **Report writer.** "These rules outrank the request" gains the source-selection prohibitions: a
  request never makes the report average or merge differing values, leave out a value's described
  period or the stated date of a forecast or an estimate, or present a near match as an exact one.
  The dates part names exactly what rule 7's report-review part checks, because the writer gives a
  stated date only where it makes a difference and a broader "a value's dates" would contradict
  that. The rest of the rules does not outrank a request, so a user
  may still narrow what the report covers. "Do not explain in the report that you declined part of
  a request" gets one exception: a report that declines to average or merge says in one sentence
  that the values are given separately because the sources differ, so a user who asked for an
  average is not left without one and without a reason.
- **Report review.** "Check exactly these" becomes "Check exactly these, and the source-selection
  checks and any client-specific checks below".

Alternatives considered:

- **Letting the rules' text override the older text implicitly.** Rejected: a model given two
  contradicting instructions follows either, unpredictably, and the older ones come first.
- **Putting the whole source-selection block above the request.** Rejected: rule 3 adds previous
  values as context, and a user who asks for the latest figure alone should get it. Only what
  report review checks outranks the request, so the writer and report review agree on it.

### 5. The research agent's parts ask only for retrievals

No part asks the research agent to record, note, summarise or compare. Rule 7 says "make sure the
findings carry the stated date", which the agent does by calling a tool that returns it.

Alternatives considered:

- **Asking the agent to write `NOTE:` text beside its calls.** Rejected for now: under forced tool
  choice the model often writes no text. Add it only if evals show research review cannot tell
  what research looked for.
- **A `record_note` tool.** Rejected for now for the same reason; it also needs the runner to keep
  the call out of the DIAL response and out of the step count.

### 6. Research review's scope rule admits the rules' gaps

The paragraph "do not expand scope: only list work needed to fulfil the EXISTING plan … When in
doubt and the plan is substantively covered, prefer to finish" becomes: list only the work needed
to fulfil the existing plan **and the rules below**; a gap those rules define is part of the plan,
not a new angle; do not invent other angles or comparisons; when in doubt and both the plan and
the rules are substantively covered, prefer to finish. Rule 1's "reasonable attempt" bounds each
gap: a gap stays open only until the findings show one.

Rule 2's research-review part exempts a dataset value from the later-release check, because the
dataset's entry in the data sources was fetched at the start of the turn and the research agent is
told not to call the list tool again; without the exemption research review would ask for a step
the agent is told not to take. The exemption covers only that release: a fact a dataset answers
still needs a search of the publications for its latest value, because rule 2 asks for the latest
publication edition of every fact. The part says so explicitly. Worded only as "a dataset value
needs no such check", research review read it as closing the whole fact and planned no search of
the publications in a local eval run.

Rule 2 also says what counts as a check for a later value, because the eval runs showed research
review accepting weak ones. A later value can come from another publication type or series than
the one first found, such as an interim update revising an annual report's forecast, so the check
is scoped by publication date and not by the first result's type. A listing shows titles and
dates, not values, so a later listed document whose title could cover the fact is searched or read
before the fact is closed. When the latest edition does not give the value, the editions before it
are checked until one does. Each of these was a run's reason for closing research too early: a
listing filtered to one type, a later document dismissed by its title, and a latest edition that
prints no figure.

Rule 3's research-review part treats a previous value that the findings hold only as a later
edition's quote, such as "down from 1.5%", as a gap, and the research agent's part asks for the
previous edition itself. The quote carries no stated date, so the writer could not date the
previous value, and rule 7 asks for the stated date of a forecast. The part says "not in the
findings" rather than "missing", because rule 1 uses "missing" for evidence that a reasonable
attempt did not find, which is not a gap.

Alternatives considered:

- **Leaving the paragraph and relying on the rules' text.** Rejected: "only list work needed to
  fulfil the EXISTING plan" contradicts the rules' gaps directly.
- **Having preparation add the source-selection steps to the plan.** Rejected: the plan is what the
  user approves, and it would grow a fixed tail of steps on every question; the rules would also
  stop applying to facts that research finds and the plan does not name.

### 7. Publication dates come from the document listing, named by what it does

Rule 7's research-agent part describes the listing without naming the tool: the tool that lists
documents with their filterable metadata, which may return one page at a time and may not look a
document up by id. The agent lists once per research, narrowed by a publication-date filter where
the plan allows rather than by publication type, which would hide a later value of another type
(decision 6), with a limit that covers every matching document or by paging, and lists again,
without the filter or with the next page, only for a document the list misses. One entry settles a
document's date, present or absent, so the listing never loops, and research review never asks for
a separate forecast vintage or data cut-off, on which it spent extra iterations in the eval runs. A channel's
client rule names the tool, the order it lists in, the metadata key that holds the date and the
publication types, and a channel whose date is not a filterable field names another source.

Alternatives considered:

- **Naming the listing tool in the generic rule.** Rejected: the tool's name and behavior belong
  to Generic RAG and change with it, and its order and filter fields differ per channel. A client
  rule states what the channel's listing does, and is edited with the channel's configuration when
  the server changes.
- **The app fetches the metadata of every document the findings mention and injects the dates.**
  Rejected for this change: a lasting lookup of publication dates is deferred, and this option
  would add a fetch and a new input to the research calls.
- **Relying on the chunk-retrieval tool's metadata.** Rejected as the generic rule: that tool
  returns metadata only for the documents a query matches, so it cannot date a document the
  research already holds. A channel whose server returns the date there can say so in a client
  rule.

### 8. Report review judges only what the draft shows, and accepts "the sources do not give it"

Report review never sees the sources. Its rule 6 part therefore flags a range or an average
spanning two sources' values for the same fact, and two values for the same fact that the draft
presents as differing without their own citations and a reason; it does not judge whether a figure
with two citations hides a disagreement. A figure computed from values of different facts, such as
the difference between two indicators' growth rates, is outside the check: worded as "a range or
an average whose parts carry different sources' citations", the check flagged such a column as a
merge in a local eval run. Its rule 7 part names two cases the eval runs showed it getting wrong
in opposite directions: it passed a previous forecast given only as a revision's starting point
("revised down from 1.5%") without a date, and it asked to mark table values as historical
although the table's year column states their described period. Rule 1 gives report review a part: a check that asks for evidence, such as a stated
date or a reason, is satisfied by a statement that the sources do not give it. Without that part,
a date the sources lack would force revisions the writer cannot satisfy until the version budget
ran out.

Alternatives considered:

- **A report-review check against two citations on one figure.** Rejected: the writer is told to
  cite every source of a statement as a separate bracket, so two agreeing sources on one figure
  are correct, and report review cannot tell them from a merge. The writer's part keeps the
  prohibition; evals check it against the sources.

### 9. Client specifics go into client rules, not into the generic text

A ban on some content, such as a topic a channel's reports must leave out, is not part of the
definition of methodology, so the generic "Terms" rule carries none, and a channel that needs one
carries it in a client rule. The same holds for what a channel's datasets document, whether they
keep earlier releases, where its publications document their methodology, which metadata key
holds a publication's date, and which tool lists the documents. The generic examples are
domain-neutral.

### 10. The length violation asks to condense only

`_LENGTH_VIOLATION` (`report_rules.py`) says "cut detail". It becomes "state the same content more
concisely — tighten prose, merge overlapping passages; keep every value with its citation and its
dates, unless another item of this list asks to change it". The exception matters because one
revision instruction merges every violation, and `_QUERY_WITHOUT_DATA_VIOLATION` can ask to drop a
statement. The writer's `_LENGTH_INSTRUCTION` already says "condense and rewrite" and stays.

### 11. Research review and report review reason before their verdict

Both review calls run the default chat model with reasoning effort `medium`; the research agent
and the writer keep none. Without reasoning, research review closed research on a listing or on a
document's title although the rule text named that case, and report review passed drafts that
broke the dates checks and misread a year column as a missing period. With reasoning, research
review asked for the later editions the rules require, and, once rule 8 had its part (decision 12),
the near matches; report review caught uncited sentences it had missed. Before reasoning, most
runs used up a loop budget; after it, most did not. Questions with many sources still use up the
report loop's budget, because report review then finds more real violations than two revisions
can fix. Report review still misses some dates violations, such as an estimate dated only by a
title that contains a year.

Alternatives considered:

- **More prompt wording alone.** Tried first: each round of wording fixed the case it named, and
  the model found another reason to close research early.
- **Reasoning for all four calls.** Rejected for now: the research agent's calls are many and
  forced to call a tool, so reasoning would multiply cost and latency where the evals showed no
  judgement failure; the writer's failures are the calculation and inference rules of other
  policies.
- **Splitting report review into several calls, or giving it the findings.** Left for later: both
  change the call's inputs and its budget, and reasoning alone moved the checks this change adds.
- **A configurable reasoning effort per call.** Left for later: a code constant keeps this change
  to the rules; a property can follow when a channel needs another value.

### 12. Rule 8 gains a research-review part

Without a research-review part for rule 8 (no exact match), research review did not ask for near
matches in the eval runs, and the reports named near matches without giving their values. The part
makes a fact with no exact match, and no search for its nearest matches
by scope, geography or period, a gap. Unlike rule 6's search for further sources, a search for the
nearest matches has a natural end: the smallest region that contains a country, or the nearest
years. After the part was added, research review asked for the nearest matches and the reports
gave their values.

## Risks / Trade-offs

- [More tool calls and more cost per turn: every fact now gets a search of the publications, even
  one a dataset answers, a check for a later edition, a previous value, a dataset query and a
  methodology search.] → The evals measure cost, tool calls and research iterations. Rule 1
  bounds each search to a reasonable attempt, rule 3 asks for a previous value only where it gives
  context, and research review may not ask for an open-ended search for disagreeing sources.
- [A document listing of a whole corpus is a long tool result, carried in every later research-agent
  call and in the writer's transcript.] → The rule asks for a metadata filter where the plan allows,
  and prompt caching serves the repeated prefix. The evals' peak input tokens show the effect.
- [Research review keeps asking for the same check because it cannot see that research looked for
  it.] → Rule 1 defines a reasonable attempt as two searches, which the findings show as tool calls.
  The evals showed one repeated ask of this kind: research review receives no images, so it asked
  again for a page whose value is printed only in the page image. If this recurs, add the note
  mechanism of decision 5's alternatives.
- [Reasoning makes the two review calls slower and dearer (decision 11).] → They are two calls per
  iteration or draft, against many research-agent calls; the evals' execution time and cost show
  the effect.
- [Rule 2's date-scoped listing can return most of a corpus when the agent picks a wide range.] →
  The evals' peak input tokens show it; the client rule asks for a date range, and the listing is
  made once per research.
- [Three more checks in one report-review call lower its recall on the older ones.] → The evals'
  output checks cover the older ones; split the call only if they regress.
- [A longer report pushes past the word ceiling, and the length revision drops values.] → Decision
  10 forbids dropping a fact in the violation text itself.
- [Obviously outdated and "gives context" are judgements.] → Their conditions are checkable from
  the findings, and the term forbids the model's own knowledge.
- [A channel without a client rule naming its listing tool and date key.] → The generic rule
  describes the tool by what it does, which the tool's own description matches; the evals run on a
  channel that has the client rule.

## Migration Plan

- A channel gets the generic rules with the new image; nothing in its configuration has to change.
- A channel adds client rules by setting `prompts.client_rules`. The DIAL application-type schema
  generated from the model shows the new field.
- Rollback: an older image ignores `client_rules`, so a configuration that sets it keeps working.

## No changes required

- `dial_conf/core/applications-template.json`: `client_rules` has a default, so the template, which
  sets exactly the required properties, stays as it is.
- The README environment-variables table: no environment variable changes.
- The preparation prompts (`app/preparation/`) and the playground agent (`app/playground/`): see
  Non-Goals.
- `report_rules.py`, apart from the length violation's wording: the new rules have no Python check.
- The citation, References and data-sources code: the rules change what the models are told, not
  what the app parses, fetches or builds.
