## Context

See `proposal.md` — Why for the motivation. This section carries only the facts that shape the
approach; each was read out of the relevant source rather than inferred.

**Where the report is delivered today.** `ResearchRunner.run` drives the research graph with one
`astream`, keeps the last root-state `values` part, and then `_deliver_report` appends
`state["report"]` to the DIAL choice and adds it to the message slice the coordinator persists.
Nothing is streamed token by token: a draft may still be revised, and DIAL content is append-only,
so the report reaches the choice once, after the graph has finished
(`src/dial_deep_research/app/research/runner.py`).

**How the report cites.** The report prompt fixes two inline forms, `[doc <id>, page <ix>]` and
`[dataset <id>]`, and tells the writer to translate the retrieval tool's compact `[(207, 1)]`
tuples into the first (`app/research/prompts.py`). The document id is the retrieval server's own
document id — for the Generic RAG implementation, `RetrievedDocument.source_id`, which is
`Document.id` — and the page is a 1-based PDF page number, assigned by the page extractor as
`enumerate(pdf.pages, start=1)`. So both halves of a marker are already the values the
file-sharing tool and the PDF viewer need, with no translation.

**How DIAL Chat renders a citation.** Read from `epam/ai-dial-chat`, branch `development` once
pull requests #8560 (2026-09-08) and #8681 (2026-09-09) had merged, in `libs/quotations`,
`libs/chat-shared` and `libs/chat-hooks`:

- An annotation says where its pill belongs in one of two ways. The older way is a
  `text_character_range` selector holding a character offset into the message. The newer way, which
  this design uses, is an `html_tag` selector naming a marker tag the producer put in its own text:
  `{type: 'html_tag', tag: 'cit', id}` matching a `<cit data-id="…">` tag. Note the asymmetry: the
  selector's field is `id`, the tag's attribute is `data-id`.
- The one markup shape the client interprets is the pair `<cit data-id="…"></cit>`, matched in
  `citation-injection.ts`. Every other `cit` shape — an unpaired tag, one written with `id` instead
  of `data-id`, a fragment still arriving mid-stream — is escaped by `escapeUnsupportedCitTags` and
  shown to the reader as literal text. The attribute is `data-id` and not `id` because
  `rehype-sanitize`'s default schema rewrites `id` to `user-content-…` to prevent DOM clobbering,
  while `data-*` attributes are exempt from that rewrite.
- `groupAnnotationsByCitId` groups tag-anchored annotations **by tag id** — one group per id, and
  `groupAnnotations` concatenates those with the URL-grouped ones. The producer therefore controls
  grouping outright: two ids never merge even when they cite the same document, and several
  annotations sharing one id form one group deliberately. One pill is drawn per group.
- `CitationDropdown` renders one `CitationMarker` per group, labelled from
  `body.source.attachment.title` (falling back to the URL's last path segment, percent-decoded, then
  its hostname), and `body.title` labels the entry inside the popup.
- A marker tag reaches the rendered tree as a real element: `MarkdownRenderer` allow-lists `cit`
  and its `data-id` attribute through `rehype-raw` and `rehype-sanitize`, and
  `useCitationMarkdownComponents` registers a `cit` component override that looks the group up by
  that attribute. The override is keyed by tag name alone, with no Markdown context in it, so a tag
  draws its pill wherever the parser puts an element — a paragraph, a list item, a table cell, a
  heading, a blockquote. The hook's `p` and `li` overrides serve the older offset-anchored
  citations only.
- `resolveMessageAnnotations` reads `custom_content.annotations` when non-empty and keeps only
  entries carrying `body.source.attachment.url`; a flat `body.source = {type, url}` is valid only in
  the other container, `custom_fields.annotations`, which is normalized into the same internal shape
  with `body.selector` and any supplied `index` retained. A producer that streams its own response
  writes the nested shape directly.
- `annotationToPdfCanvasContent` (`libs/chat-hooks/src/files/attachment-canvas.ts`) opens the cited
  PDF and sets the page to navigate to from the clicked annotation's own `body.selector`, taking the
  first `pdf_bbox` entry whose `page` is an integer of at least 1. The page travels in
  `PdfCanvasContent.page`, independently of whether a highlight can be drawn, so a zero-area box
  navigates and draws nothing. The annotation the user selected in a grouped popup is the one read,
  never the group's first.

Three consequences shape this design: the producer chooses the anchor position by placing a tag, so
no offsets are involved; a pill is drawn wherever the Markdown parser parses the tag, so the step
needs no rule about which block a citation may stand in; and a tag no annotation claims is shown to
the reader as text, so a missing annotation costs its citation and leaves the tag visible where it
stood.

**The second reader is the same renderer.** The DIAL overlay (`libs/chat-overlay`,
`@epam/ai-dial-chat-overlay`, replacing the legacy `@epam/ai-dial-overlay`) embeds a deployed
`apps/chat` in an iframe and talks to it over `postMessage`; it does not render messages itself. So
the rendering constraints above hold once for both intended readers, and the overlay needs no
producer-side work of its own.

