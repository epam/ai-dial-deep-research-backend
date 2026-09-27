## MODIFIED Requirements

### Requirement: Every research LLM call's inputs and outputs are specified

The research graph makes four kinds of LLM call, one per node. Each one's inputs SHALL be exactly
what is listed here — nothing else reaches a model, and adding an input SHALL require updating
this requirement. Where a call deliberately omits something another call receives, the omission
is part of the contract, not an accident of implementation.

**1. research-agent** (one call per agent step)

- System prompt: the research-agent instructions, filled with today's date, the instance's
  `client_name`, and the turn's data-sources string in a `<data_sources>` block: the instance's
  `data_sources_descriptions`, followed by the datasets section when the channel has a dataset
  server and by the rendered glossary when the channel configures one (see
  **data-sources-discovery**). They state when to announce a step with `update_status`, and the
  rules that it is called at most once per assistant message, never as a message's only tool call,
  and never together with `finish_iteration`. When the glossary's list failed or some of its terms
  did not resolve, they also carry the instruction to repeat what the app's glossary fetch missed,
  with at most three calls, each part only when its tool is bound. On a channel with a dataset server, they also
  carry the instruction that says, for each bound dataset tool, whether the app's own calls
  succeeded: the agent does not call a tool again for an answer the datasets section shows, and
  calls it when the app's calls failed, with at most three calls (see **data-sources-discovery**).
- Messages: the graph's accumulated `messages` — the seed instruction (the aligned query and the
  approved plan), every `AIMessage` and `ToolMessage` of the turn so far **including image
  content blocks**, and each research-review-injected next-plan instruction. Image blocks are
  subject to the image budget (see **image-budget**), which may have substituted the newest
  image-carrying results with error messages. This call is the only one that receives its own
  `update_status` calls and their acknowledgements.
- Tools bound: the MCP-loaded tools plus `finish_iteration` and `update_status`, with forced tool
  choice.
- Output: tool calls only — never free-form text.

**2. research-review** (one call per completed iteration)

- System prompt: the research-review instructions, filled with today's date.
- Messages: one human message carrying the original query, the rendered findings, and the plans
  pursued so far. The findings rendering carries the instructions given, the name and arguments
  of every tool call, any notes research-agent wrote, and the **text** of every tool result.
- **Images are NOT included**: an image-carrying tool result is rendered with a marker noting an
  image was returned, and the image itself is omitted. This call therefore judges coverage
  without seeing what research-agent saw in charts, tables, and figures.
- **The status announcements are NOT included**: `update_status` calls and their acknowledgements
  are removed before the findings are rendered, so no announced status appears among the tool
  calls this call weighs when judging coverage.
- System prompt, additionally: the turn's data-sources string in a `<data_sources>` block, the
  same string research-agent receives, so the next-iteration plan this call writes points at the
  data sources that exist.
- Output: a structured verdict — the assessment, then the next-iteration steps (empty means
  research is complete).

**3. report** (one call per draft: the first, and each revision)

- System prompt: the report instructions, filled with today's date — the configured section
  structure, the protected sections, the word ceiling, the prohibited meta-annotations, the
  citation rules, and the rule that a source is referenced only by an inline citation form and
  never by a hyperlink (see **report-composition**) — and the turn's data-sources string in a
  `<data_sources>` block, the same string research-agent receives. On a channel that configures a
  glossary, they also carry the rule that the report uses the glossary's terminology, whether or
  not the app's glossary fetch succeeded (see **report-composition**). They carry no instruction to request missing definitions, because this
  call has no tools.
- Messages: the accumulated `messages` transcript **including images** (already clamped by
  the image budget) with the `update_status` calls and their acknowledgements removed, then the
  report request carrying the aligned query and the plans pursued. Removal is deterministic, so
  successive report calls in a run still share a byte prefix (see **prompt-caching**).
- **The status announcements are NOT included**: what research told the user it was doing is not
  evidence, and SHALL NOT reach the model that writes the report.
