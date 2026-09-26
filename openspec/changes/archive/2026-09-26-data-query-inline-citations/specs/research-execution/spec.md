## MODIFIED Requirements

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

**Only a data query that returned data SHALL be cited.** A data-query tool also reports ids for
queries that returned nothing: a query it constructed and did not execute, the query it offers for
each candidate dataset when it asks for a dataset to be selected, and an executed query whose
result was empty. The instructions SHALL tell the writer never to cite such an id, because such a
query backs no value, so no fact can come from it. Whether a query's result carries a data explorer
link is not the writer's concern: the writer does not see the link, and a missing one costs the
citation its pill and nothing else (see **report-citations**). The app also checks every draft's
query ids against what the turn captured and asks for a revision when one breaks this rule
(**report-composition**), but the instruction is what keeps a first draft right.

Naming these is what separates the three forms from a formatting convention. The writer cannot infer
from the shape of a marker which values belong in it, and a writer that puts a dataset's display
name where its URN belongs, or omits a page from a document citation, produces a citation that
parses into nothing and silently loses its pill.

**How the writer gets from a tool's attribution to those forms is owned by the
**source-attribution** capability**, and its rule bears on this prompt directly: the instructions
SHALL describe what a tool's attribution conveys — which part names the document or dataset, which
part names the page — and SHALL present any concrete spelling as one example among others. They
SHALL NOT state that the tools report attribution in one particular form, because that makes one
server's formatting load-bearing for this application while breaking no test when it changes.

**Those three forms SHALL be the only way the report references a source.** The report cites what the
research retrieved and nothing else, so it SHALL carry no hyperlink in any form. Which forms count,
what the writer is told, what the app checks and what is removed before delivery are owned by the
**report-composition** capability.

**The inline citation format SHALL NOT be configurable, per instance or otherwise.** It is not a
style choice but a machine-readable interface: the app parses these markers out of the delivered
report to build DIAL inline citation annotations from them (see the **report-citations**
capability), so a deployment that emitted a different form would break that step rather than
merely look different. Every report from every instance therefore carries the same inline form,
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