**Why the cited file must be copied.** The spike's finding F1: DIAL Core grants a normal user
session access only to resources under that user's own bucket (`AccessService.java`), and Core's
response-attachment auto-sharing grants an ephemeral per-request key rather than the user's session,
which expires long before the user clicks a citation. The sanctioned route is the caller's `appdata`
folder, resolved from `GET /v1/bucket` with the per-request key. The retrieval server does that copy
itself and returns the destination path; for the Generic RAG implementation `copy_file_to_user`
compares etags first and skips the transfer when the copy is already current, so a repeated citation
costs two metadata calls.

**What one real file-sharing tool returns.** Measured against a running Generic RAG instance,
reached through DIAL Core's deployment endpoint, by calling its file-sharing tool over MCP with two
document ids — one indexed and one that does not exist. The **report-citations** capability states
the contract the app depends on; what follows is the evidence behind it and a demonstration that one
real server satisfies it, not a further demand on the next server:

- The tool advertises an output schema of `{"type": "object", "additionalProperties": {"type":
  "string"}}`, and its input is the single `document_ids` array of integers the contract names.
- The result populates **both** the MCP `structuredContent` field and a single `text` content block,
  and the two parse to the same JSON object. There is no wrapper key: the object is the mapping
  itself. Its keys are the document ids as JSON strings, because JSON has no integer keys.
- Each value is a DIAL file URL **relative to the storage root** — it begins `files/` and carries
  no scheme and no host — of the form
  `files/<bucket>/appdata/<deployment-id>/<folder>/<file>.pdf`. Segments are percent-encoded, so a
  file name containing a space arrives carrying `%20`.
- The id that does not exist is simply **absent** from the mapping, and the call still succeeds
  (`isError` false). Partial answers are the server's real behaviour, not just a tolerance the
  contract asks for.
- The `<bucket>` of the returned path is the **caller's own** bucket: it matches the bucket that
  `GET /v1/bucket` reports for the api-key that made the call. So the copy is readable by the
  identity that asked for it, which is the whole point of the tool.
- That same `GET /v1/bucket`, called with an ordinary api-key, returns **only** `bucket` and no
  `appdata` field. The `appdata` path exists solely for a per-request key issued to a deployment,
  which is why a file-sharing tool reached outside deployment mode cannot resolve a destination at
  all — `copy_file_to_user` raises rather than guessing one.

**What the spike already proved.** The `annotations-spike` branch of this repository
(`src/dial_deep_research/app/annotations_spike/`, not merged) emitted an offset-anchored payload for
a fixed report and confirmed, logged in as a real end user: pills render inline, the zero-size
`pdf_bbox` scrolls the viewer to the named page and draws nothing, `index` survives the streaming
path, and the page never comes from the URL. Everything it validated about the annotation **body**
carries over unchanged; only how the pill's position is expressed differs.

**One thing the spike's report did not have.** Its fixed text was headings and paragraphs only. A
real report carries tables, bullets and emphasis, so the demo covers those placements and a real
report is the case that checks them at length.

## Goals / Non-Goals

**Goals:**

- One pill per cited position, anchored where the citation stood, opening the cited page of a file
  the reader can actually read — and one pill, not a row of them, where a statement cites several
  sources at once.
- Deep Research depends on a tool contract, so the retrieval server can be replaced without
  re-deriving the citation mechanism.
- The report the review loop settled on is otherwise untouched, and no citation problem can cost a
  finished report.
- The parsing, the eligibility conditions, the tag replacement and the payload are testable without
  DIAL, an MCP server, or a model.