- On a revision, additionally: the draft being revised, the revision instruction, and the draft's
  measured word count alongside the ceiling. The instruction is the review step's findings, the
  app-rendered length direction when the count forced the revision, or both merged — a revision is
  never issued without one (see **report-composition**). These SHALL be **appended after** the
  original report request rather than replacing it, so the byte prefix is unchanged and the
  provider's prompt cache can serve it (see **prompt-caching**).
- Tools bound: none.
- Output: the report text. It is not streamed to the assistant content (see the report-node
  requirement below).

**4. report-review** (one call per draft)

- System prompt: the report-review instructions, filled with today's date — what to check and what
  not to — and the turn's data-sources string in a `<data_sources>` block, the same string
  research-agent receives. When the glossary fetch listed at least one term, or research-agent
  obtained a successful glossary tool result, the checks include the glossary-terminology check
  (see **report-composition**).
- System prompt, additionally, on a channel that configures a glossary: the text of every
  **successful** result of the two configured glossary tools (the list-terms tool and the
  term-definitions tool) that research-agent obtained during the turn, in the order they were
  obtained, in a `<glossary_tool_results>` block. The app selects them from the transcript by the
  configured tool names, and passes their text as the server sent it, without parsing it. A result
  marked as an error is left out. The block is absent when there is no such result. This is the one
  kind of tool result this call receives: it is the glossary the check judges against when the
  app's own fetch missed terms or definitions.
