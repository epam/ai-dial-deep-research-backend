## MODIFIED Requirements

### Requirement: Report node writes the final cited report and is the only assistant content

The report node SHALL be an LLM call (with no tools) that writes the report from the original
query, the iteration plans, and the accumulated tool messages, following the citation rules
below and the composition rules of the **report-composition** capability. The same node writes
the first draft and each subsequent revision; on a revision it SHALL also receive the review's
instructions and the draft they refer to.

Citations SHALL use inline `[doc <id>, page <ix>]` for document-sourced facts and
`[dataset <id>]` for dataset-sourced facts.

**How the writer gets from a tool's attribution to those forms is owned by the
**source-attribution** capability**, and its rule bears on this prompt directly: the instructions
SHALL describe what a tool's attribution conveys — which part names the document or dataset, which
part names the page — and SHALL present any concrete spelling as one example among others. They
SHALL NOT state that the tools report attribution in one particular form, because that makes one
server's formatting load-bearing for this application while breaking no test when it changes.

**Those two forms SHALL be the only way the report references a source.** The report cites what the
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
structure includes one (the default does). How that decoding is rendered is carried by that
section's configured description, not by this requirement (see **report-composition**, which also
states what a structure configured without such a section means).

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
report may not carry, replaces each convertible citation marker with that citation's marker tag, and
leaves every other character alone (see the **report-citations** capability). That step is the single permitted transformation between the draft
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
capability's two conditions, whose deliberate consequence is that every citation left unconverted
stays fully readable in the text.

#### Scenario: Report is the assistant answer

- **WHEN** the report review loop settles on a draft
- **THEN** exactly that draft's text SHALL be appended to the assistant message content as the answer — with each converted citation's marker replaced by its marker tag, every unconverted citation marker in place as written, and a references section decoding them

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