**Non-Goals** (beyond the proposal's scope statement):

- Highlighting the cited passage inside the PDF. The zero-size `pdf_bbox` is deliberate; a real
  bounding box would need the retrieval server to return coordinates.
- Making a citation resolvable outside the turn that produced it. The copy lands in the reader's own
  bucket and stays there, but nothing in this change re-copies a document whose copy a user deleted.
- Changing what the report writer or the report review does. The prompts, the ceiling, and the
  review loop are untouched, so a citation that cannot become a pill is a rendering fact, not a
  writing rule.

## Decisions

### D1. The citation step runs in the research runner, after the graph, not as a graph node

The step needs the DIAL choice, to append the post-processed text to and to emit annotations on, and
it must run exactly once, on the settled draft, after the loop can no longer change it.

- *A node inside the research graph* — rejected. It would put an MCP tool call inside the graph's
  step budget (`recursion_limit`), where a citation failure would interact with `GraphRecursionError`
  handling, and it would still have to hand the payload out to the runner to emit. The graph owns
  research and report decisions; delivery is the runner's.
- *Inside the report node* — rejected: a draft written there may still be revised, so the step would
  run once per version and waste the copies of an unpublished draft.
- *In `completion.py`* — rejected: the report and its delivery already live in `ResearchRunner`, and
  the coordinator would need the graph state to do the work.

The runner therefore orchestrates, and everything decidable from strings lives in a new
`app/research/citations.py` with no DIAL or LangChain imports.

### D2. Two independent conditions decide whether a citation becomes a pill

The rule is in the spec (**report-citations**); it is a decision rather than a detail because the
condition is what makes the step predictable, and because earlier cuts of it carried tests that were
not independent. One condition: the cited document has a URL from the file-sharing tool and that
file is a PDF — which is also the reason a dataset never qualifies, since it is not a file. A
citation failing it keeps its `[doc <id>, page <ix>]` text. Where in the Markdown the marker stands
is not a condition, because the client draws a pill wherever it parses the tag.

An earlier cut carried a third condition — that the bracketed text is a citation rather than a
Markdown link label. It is unnecessary once the deterministic edits run in the order D12 fixes: link
removal keeps a link's label and drops its brackets along with the URL, so `[doc 1 overview](url)`
reaches the citation parser as `doc 1 overview` and matches nothing.

**The parser is not the word-count regex.** `report_length.py` already carries `_CITATION_RE`, which
matches `[doc …]` and `[dataset …]` loosely — case-insensitively, with any text inside the brackets —
because its job is to keep citation text out of the word count, where matching too much is harmless.
Conversion needs the opposite bias: it acts only on the defined form, so it requires an integer id
and, for a document, an integer page, and leaves everything else as text (the spec states the
grammar). The two patterns therefore stay separate, each erring the safe way for its own job. That
is a deliberate divergence rather than a missed reuse, and it is worth saying because the project's
single-source-of-truth rule would otherwise read as an instruction to share one pattern.

- *Convert a citation whose file is not a PDF* — rejected two ways. Sending the file's real content
  type gives a pill whose Preview silently does nothing, because the annotation preview path handles
  only PDFs; sending `application/pdf` regardless makes the viewer fail with "Failed to load
  document" and misstates the file. A readable text marker beats both. Since the contract returns
  only a URL, the test is that URL's path ending in `.pdf`, which errs toward keeping the marker.
- *A third condition, splitting "has a URL" from "the annotation model accepts that source"* —
  rejected: the model's single-attachment source shape is why a non-file citation has nothing to
  point at, which is a reason behind the URL condition, not a second test a citation could fail
  independently. Two conditions that never fail apart are one condition described twice.
- *Convert every document marker, including one whose document resolved no URL* — rejected: the
  client shows a tag no annotation claims as text, so such a marker would deliver visible markup
  where a readable citation could have stood.
- *Keep every marker and put a pill beside it* — rejected by the product decision in the proposal:
  the pill is meant to be the marker, and `[doc 442, page 3] 📄 file.pdf, page 3` says it twice.
- *Make eligibility configurable per reader* — rejected: both intended readers are the same renderer
  (the overlay embeds the chat application), so a second rule could only ever disagree with reality.

The cost is a report that can mix pills with text markers. That is the honest rendering of what the
client can show, and an unconverted citation degrades to today's behavior rather than to something
broken.

### D3. The anchor is a tag the step writes into the text, not a computed offset

Each converted position gets an opaque id; the citation's marker is replaced by
`<cit data-id="…"></cit>` and every annotation anchored there names that id in its selector.

- *The `text_character_range` selector the spike used* — rejected now that the tag form exists. It
  requires the anchor to be a character offset into the **whole assistant message**, which drags in
  the length of any preparation text streamed earlier in the turn, an accessor the DIAL SDK does not
  offer (`Choice` exposes `append_content` but nothing that reads back what was appended), and a
  drift risk on every future change to what precedes the report. It also groups pills by attachment
  URL, which collapses every repeat citation of a document into one pill.
- *A tag id derived from the document and page* (`doc442-p3`) — rejected: two citations of the same
  page in different paragraphs would then share an id, and the client would draw the same pill twice
  while treating both positions as one group — the collapse the tag form exists to avoid.
- *Emitting the opening tag alone* — rejected in favour of the pair `<cit data-id="…"></cit>` the DIAL
  Chat team's integration instruction asks for. The matcher consumes only the opening tag either
  way, and the leftover closing tag is stripped by the renderer's sanitize pass, so the two render
  identically and following their instruction costs nothing.
- *The `id` attribute, which the branch as read is the only one that matches* — rejected on the DIAL
  Chat team's answer: `data-id` is the intended attribute and their implementation of it is being
  pushed. Targeting the confirmed contract rather than the code as read means this app does not have
  to change again a week later; the cost is that validation needs a build carrying their fix.

### D3a. A run of adjacent citations folds into one tag with several annotations

A statement supported by several sources is written as consecutive markers — the report prompt's own
example is `[doc 150, page 1] [doc 150, page 3] [doc 283, page 1]`. Those become **one** tag, with
one annotation per source, all naming that tag's id. The client groups annotations by tag id, so the
reader gets one pill whose popup steps through the sources instead of three pills in a row. Within a
run, two markers naming the same document and page collapse into one annotation, and each annotation
still carries its own `index` — two same-id annotations without one are merged by the client into a
single entry.

- *One tag per citation* — rejected: three tags side by side draw three pills for one statement,
  which is noise, and the reader has to click each to learn what it is.
- *One tag per citation, all sharing an id* — rejected and worth naming, because it looks like the
  economical version of the same thing: the client substitutes **every** tag carrying a matched id,
  so N tags with one id draw the same pill N times.
- *A run keeps its marker text when any of its citations fails a condition* — rejected as
  all-or-nothing: one unresolved document would cost the pill of every source beside it. The run
  converts what it can and leaves each failing citation's marker where it stands.
- *Treat "separated by a full stop" as adjacency too* — rejected: a citation after a sentence
  boundary supports a different statement, and folding the two would attach a source to a claim it
  was not offered for.

### D4. A tag is placed wherever the citation stands, and no Markdown block is classified

The step reads the draft as a string and replaces every convertible marker, wherever it sits. It
holds no model of Markdown blocks: the client's `cit` component override is keyed by tag name, so
the pill is drawn in a table cell, a heading, a blockquote or an emphasis span as readily as in a
paragraph.

The one place a tag does not become a pill is code — a fenced block, an indented block, or an inline
code span — because Markdown parses no raw HTML there and the reader sees the tag as written. That
is accepted rather than detected: a report cites its sources in prose, lists and tables, and paying
for a line scan of every draft to protect a case that does not arise buys nothing.

- *Keep the line-based classifier that skipped tables, headings, blockquotes and code* — rejected
  once the client shipped native `cit` rendering: the classifier's whole purpose was to avoid
  placeholder text where the client could not substitute a sentinel, and the client now substitutes
  everywhere its parser reaches. Keeping it would suppress pills a report's tables and headings can
  carry.
- *A real Markdown parser* — rejected: a new dependency to answer a question the step no longer
  asks.

### D5. The tool is named per MCP server in configuration, and at most one server may name it

One optional string field on `MCPClientSettings`, `file_sharing_tool`, both opts the server in and
says which tool to call. Flat rather than nested, because the DIAL application-type schema generator
inlines a root property's model and raises on a model nested below that (`_inline_root_refs`), and
`mcp_servers` is already such a root property.

- *A fixed tool name discovered by convention* — rejected: the feature would switch itself on and
  off with a remote server's tool list, an operator would have no switch, and a same-named tool with
  a different shape would fail at report-delivery time.
- *A boolean flag plus a hardcoded name* — rejected: it writes one server's chosen tool name into
  the contract, which is what R8 of the design write-up exists to avoid.
- *A nested `citations: {...}` object, for the metadata contracts to join later* — rejected: the
  schema generator cannot render it. Later contracts become sibling string fields.
- *A single top-level property naming server and tool* — rejected: it duplicates an association the
  server entry already expresses, and two properties could then disagree.

The at-most-one rule is not a simplification but a correctness requirement: a `[doc 442, page 3]`
marker names no server, so two servers issuing integer ids would make 442 ambiguous, and the report
writer has no way to qualify it. A configuration that wants two document servers needs the marker
format to carry a source first — a change to the **research-execution** citation requirement.

### D6. The tool is invoked as a LangChain tool, and only its structured result is read

`load_mcp_tools` already builds a LangChain tool per MCP tool, and `langchain-mcp-adapters` builds
them with `response_format="content_and_artifact"`, which is LangChain's two-slot tool result:
`content` is what a model would be shown, and `artifact` is a structured value it would not. An MCP
reply has two slots of the same kind, and the adapter routes one into each. Measured in the
installed `langchain_mcp_adapters/tools.py` 0.3.0: `_convert_call_tool_result` sets
`artifact` to `MCPToolArtifact(structured_content=result.structuredContent)` when the server sent
that field and leaves it `None` when it did not, while `content` becomes the converted content
blocks — a list of dicts rather than a plain string.

**The call is made with a tool-call-shaped input**, `{"name": <tool name>, "args": {"document_ids":
[...]}, "id": <a generated id>, "type": "tool_call"}`, and the step reads
`artifact["structured_content"]` off the `ToolMessage` that comes back. The shape is load-bearing,
not a style choice: `langchain_core.tools.base._format_output` returns the bare content and builds
no `ToolMessage` at all when `tool_call_id is None`, and the id is non-`None` only for a tool-call
input. A plain-argument invocation therefore throws the artifact away, the structured result becomes
unreachable, and the step would take its no-structured-result failure path on every turn — warning
once and converting nothing, which is a silent feature-off rather than a visible error. The ids go
out as integers, the type the measured tool's input schema requires (`document_ids`, an array of
integers with `minimum: 1`, and no other property accepted).