- Messages: one human message, assembled **stable content first** so successive review calls in a run
  share a byte prefix (the same rule as research-review's assembly, see **prompt-caching**): the
  configured report structure with each section's description, the protected sections, the aligned
  research question, and **the approved preparation plan only** — the plan list's first entry,
  since later entries are authored by research-review rather than the user and cannot carry a
  user's formatting instruction. The draft comes **last**, being the only part that differs between
  the calls of one run.
- **Neither the measured word count nor the ceiling is included**, and the message tells this call
  that the app checks the headings, the length and the hyperlinks itself. None of the three is
  its to judge: the app checks the draft and adds their violations on its own (see
  **report-composition**).
- **The research findings are NOT included** — no transcript, no tool results other than the
  glossary tool results above, no images, and so no status announcements either. Every criterion this call judges is decidable from the draft, the
  configuration, the query and plan, and the data-sources string.
- Output: a structured verdict — one list of report violations, where an empty list is the
  approval. There is no separate approval field, so a remark the model does not want acted on
  cannot be expressed and forces a revision instead.

#### Scenario: research-review judges coverage without the images

- **WHEN** research-agent fetched a page in image mode and research-review runs afterwards
- **THEN** the review call SHALL receive a marker recording that an image was returned and SHALL
  NOT receive the image content itself

#### Scenario: report-review sees the draft but not the findings

- **WHEN** report-review judges a draft
- **THEN** its input SHALL contain the draft, the configured structure, the protected sections, the
  query and plan, the data-sources string, and the research agent's successful glossary tool
  results when there are any, and SHALL NOT contain any other tool result, any transcript message,
  image, measured word count, or ceiling

#### Scenario: A revision's prompt extends the draft's prompt

- **WHEN** the report node writes a revision after a first draft
- **THEN** the revision call's messages SHALL begin with the same system prompt, transcript, and
  report request as the first draft's, with the draft, the instructions, and the counts appended
  after them

#### Scenario: Status announcements reach research-agent but no other call

- **WHEN** research-agent has announced several steps with `update_status` during an iteration
- **THEN** research-agent's own next call SHALL still receive those calls and their
  acknowledgements, while research-review's rendered findings and the report call's transcript
  SHALL contain neither the calls nor the acknowledgements nor any announced status text

#### Scenario: Removing a status leaves the rest of its message intact

- **WHEN** one assistant message carried `update_status` alongside research tool calls, and that
  transcript is prepared for research-review or the report node
- **THEN** the research tool calls of that message SHALL be preserved with their results, and only
  the `update_status` call and its acknowledgement SHALL be removed, leaving every remaining tool
  call paired with its result

#### Scenario: Every research graph call receives the data-sources string

- **WHEN** a research turn runs on a channel whose glossary listed terms
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the same data-sources string, ending in the rendered glossary

#### Scenario: A channel without a glossary still gives research the topics map

- **WHEN** a research turn runs on a channel that configures no glossary and has no dataset server
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the instance's `data_sources_descriptions`, and no prompt of the
  research graph SHALL carry a datasets section, a glossary or the glossary-terminology rule

#### Scenario: Every research graph call receives the datasets section

- **WHEN** a research turn runs on a channel with a dataset server that configures no glossary
- **THEN** the system prompts of research-agent, research-review, the report call and
  report-review SHALL each carry the instance's `data_sources_descriptions` followed by the same
  datasets section, and only research-agent's SHALL carry the instruction about the dataset
  tools

### Requirement: Report node writes the final cited report and is the only assistant content

The report node SHALL be an LLM call (with no tools) that writes the report from the original
query, the iteration plans, and the accumulated tool messages, following the citation rules
below and the composition rules of the **report-composition** capability. The same node writes
the first draft and each subsequent revision; on a revision it SHALL also receive the review's
instructions and the draft they refer to.

Citations SHALL use inline `[doc <id>, page <ix>]` for document-sourced facts,
`[data_query <id>]` for facts drawn from a data query, and `[dataset <urn>]` for facts about a
dataset as a whole that no data query produced — such as when a dataset was last updated, or what
it covers. **Every fact drawn from a data query SHALL be cited `[data_query <id>]`**, never
`[dataset <urn>]`, even though the query's result names its dataset too: the query citation is the
one that opens the cited data, and the dataset it ran against still reaches the References section
through it (see **report-citations**).

**On a channel that configures a glossary, a fact taken from a glossary definition SHALL be cited
`[glossary <term>]`**, where `<term>` is the term as the glossary spells it: for example
`[glossary Primary Commodity Prices]`. The glossary is the one the report writer is shown, in its
data-sources string, and the terms and definitions the research obtained with the glossary tools.
The marker is written like the other three and reviewed like them; before delivery the app moves
the glossary markers of each run of adjacent citations to its end and rewrites them into one readable
group, `(<term> - glossary term)` for one term, with no pill, and lists the cited terms
in the References section's glossary table (see **report-citations**). It counts as an inline
citation wherever the report's rules speak of inline citations, such as the word count. On a channel
without a glossary the form SHALL NOT be offered to the writer.

**What identifies a source in each form is part of this contract**, not a detail left to the
writer, because the app parses these markers and resolves what it finds back against the server
that reported it. The instructions SHALL state each:

- A **document** is referenced by its **document id and the index of the cited page** — two values,
  both required. A document citation without a page is not a weaker citation but an unparseable
  one, because a document server attributes at page level and the reader is scrolled to that page.
- A **dataset** is referenced by its **URN**, the identifier the dataset server reports for that
  dataset, written whole. A URN carries punctuation — typically a colon, and often a parenthesised
  version — and every character of it is part of the identifier, so it SHALL NOT be abbreviated,
  case-changed, percent-encoded, or stripped of its version. The **source-attribution** capability
  owns why: the identifier is sent back to the server, and a transformed one resolves nothing.
- A **data query** is referenced by its **query id**, the identifier the data-query tool reports
  for that query in its result, written whole. It SHALL NOT be abbreviated, case-changed or
  replaced by the dataset's URN or name.
- A **glossary term** is referenced by its **name as the glossary spells it**, written whole after
  the keyword `glossary`: `[glossary <term>]`. The `<term>` slot accepts any run of characters other
  than a bracket or a line break, the way the data-query id slot does, so a term containing a square
  bracket cannot be cited.

**Only a data query that returned data SHALL be cited.** A data-query tool also reports ids for
queries that returned nothing: a query it constructed and did not execute, the query it offers for
each candidate dataset when it asks for a dataset to be selected, and an executed query whose
result was empty. The instructions SHALL tell the writer never to cite such an id, because such a
query backs no value, so no fact can come from it. Whether a query's result carries a data explorer
link is not the writer's concern: the writer does not see the link, and a missing one costs the
citation its pill and nothing else (see **report-citations**). The app also checks every draft's
query ids against what the turn captured and asks for a revision when one breaks this rule
(**report-composition**), but the instruction is what keeps a first draft right.

Naming these is what separates the citation forms from a formatting convention. The writer cannot infer
from the shape of a marker which values belong in it, and a writer that puts a dataset's display
name where its URN belongs, or omits a page from a document citation, produces a citation that
parses into nothing and silently loses its pill.

**How the writer gets from a tool's attribution to those forms is owned by the
**source-attribution** capability**, and its rule bears on this prompt directly: the instructions
SHALL describe what a tool's attribution conveys — which part names the document or dataset, which
part names the page — and SHALL present any concrete spelling as one example among others. They
SHALL NOT state that the tools report attribution in one particular form, because that makes one
server's formatting load-bearing for this application while breaking no test when it changes.

**Those forms — the three markers, and the glossary form on a channel that configures a glossary —
SHALL be the only way the report references a source.** The report cites what the
research retrieved and nothing else, so it SHALL carry no hyperlink in any form. Which forms count,
what the writer is told, what the app checks and what is removed before delivery are owned by the
**report-composition** capability.

**The inline citation format SHALL NOT be configurable, per instance or otherwise.** It is not a
style choice but a machine-readable interface: the app parses these markers out of the delivered
report to build DIAL inline citation annotations from them, and the glossary form to build the
References section's glossary table (see the **report-citations** capability), so a deployment that
emitted a different form would break that step rather than merely look different. Every report from every instance therefore carries the same inline form,
and only a change to this requirement may change it.

Every cited source SHALL be decoded in the report's references section, whenever the configured
structure includes one (the default does). **The report node SHALL NOT write that section**: the
app builds it after the loop settles, from the metadata the servers reported about the sources the
delivered report actually cites (see **report-citations**). The writer is given the other sections
only, and what a row holds comes from configuration rather than from this requirement (see
**application-config-schema**).

The delivered report SHALL be the **only** node output that becomes the user-visible assistant
message content. A draft SHALL NOT reach the assistant content while the report review loop is
still running: the content SHALL be appended once, after the loop settles on the draft to
deliver. Research-agent reasoning, research-review structured output, and report-review
structured output SHALL NOT be appended to the assistant content; research-agent tool calls SHALL
surface as DIAL stages, and report-review's findings SHALL surface as a DIAL stage of their own (see
**report-composition**). Not being assistant content does not mean being invisible: the stage channel
carries what the user needs to see about how the answer was produced. A blank-line separator SHALL precede the report only when text was already streamed
into the assistant content earlier in the same turn.