The result is validated into a typed model keyed by integer
document id (accepting the string keys JSON forces). It reads the content blocks not at all, even
though the measured server carries the same mapping there as JSON text. That second copy is not the
server's choice: FastMCP builds the text block by serializing the structured value, and
`ToolResult.to_mcp_result` has no path that returns the structured value without it (read in the
installed FastMCP 3.4.2). Since the duplication cannot be turned off at the source and both copies
are the same object, reading one is the whole of what reading two would give.

A missing artifact is therefore a failed call, and it lands in the delivery-failure path the
**report-citations** capability prescribes: one warning naming the failure kind, and the report
delivered with its markers as text. That is the outcome for a tool that declares no output schema,
since MCP sends no structured result for such a tool — which is why the contract requires the tool
to declare one rather than leaving the app to guess where the mapping went.

- *A second MCP client calling the session directly* — rejected: it duplicates the connection,
  header and bearer wiring that `build_mcp_client` already owns, for no gain.
- *Read the text block too, as a fallback* — rejected: it is a second read path for a case no server
  we can point at produces, and a path no test exercises against a real server is worse than a loud,
  specified failure, because it decides silently which copy the mapping came from. If a text-only
  server ever appears, the warning names it and the fallback becomes a small addition with a real
  server to test against.
- *Read the text block instead* — rejected: it re-parses what the server already structured, and the
  text block is the copy MCP keeps for older clients.

`handle_tool_error` is deliberately set to **`False`** on this tool, which takes an explicit
assignment rather than leaving it alone. The adapter installs an error handler by default:
`MultiServerMCPClient` defaults `handle_tool_errors=True` and forwards it into every `get_tools`
call, and `convert_mcp_tool_to_langchain_tool` passes `_handle_mcp_tool_error` into the
`StructuredTool` it builds (read in the installed `langchain-mcp-adapters`), while
`langchain_core`'s base tool re-raises a `ToolException` only when that attribute is falsy. A tool
the app merely refrains from touching therefore still turns an MCP error into ordinary content with
`status="error"` — for an app-called tool, a failure wearing the shape of an answer. Clearing the
attribute (or building this one tool from a client constructed with `handle_tool_errors=False`) is
what makes the failure reach the step. `enable_tool_error_handling` still applies to the agent's
tools, where turning an error into text the model can retry on is the point.

### D7. Both labels read `doc <id>, page <ix>`, the same text the marker carried

`body.source.attachment.title` is the group label and therefore the pill's own text;
`body.title` labels this citation's entry inside the pill's popup. Both carry `doc <id>, page <ix>`,
so a pill reads as the marker it replaced and a reader can tie it to the report's references section
now that the inline marker is gone. In a run's popup those labels are what tells the sources apart,
and the pill takes the label of the run's first citation while the client marks how many further
sources sit behind it.

The app has no document title to put there. The only human-readable text it holds is the file name
inside the shared URL, and that is a storage path segment rather than the document's title. So no
label is derived from the URL, and nothing in the payload decodes any part of it — `attachment.url`
carries the tool's URL verbatim, since a URL the app rewrote is a URL that may no longer name the
file.

- *The file name from the URL, with the cited page* — the previous choice, dropped: the pill would
  read a storage path segment, which is the document's file name only by the retrieval server's
  convention and is not the title a reader expects, and the app would have to percent-decode it to
  avoid showing `%20` where the file name has a space. Naming the id and page is honest about what
  the app actually knows, and it stays correct whatever the server names its files.
- *Real document titles from a metadata route* — deferred, and the intended replacement. It needs a
  route from a document id to that document's metadata, which the measured server does not have
  today: its document-listing tool filters by publication metadata rather than by id, and the server
  exposes no MCP resources at all. So this is a new tool or a new resource on the retrieval server,
  not a rearrangement of what is already there, and it is the change that would make these labels
  read as document titles.
- *A page-free label* — rejected: naming the page is possible now that grouping is ours rather than
  the client's, it is exact for the common case of a lone citation, and it saves the reader a click.
- *No titles at all* — rejected: the pill would fall back to the client's own label, derived from
  the URL's last path segment, and the popup entry would carry nothing at all.

### D8. The page travels only in the `pdf_bbox` selector

No `#page=N` fragment is appended to the URL. The spike's F2a measured that the annotation preview
path passes `source.url` unstripped into the download-URL resolver, so a fragment percent-encodes
into the query and the canvas fails with "Failed to load document", while the download action
strips it. A fragment would also be the only way to split one document's citations into separate
pills, which makes it tempting — and it trades the pill's primary action for that.

### D9. Annotations are emitted as one raw chunk after the content

`aidial-sdk` has no annotations API, so the array goes out through
`choice.send_chunk(ArbitraryChunk({...}))`, the same mechanism the SDK's own state and attachment
chunks use, while the choice is open.

- *`choice.add_attachment`* — rejected: it assigns attachment indices from its own counter, which
  would renumber annotation indices; and annotations embed their source file directly, so they never
  need to reference the attachments array.
- *Wait for an SDK annotations API* — rejected as a blocker, worth an upstream ask. `ArbitraryChunk`
  and `BaseChunk` are outside the package's `__all__`, so this import path is unexported and could
  change without deprecation; that is the risk of moving now.

### D10. The delivered text is what gets persisted

The report `AIMessage` added to the persisted slice carries the post-processed text, so the
conversation state matches what the reader saw. The annotations themselves are not persisted into
the app's own state: the client keeps them on the message, and no later turn of this app reads them.

- *Persist the draft with its original markers* — rejected: a later turn would show citations the
  user never saw, and the persisted answer would differ from the delivered one. The cost of the
  choice is that the persisted text carries the marker tags, which anything reading that state back
  — history, an export, a copy — sees as markup.