What is appended is the settled draft **after the citation step**, which removes the hyperlinks the
report may not carry, replaces each convertible citation marker with that citation's marker tag,
appends the References section, and leaves every other character alone (see the **report-citations**
capability). That step is the single permitted transformation between the draft
the review settled on and the text the user reads; nothing else may alter a settled draft, and the
annotations it emits SHALL be the only other thing the app adds to the message alongside that text.

**The report SHALL be delivered as assistant message content, never as an attachment.** A citation
pill is drawn only inside the assistant message bubble, where the client injects it while rendering
that message's Markdown; an attachment opened in the client's side canvas is rendered by a path that
resolves no annotations. A report moved into a `text/markdown` attachment would therefore show as
plain text with no pill anywhere, and the annotations, which name marker tags standing in the
message text, would have nothing to anchor to.

The delivered content therefore carries markup a reader's client is expected to resolve: a client
that understands the marker tags renders a pill for each, and one that does not either drops a tag
or shows it. A converted citation's readable text lives in its annotation rather than in the report
text, so a client that discards the annotations loses that citation rather than degrading to a
visible marker. Which citations are converted at all is decided by the **report-citations**
capability's conversion conditions, whose deliberate consequence is that every citation left unconverted
stays fully readable in the text — and the References section lists every cited source whether or
not its citations converted, naming in text every source whose citations did not, so an unconverted
marker still resolves to a named source. A source whose citations converted is named in its
References row by a pill, on the same condition, so a client that discards the annotations loses
that row's name exactly as it loses the source's inline citations.