### D11. The citation step is announced as an activity stage

The runner keeps exactly one activity stage open while the graph runs and closes it before
delivering the report. The citation step happens after that close and can take a moment — a first
citation of many documents is several server-side copies — so the step opens one activity stage of
its own, and closes it before the content is appended.

The stage is opened only once the step has work — a file-sharing call to make, or edits to apply.
A draft that cites nothing and carries no link leaves the step with nothing to do, and a stage there
would open and close in the same instant, which the activity-stage requirement forbids because the
chat renders it as a completed step. That requirement is extended by this change rather than worked
around: its window now runs to the report's delivery, and the citation step is one of its
replacement triggers (see **dial-agent-with-mcp**).

- *Emit nothing* — rejected: the turn would look finished while it is still working.
- *Reuse the graph's activity stage* — rejected: it is closed with the graph's outcome, and a stage
  name can only be appended to.
- *Open the stage unconditionally* — rejected: on a turn with no citations and no links it would be
  an instantaneous open-and-close, the one stage pattern the requirement rules out.

### D12. The no-hyperlink rule is an app-checked report rule, and a removal at delivery

Two mechanisms with **different jobs**, which is what makes the pair work. The rule lives as a new
`ReportRule` in `report_rules.py`, whose abstraction already keeps a rule's writer instruction and
its check over a finished draft in one place; its violations join the review model's list exactly as
the structure and length rules' do. The review loop is where a link is properly fixed, because the
repair that reads well is a **rewrite of the sentence**, and only the report writer can produce one —
so the violation asks for a rewrite, not for a deletion. The delivery step then hard-removes whatever
survived, with no ambition to read well: by then the draft has already had its revision chance, and a
sentence ending mid-thought is a better outcome than a report that points its reader elsewhere.

Detection stays in Python even though the fix is the model's. The two are separable: a regex cannot
be talked out of seeing a link, and the report writer is the one that rewrites it. Note that
"detected by the report review" and "checked in Python" are not in tension here — the app's
violations are folded into the review step's list, so the review step is what reports them either
way.

- *Ask the review model to judge it* — rejected: a link is decidable by a regex, and the
  **report-composition** capability already reserves model judgement for what needs a reader, with a
  model verdict unable to pass an app-checked rule. The review prompt therefore stops asking about
  links and is told the app checks them, matching how headings and length are already handled.
- *Only check it, and let a violation force a revision* — rejected: the review may never run (a
  version budget of one) or may run out of versions, and a report that ships with a clickable
  external link has cited something the research never retrieved. The review is the layer that
  produces a *good* result; it cannot be the layer that produces a *guaranteed* one.
- *Only remove it at delivery, with no violation* — rejected: the writer would keep producing links
  with nothing pushing back, and the reader would silently lose the label's link with no revision
  attempted. Removal is the safety net, not the mechanism.
- *Leave an autolink or a bare URL in place, as an earlier cut of this decision did* — rejected: the
  rule is that the report points its reader at the retrieved sources and nowhere else, and a URL
  left as text still points outward — and a Markdown renderer auto-links it, so it is clickable
  again.
- *Repair a bare URL so the sentence still reads well* — rejected as impossible at this layer, and
  unnecessary. Inline code and a placeholder such as "(link removed)" both keep naming the
  destination, and no mechanical rule can reword the sentence around a deletion. That readability
  concern is real, and it belongs one layer up: the review loop demands a rewrite while a version is
  still available. Deletion at delivery is therefore accepted with its cost, because it only ever
  applies to a draft whose review already failed to remove the URL.

Link removal runs **before** citation detection, and citation detection then treats whatever text it
receives uniformly. Ordering it the other way would need the citation parser to carry a rule about
brackets followed by `(` — an earlier cut of this design did exactly that — which is code written for
a malformed case nobody has seen. Neither pass tries to repair the other's input: the repair stops at
removing the link, and the boundary of what is deliberately not attempted is in the spec.

**The two halves ship together, and only the citation half has a switch.** Link removal and the new
report rule apply to every deployment as soon as this change lands. No configuration turns them off:
an instance that names no file-sharing tool still gets the writer instruction, the review violation
and the removal at delivery. That is deliberate, not an oversight. The removal needs a deterministic
pass over the settled draft between the loop and the choice, which is what this change introduces —
`ResearchRunner._deliver_report` appends the draft verbatim today — and the rule is what makes "the
inline citation forms are the only way the report references a source" true, which is the premise
the citation parser rests on. Splitting the rule into a change of its own was raised in review and
rejected on that ground: it would introduce the same seam one change earlier, for one `ReportRule`
and one string pass.

**That pass is where later deterministic edits go.** It runs on every delivered report, including a
draft no review ever judged — `max_report_versions` of 1 makes no review call at all — so it is the
one point where the app can guarantee something about the text the reader gets. The known next
tenant is a references section built by code rather than written by the model, which the proposal
defers until a document-metadata contract exists; it belongs in this pass, beside link removal and
citation conversion, rather than in a second delivery-time mechanism of its own.