#### Scenario: Report is the assistant answer

- **WHEN** the report review loop settles on a draft
- **THEN** exactly that draft's text SHALL be appended to the assistant message content as the answer — with each converted citation's marker replaced by its marker tag, every unconverted citation marker in place as written, and the app-built references section decoding them

#### Scenario: The writer is not asked to write the references section

- **WHEN** the report writer's prompt is rendered from the configured structure
- **THEN** no references section SHALL appear among the sections the writer is told to write, the
  prompt SHALL state that the application appends that section itself, and a draft that writes one
  anyway SHALL be reported as a structure violation (see **report-composition**)

#### Scenario: An unfamiliar attribution spelling still yields correct markers

- **WHEN** a tool message attributes a fact in a labelled form the writer's instructions never named,
  such as `[Document 207, Page 1]` where the examples showed another spelling
- **THEN** the draft SHALL cite that fact as `[doc 207, page 1]`, because the instructions describe
  what the attribution conveys rather than the characters one server writes it in

#### Scenario: Drafts under review are not visible

- **WHEN** the first draft is rejected by the report review and a revision is written
- **THEN** the rejected draft SHALL NOT appear in the assistant message content, and the user SHALL see only the draft the loop finally delivers

#### Scenario: Research-agent and review output are not the answer

- **WHEN** research-agent emits reasoning alongside tool calls and research-review and report-review emit their structured verdicts
- **THEN** none of that text SHALL appear in the assistant message content; research-agent's tool calls SHALL appear only as DIAL stages

#### Scenario: No leading separator when the report is the whole answer

- **WHEN** a turn's preparation stage streamed no assistant text before research started
- **THEN** the assistant message content SHALL begin with the report's first character, with no leading blank line

#### Scenario: The writer is told what identifies each kind of source

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that a document is referenced by its document id and cited page index,
  and that a dataset is referenced by its URN written whole, with its punctuation and version intact

#### Scenario: A data-query fact is cited by its query id

- **WHEN** a data-query tool reports a query whose id is `dq_0123abcd45`, run against the dataset
  `IMF:WEO(1.0.0)`, and the report states a value from that query's data
- **THEN** the report SHALL cite the value as `[data_query dq_0123abcd45]`, and SHALL NOT cite it as
  `[dataset IMF:WEO(1.0.0)]`

#### Scenario: A statement about a dataset as a whole cites the dataset

- **WHEN** the report states when a dataset was last updated, taken from the dataset catalogue
  rather than from a data query
- **THEN** the report SHALL cite that statement as `[dataset <urn>]`

#### Scenario: A candidate dataset's query is never cited

- **WHEN** a data-query tool result asks for a dataset to be selected and lists two candidate
  datasets, each with a query id, and runs no query
- **THEN** the report SHALL cite neither id, and SHALL state no value as drawn from either query

#### Scenario: The writer is told to cite only queries that returned data

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that only a data query that returned data is cited, and that the ids of
  candidate queries, of queries that were not executed, and of queries that returned nothing are
  never cited

#### Scenario: The writer is told what identifies a data query

- **WHEN** the report writer's citation instructions are read
- **THEN** they SHALL state that a data query is referenced by the query id the tool reported,
  written whole, and that every fact drawn from a data query is cited that way

#### Scenario: A dataset's display name is not its reference

- **WHEN** a dataset-query tool reports a dataset with both a human name and a URN
- **THEN** the instructions SHALL direct the writer to cite the URN, and the report SHALL carry the
  URN in the marker rather than the name

#### Scenario: A glossary definition is cited with the glossary marker

- **WHEN** a channel configures a glossary, and the report states what a glossary term means, taken
  from the glossary's definition of `Primary Commodity Prices`
- **THEN** the writer's instructions SHALL have it cite `[glossary Primary Commodity Prices]`, and
  the delivered text SHALL carry `(Primary Commodity Prices - glossary term)` in its place

#### Scenario: A channel without a glossary is not offered the glossary form

- **WHEN** a report is written on a channel that configures no glossary
- **THEN** the writer's instructions SHALL NOT mention the glossary citation form