### D13. The demo is a separate completion over shared code, with its own fixtures

The mechanism needs somewhere it can be seen working before it can affect a real report, and the
DIAL Chat team needs something they can run against their own build. That is a second chat
completion, registered only under its own environment flag, answering with a fixed report — and
calling the same citation code a research turn calls.

- *Verify through the research completion itself* — rejected as the primary route: reaching the
  citation step means a full research turn against a live retrieval server, minutes per attempt, with
  the report's wording — and therefore which cases appear at all — decided by a model. A rendering
  question needs a fixed input.
- *Extend the playground completion* — rejected: it exists to exercise MCP tools through an agent,
  and folding an unrelated fixed-reply mode into it would make both harder to reason about.
- *Have the demo call the configured file-sharing tool like the research turn does* — rejected: it
  would tie the demo to a live retrieval server and to that server's document ids, so the reply would
  differ per environment and could not be run by anyone outside this project. The demo ships PDF
  fixtures and performs the caller-bucket copy itself instead, which is the one place it deliberately
  differs from production.
- *Copy the mechanism into the demo* — rejected outright, and the reason the shared module exists:
  a demo that reimplements what it demonstrates can pass while the product is broken. Everything
  decidable from strings — parsing, run folding, link removal, tag replacement, payload building —
  lives in one module both callers reach, and the emission helper is shared too.
- *Keep the throwaway spike as it is* — rejected: it was built to answer questions, its report is
  prose about unrelated papers, and it hand-builds its payload. What replaces it is specified,
  exercises every behaviour on purpose, and shares the product's code.

The fixtures are PDFs kept out of git, as the spike's were, so the repository carries no binary
sample documents.

### D14. The overlay adds a second chat on host port 4207

The spike's overlay swaps the base `chat` and `themes` services for next-generation images under the
same service names, so only one generation runs at a time
(`docker-compose.spike.yml`: `image: epam/ai-dial-chat:1.0.0-rc.6`, `ports: "3000:5000"`). This
change turns it into an overlay that **adds** a second pair, because the point is to compare what
each generation does with one reply, and a swap cannot show that without a restart.

Adding means the new chat needs a host port of its own, and the choice is constrained rather than
free. Its login goes through the shared Keycloak client, which accepts a redirect URI only on the
ports registered for it: the overlay records those as localhost 3000, 4207 and 5000, with 3010 and
3020 explicitly not registered. Port 3000 stays with the base chat, and 5000 is the app's own
default host port (**local-stack**: "app at 5000 on the host"). That leaves **4207**, and it is not
a preference — an unregistered port fails the login with "Invalid parameter: redirect_uri" before
any of this can be looked at.

- *Ask for another port to be registered on the client* — rejected as a dependency on someone
  else's configuration for something 4207 already satisfies.
- *Keep swapping and restart to compare* — rejected: the comparison is the requirement, and a
  restart between two renderings of one reply makes it a memory test.

One constraint of the swap-style overlay does not obviously carry over and SHALL be re-checked when
this is written: the current file states that the app must not run on host port 5000 under it,
because the chat image is one container whose backend-for-frontend listens there. With the
next-generation chat on 4207 and the base chat still on 3000, that reason may no longer apply. It is
recorded here rather than dropped silently, and it is a five-minute check against a running stack
rather than an argument to settle on paper.

## Risks / Trade-offs

- **StatGPT drops the annotations today, and a converted citation keeps nothing readable without
  them** → `OpenAiToDialStreamer._process_custom_content` forwards only `state`, `attachments` and
  `stages`, so a relayed report loses `custom_content.annotations`, and with them the document, the
  page and the label of every converted citation — the delivered text holds only an empty marker tag
  at that spot. Mitigation: citation conversion is inert unless an instance names a file-sharing
  tool, so that switch is per instance, and this change deliberately does not attempt that chain —
  the relay stays deferred work. Link removal has no such switch (see D12), but it leaves nothing
  for a relay to drop: the delivered text is plain prose either way. The fix on that side is small (one branch, plus a passthrough method on its choice
  protocol), and until it lands the feature serves readers who reach Deep Research directly.
- **Preview lands on the wrong page for every repeat citation of one document** → Read from
  `feat/cit-html-tag-annotations`, not observed: `annotationToPdfCanvasContent` resolves the clicked
  annotation's group with `groups.find((g) => g.sourceUrl === source.url)`, which is ambiguous now
  that groups are keyed by tag id, so after a document's first citation the viewer gets another
  citation's highlights and a `selectedHighlightId` that matches none of them. A research report
  cites the same document repeatedly, so this affects most pills. Mitigation: none on our side — it
  is one line in their code and is raised with them. Worth confirming in the browser during
  validation, since it is a code reading rather than an observation.
- **The delivered text carries markup only this renderer understands** → DIAL Chat and the overlay
  strip a tag no annotation claims, so prose stays clean there; another renderer may show the raw
  tag, and our persisted state, history and any copy or export carry it regardless. Mitigation: the
  tag is small, empty, and placed where a citation marker already stood, so the worst case is a
  visible `<cit data-id="…">` rather than damaged prose. This is the price of anchoring by tag instead of
  by offset, taken deliberately for one pill per occurrence.
- **A citation written inside code delivers a visible tag** → Markdown parses no raw HTML in a
  fenced block, an indented block or a code span, so a tag placed there is shown as written (D4).
  Mitigation: none by design — a report cites in prose, lists and tables. One local end-to-end run
  of a real report, inspected in the chat, is what would surface it if a report ever cites inside
  code.
- **A hallucinated page number opens the wrong page** → The page comes from the model copying a
  retrieval marker, and nothing validates it against the document's page count. Mitigation: none in
  this change; the document metadata contract would make a bound available later.
- **A Markdown link whose label starts with `doc` could be mistaken for a citation** → e.g.
  `[doc 1 overview](url)`. Mitigation: the fixed order of the deterministic edits (D12). Link
  removal runs first and keeps the label alone, so the parser reads `doc 1 overview` with no
  brackets and matches nothing. The word-count regex in `report_length.py` does match that label,
  which is harmless there because it only excludes citation text from the count. The mirror case —
  a link whose label is itself a citation marker, `[doc 1, page 2](url)` — loses its brackets the
  same way and so loses its pill; the writer is instructed never to produce a link at all.
- **Latency and cost of the copies** → One tool call per turn, carrying only the cited ids; the
  copies are server-side, and an already-current copy is skipped after an etag comparison. The step
  adds one round trip plus the server's copies to a turn that already took minutes.
- **An unexported SDK import path** (`ArbitraryChunk`) → Pinned dependency, one call site, covered by
  a test; an upstream ask for a supported API is the durable fix.
- **A non-streaming caller receives the annotations with their indices stripped** → Read in the
  installed `aidial-sdk`: a request with `stream: false` is served by `to_block_response`
  (`aidial_sdk/application.py`), which merges the chunks and then runs `cleanup_indices`
  (`aidial_sdk/utils/streaming.py`, `aidial_sdk/utils/merge_chunks.py`) over the assembled message.
  That helper deletes the `index` key from every dict element of every list it walks, annotations
  included. A run's several sources rely on distinct indices to stay distinct behind one tag, so for
  such a caller they can collapse into one popup entry. Mitigation: none, and none needed for the
  intended readers — DIAL Chat and the overlay both stream, and the spike confirmed the streaming
  path keeps the field. The limitation is stated in the **report-citations** payload requirement so
  the index rule is not read as holding for every caller.
- **The tag rendering is on DIAL Chat's development branch but in no release** → it merged there on
  2026-09-08 and 2026-09-09, after the newest release was built. Mitigation: the overlay runs the
  `development` image tag, and confirming which chat version a reader gets stays a precondition for
  enabling the feature for them.

## Migration Plan

No data migration and no schema migration. The order is deliberate: the demo comes before the
product wiring, because it is what makes the mechanism verifiable at all.

1. **Ship the shared citation code and the demo completion**, with the demo's flag off by default.
   Nothing about a research turn changes yet.
2. **Verify the mechanism through the demo**, against a chat build carrying the marker-tag
   rendering. That is the `development` image tag, which the overlay runs: the rendering is on DIAL
   Chat's development branch and in no release yet. What to look for: a pill at every
   convertible citation and none where a citation was left as text, a run rendering one pill with
   several sources, one document cited in several places rendering separate pills, each pill opening
   its own page, no raw marker tag or placeholder anywhere, and the fixtures opening for a user other
   than whoever added them.
3. **Wire the research turn**: the file-sharing tool call, the per-server configuration field, the
   hyperlink rule in the report rules, and the delivery step. From this step on, every deployment
   gets the hyperlink rule — the writer instruction, the review violation and the removal at
   delivery — whether or not it names a file-sharing tool, because that rule has no configuration
   switch (see D12). What an instance that names no tool does not get is citation conversion: its
   reports carry every citation marker exactly as the writer wrote it.
4. **Name the tool in one instance's `mcp_servers` entry** and check a real report — whose prose
   carries tables, bullets and emphasis, unlike any fixture — for the same things, plus whether
   annotations survive a reload and a re-share.
5. **Later, and out of this change**: the relay through StatGPT, which drops `annotations` today.

Rolling back the citation half is a configuration edit at each stage: unset the demo's flag, or clear
the file-sharing tool name on the instance, and no report gets a marker tag or an annotation, with no
code change or redeploy. The hyperlink rule has no such switch — rolling it back means reverting
code, which is the trade-off D12 states and accepts.

## Open Questions

- Whether inline annotations survive a conversation reload and a re-share. The spike confirmed the
  older reference-attachment convention survives a share, and annotations ride on the same message
  snapshot, but this was never exercised. It changes nothing in this design; it changes what we
  promise a client.
- Whether DIAL Chat will offer a page-only selector, which would retire the zero-size `pdf_bbox`
  workaround. Cosmetic here — the payload keeps working either way.
