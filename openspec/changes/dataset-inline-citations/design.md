## Context

See `proposal.md` — Why. What follows is only the state the approach has to fit into.

The citation step already has the shape this change extends. `ResearchRunner._run_citation_step`
removes hyperlinks, collects the cited document ids, calls one contracted tool for their URLs, reads
one contracted resource for their titles, and hands all of it to `convert_citations`, which is pure
and takes mappings rather than doing I/O. Every one of those resolutions fails into an empty mapping
rather than an exception, and an unresolved citation keeps its marker text. A dataset resolution
drops into that frame without changing it.

Three facts about the surrounding systems were read rather than assumed, and the approach rests on
them:

- **The StatGPT MCP's available-datasets tool answers with a structured result.**
  `statgpt/app/mcp/tools/datasets_meta.py` builds an `AvailableDatasetsStructuredContent` and returns
  it through a fastmcp `ToolResult`. Its `DatasetRecord` carries `id`, `name`, `description`,
  `provider`, `lastUpdated`, `url` and `numberOfIndicators`, serialized by alias, with `url` and
  `lastUpdated` both `str | None` and omitted when unknown. Its answer carries one record per dataset the channel exposes, each
  `id` a URN of the form `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)`.
- **That identifier is the one the report writer already carries into a marker.** The data-query
  tool reports the same string as `urn` in its structured result, and `app/research/prompts.py`
  already instructs the writer to cite "the dataset's `ID` as the tool reports it". The existing
  `_DATASET_MARKER` pattern accepts any character but brackets and newlines, so the colon and the
  parenthesised version survive parsing unchanged.
- **DIAL Chat opens an external citation URL without any change on its side.**
  `openAnnotationAttachment` sends any attachment URL not beginning `files/` to
  `window.open(url, '_blank', 'noopener,noreferrer')`; the citation card labels that button "Open in
  browser" exactly when the source type is `text/html` or `application/xhtml+xml`, and "Download"
  otherwise; the pill's own text comes from `attachment.title`; and `useAnnotations` re-derives a
  stored MIME type only from a *recognized URL extension*, so an extensionless portal URL keeps the
  type this app sends.

One existing code detail shapes a decision below: `find_citation_markers` matches the dataset form
but discards its id. `CitationMarker` documents this — "A dataset marker carries neither: its id is
not read" — because nothing needed it. It does now.

## Goals / Non-Goals

**Goals:**

- Resolve a cited dataset's name and page address through a contract the app states, so any dataset
  server that satisfies it works without a code change, exactly as the file-sharing contract does
  for documents.
- Keep dataset resolution inside the existing failure frame: no citation failure costs the report,
  and an unresolved dataset citation keeps its marker text.
- Leave the research agent's tool surface as capable as it is today.

**Non-Goals:**

- Any second read of the catalogue. The dataset call happens once per turn or not at all.
- Caching the catalogue between turns, and caching it across the agent's own use of the same tool.
  See decision 1.
- Changing the report's citation **forms**. `[doc <id>, page <ix>]` and `[dataset <urn>]` are
  unchanged; what changes is the prompt text saying what fills them, which is a wording change
  inside an existing contract rather than a new format.
- Series-level targeting inside the dataset explorer, and the References tables. Both are separate
  roadmap steps, and the second still has an open question about what shape a References row reads
  its metadata in.

One constraint on that later References work is settled already and is recorded here so this change
does not quietly contradict it: **References must list every document and dataset the report cites,
whether or not its metadata resolved.** A source the report-writer chose to cite is a source the
reader is entitled to see listed; failing to resolve a title, a date or a URL degrades that row to
what is known about it — at worst the bare identifier — and never removes it. Resolution is a
best-effort enrichment of a row, not the row's entry condition. This is why the requirements above
constrain how an unresolved source's metadata may be *used* rather than instructing the app to
discard it.

## Decisions

### 1. The metadata comes from a no-argument catalogue tool, not an id-parameterized surface

The app calls the configured tool with no arguments, receives the channel's whole catalogue, and
selects the records whose `id` matches a cited marker.

*Alternative — an id-parameterized MCP resource, mirroring `documents://metadata/{document_ids}`.*
Rejected because it does not exist. It would have to be built in the StatGPT backend first, blocking
this change on another team's queue in order to buy a property — asking only about what is cited —
that the deployed alternative already delivers correctly, just less efficiently. The contract stated
in the spec is about the answer's shape rather than its parameterization, so replacing the tool with
a parameterized surface later is a change to one module and one config field.

*Alternative — read the portal URL out of the data-query tool's own output during research.* The
query tool already returns `metadata.datasetUrl` beside each query, so no delivery-time call would
be needed at all. Rejected on two counts. It would make the app parse the research agent's tool
messages to build citations, which is exactly the coupling the file-sharing contract was written to
avoid — the app would depend on one server's result shape rather than on a stated contract. And it
resolves only datasets the agent happened to query in this turn, while the delivered report may cite
a dataset from an earlier turn's findings.

*Alternative — cache the catalogue across turns.* Rejected for now. The answer is per-channel and
changes rarely, so a cache would work, but it would be the first cross-turn cache in this
application and would need an invalidation story and a per-identity scope (the tool is called with
the caller's own credentials). One call on the turns that cite a dataset is cheap enough that the
cache would be buying very little.

### 2. The annotation's attachment type is `text/html`

*Alternative — `application/pdf`, the value the field is defaulted to today.* Rejected because the
client branches on this exact string twice, and both branches would then be wrong: the card's second
button would read "Download" for a page that is not a file, and the "Preview" button would route the
portal URL into the PDF viewer instead of the generic path.

*Alternative — omit the type.* Rejected: the client's card treats a non-HTML type as a file and
labels the button "Download", so an absent type lands in the wrong branch as surely as a wrong one.

Note the one way `text/html` can still be overridden. `useAnnotations` re-derives the type from a
*recognized* URL extension, so a dataset whose page address happened to end in `.csv` or `.xlsx`
would be relabelled by the client and would offer a download. A portal page URL ending in a file
extension is unusual and no channel this was checked against produces one, so this is recorded as a known edge
rather than guarded against; guarding would mean refusing to cite such a dataset, which costs more
than it saves.

### 3. A label's shape does not reveal whether its lookup succeeded

Every citation label is a **leading part** naming the source plus a **fixed trailing part** saying
what kind of source it is, and the trailing part is appended after any shortening:

| Field | With metadata | Without |
|---|---|---|
| pill — document | `<title>` shortened, then `, page <ix>` | `doc <id>, page <ix>`, unshortened |
| card — document | `<title>, page <ix>` | `doc <id>, page <ix>` |
| pill — dataset | `<name>` shortened, then ` dataset` | `<urn>` shortened, then ` dataset` |
| card — dataset | `<name> dataset` | `<urn> dataset` |

A failed lookup changes only what fills the leading slot. It does not change the shape, drop the
trailing part, or add any visible mark — no "unknown", no "untitled", no bracket.

The reason is about the reader rather than about tidiness. Whether this application reached a
metadata surface is its own problem; a reader shown that distinction learns nothing they can act on,
while being invited to trust one citation less than another that is exactly as real — the
report-writer cited both, and both open the same source. The failure belongs in the step's log event,
which already counts it, and nowhere the reader looks.

Documents already worked this way; `report-citations` simply never said so, and an unstated invariant
is one a later change breaks without noticing. This change states it and adds a scenario per source
type pinning it.

**The trailing word earns its place on a dataset label.** A dataset's name is often a bare noun
phrase — `World Economic Outlook`, `Primary Commodity Prices` — that does not say what kind of thing it names,
and a URN says less still. A document's trailing part is its cited page, which was always there.

**No label carries the URL.** It lives in `body.source.attachment.url`, which is never rendered as
text. The reader reaches it through the card's open-in-browser action — clicking the pill opens the
card, not the page. That two-click path is the client's, not a choice available to this application:
no field of the annotation makes a pill's click follow its URL.

*Alternative — the name alone on the pill, with ` dataset` only on the card, which this design
carried in an earlier revision.* Rejected: it saves one word of pill width and costs the invariant,
because the fallback pill must keep the word to be intelligible at all, so a named and an unnamed
dataset would then read as different kinds of thing.

*Alternative — the URL in the card's heading or body.* Rejected: the heading's job is to name the
source rather than address it, and the body's items are facts about the dataset, while a URL is a
fact about where this application chose to send the reader.

*Alternative — shorten the unresolved document label too, for uniformity.* Rejected: `doc <id>,
page <ix>` is short by construction so shortening is a no-op in practice, but at the minimum
configurable budget of ten characters it could eat the id, and losing the id costs the reader the
only handle they have on that source.

### 4. The reserved quote slot carries the dataset's identity and currency

`body.quote` exists for a quoted passage, and document citations send none because the app does not
hold the source text. A dataset citation has no passage either, but it has two facts a reader needs
in order to judge it — which dataset this is, and how current it is — and no other field with room
for them. `AnnotationBody` therefore gains `quote: str | None`, absent on every document annotation
exactly as it is today.

The field is sent as a Markdown list, `* URN: <urn>` and `* Last update: <date>`, because the client
renders this one field through its Markdown renderer (`CitationCard.tsx` passes `body.quote` to
`MarkdownRenderer` with `ul`/`ol` class overrides, while `body.title` is interpolated as plain text).
Two facts therefore read as two items rather than as one run-on line.

**The last-update row is dropped from the list entirely when no date was reported**, rather than
rendered as "unknown" or left as an empty item. This is the one place a dataset card's content does
vary with what resolved, and it is not in tension with decision 3: that invariant governs the
**labels**, which is what a reader scanning a report sees, while the body is read only after they
have opened one card deliberately. A reader learns nothing from a line saying the application knows nothing, and
an absent date is ordinary: `lastUpdated` is `str | None` in the server's own schema.

**The date is displayed exactly as the server sent it.** The app does not reformat it, localise it,
or turn it into "3 months ago" — for the reason **source-attribution** gives about identifiers, that
the app is not the authority on what a server's value means. This is also why the contract asks for
ISO 8601 or nothing: the StatGPT tool's `_dataset_last_updated` already returns
`.date().isoformat()` or `None`, explicitly refusing to pass through free text it could not parse.

A side benefit rather than a motivation: a popup with a switcher reserves three line-heights for a
quote whether or not one exists, which is an outstanding ask to the DIAL Chat team on behalf of
document citations. Dataset citations now fill that space instead of wasting it.

*Alternative — put the id and date in `body.title` beside the name.* Rejected: it makes the heading a
paragraph, and the card already has a field whose job is the supporting detail.

*Alternative — send the two facts as plain text with newlines.* Rejected because the renderer would
collapse them into one line; the list markers are what survives the Markdown pass as structure.

### 5. `body.selector` is omitted for a dataset, and the payload is dumped with `exclude_none`

A dataset citation names no page, so the field carries nothing. `AnnotationBody.selector` becomes
`PdfPageSelector | None = None`, and `send_annotations` dumps with `model_dump(exclude_none=True)` so
the key is absent rather than explicitly `null`.

*Alternative — send `"selector": null`.* Rejected because the array travels as an `ArbitraryChunk`
through the DIAL SDK's chunk merge, and an explicit null is one more value that merge has to
round-trip correctly for no gain. Absent is the shape the client's own model describes.

*Alternative — send a `pdf_bbox` with `page: 1`.* Rejected as a lie: it names a page of a file that
does not exist, and the client's PDF-highlight mapper reads exactly these entries.

`exclude_none=True` is safe for the two optional fields this change introduces, and both want
exactly that behaviour: `selector` is absent on a dataset annotation, and `quote` is absent on a
document one. It is a whole-payload rule bought for those two, so it is worth stating rather than
assuming: **any future annotation field that is legitimately null on the wire must revisit this
dump**, because `exclude_none` would silently drop it.

### 6. The app reads the tool's answer without turning off its error handling

`share_documents` relies on `handle_tool_error = False`, set in `load_mcp_tools`, so an MCP error
reaches it as an exception rather than as ordinary result content. That trick cannot be copied here,
because the dataset-metadata tool stays in the agent's tool list and `enable_tool_error_handling`
sets `handle_tool_error = True` on every agent tool. The same object cannot hold both settings, and
whichever assignment runs last would silently win.

The app therefore reads the returned `ToolMessage`'s own `status` field: `status == "error"` is the
failed-call kind, and anything else falls through to the structured-result check. This needs no
special error-handling state at all.

*Alternative — hold a `model_copy()` of the tool with `handle_tool_error = False`, leaving the
agent's instance untouched.* Rejected as more machinery for the same outcome, and it would make the
app depend on which parts of a langchain-mcp-adapters tool a shallow copy shares.

*Alternative — remove the tool from the agent's list, as the file-sharing tool is removed, so the
existing trick applies.* Rejected on its cost to the research rather than on its mechanics: a
catalogue listing is how the agent discovers which datasets exist before querying one, and this is
the same tool. Taking it away would spend the research to buy the citation.

### 7. The configuration field is optional on a `statgpt` server

Recorded in full in the `application-config-schema` delta, including why it is asymmetric with the
required `file_sharing_tool`. The consequence for this design is that the absent-tool path is
routine rather than a fault, so it is DEBUG rather than a warning, and
`dial_conf/core/applications-template.json` is not touched.

*Alternative — required, mirroring `file_sharing_tool`.* Rejected because a validation failure fails
the turn, so requiring the field would take an existing StatGPT-backed deployment offline until its
configuration was edited, in exchange for a label. It would also refuse a channel that genuinely
advertises no catalogue tool.

### 8. Convertible citations become a discriminated pair rather than one widened model

`_ConvertibleCitation` holds `document_id`, `page` and `url` today. Rather than making the first two
optional and adding an optional `dataset_id` and `name` — a model where four of six fields are
`None` in every instance — the implementation should carry two models and a union, with
`_build_annotation` dispatching on which it has.

`CitationMarker` gains `dataset_id: str | None`, populated from the regex group that is already
captured and currently discarded.

`convert_citations` gains one parameter for datasets rather than two. Documents take `document_urls`
and `document_titles` separately because they come from two different calls that fail
independently; a dataset's name and URL arrive in one record from one call, so one
`Mapping[str, DatasetSource]` — where `DatasetSource` carries the URL, an optional name and an
optional last-update date — keeps them from disagreeing.

### 9. The prompt names what identifies a source, not only the bracket shape

How a report references a source is an internal contract with two halves that must agree: the
prompt the report writer follows, and the parser that reads the delivered text. Today the prompt
states the shapes — `[doc <id>, page <ix>]` and `[dataset <urn>]` — and leaves what fills them to be
inferred, saying only "the dataset's `ID` as the tool reports it". That is enough to produce a
plausible marker and not enough to produce a resolvable one.

The prompt therefore states both halves: a document is referenced by its **document id and the index
of the cited page**, a dataset by its **URN written whole**, punctuation and version intact, never
abbreviated and never percent-encoded.

Naming this in the prompt is cheaper than any code-side tolerance. The alternatives are all
after-the-fact repairs of a writer that was never told the rule: matching a dataset by display name,
decoding a percent-encoded marker, or guessing a version. Each is a second resolution path for a case
that should not arise, and each weakens the verbatim rule that keeps a pill pointing at the right
source.

*Alternative — leave the prompt and add tolerance in the parser.* Rejected: it makes the app
responsible for guessing what the writer meant, and every guess is a way to resolve a citation to
the wrong dataset silently.

### 10. All three resolutions are issued together

The step issues the file-sharing call, the document-metadata read and the dataset-metadata call in
one `asyncio.gather`, so the citation step costs one round trip rather than three.

Two of the three were already independent. The third, the title read, was not: it asked only about
the documents the file-sharing call had resolved, which made it wait on that answer. Decision-wise
that dependency was a choice rather than a necessity, and it is removed by **asking about every cited
document id and discarding the titles of documents that resolved no URL**. The cited ids are known
from the report text alone, so nothing has to be awaited to build the request.

Constraining **use** afterwards is what keeps the dependency's original benefit. The rule that
mattered was never "ask about fewer documents" but "never show a title for a citation that is not a
pill", and filtering at the point of use enforces that just as well as filtering the question did —
including the logging property that the resolved-titles count stays bounded by the resolved-documents
count, which would otherwise break the moment a document resolved a title but no URL.

The spec deliberately stops at use rather than requiring the app to throw the value away, because the
References section will want precisely those titles: a source the report cites belongs in References
whether or not its URL resolved. Writing "discard" here would put a rule in the way of the next
change for no benefit today.

Each helper already swallows its own exceptions and returns an empty mapping, so `gather` needs no
`return_exceptions` and each resolution keeps failing independently with its own warning kind.

*Alternative — gather only the two already-independent calls and leave the title read second.*
Rejected: it saves one of the two round trips for none of the cost, since the filter that makes full
parallelism safe is four lines.

*Alternative — leave all three sequential, one awaited after the other.* Rejected: the step runs
only once per turn, which is what made this look cheap, but it runs at the point where the report is
otherwise finished and the reader is waiting on nothing else.

**The surplus is real but small**: on a turn where the file-sharing call resolves everything, which
is the ordinary case, the metadata read asks about exactly the documents it would have asked about
before. Only a partial file-sharing answer makes the read carry ids whose titles are then thrown
away.

## No changes required

Files that look like they need touching and do not:

- **`src/dial_deep_research/app/annotations_demo/completion.py`** — the new dataset parameter of
  `convert_citations` defaults to empty, so the demo keeps calling the same function unchanged. The
  `report-citations` delta keeps the rule that the demo shows no dataset citation, and restates its
  reason.
- **`dial_conf/core/applications-template.json`** — the new field is optional, and the template sets
  exactly the required properties.
- **`README.md`** — no environment variable is added or removed.
- **`src/dial_deep_research/app/research/report_length.py`** — its own, looser `_CITATION_RE`
  already excludes dataset markers from the word count, and a marker that becomes a tag is excluded
  by the same rule the document tags are.

## Risks / Trade-offs

- **The citation card will show a "Preview" button that does nothing useful.** For inline `<cit>`
  citations the chat always supplies its `onPreview` callback, so the button is always drawn.
  Routing was read from the chat's canvas specification: HTML is matched by `html`/`htm` *file
  extension*, never by the `text/html` MIME type, so an extensionless portal URL falls to
  "Everything else" and opens the side canvas showing "Preview is not supported for this file".
  → **Mitigation**: nothing in the annotation payload can influence it, so this is an ask on the
  DIAL Chat team — for a web-link citation source, either hide Preview or point it at the URL. The
  card's other button is the working one and is correctly labelled, so the feature is usable while
  the ask is open. Record the ask in the cross-repository document that tracks this chain.

- **The cost of the catalogue read scales with the channel's catalogue, not with the report.** A
  channel with hundreds of datasets sends all of them to resolve one citation.
  → **Mitigation**: the call is made once per turn and only when the delivered report cites at least
  one dataset, so a report citing no dataset pays nothing. Decision 1 records the parameterized
  surface as the replacement if a channel ever makes this hurt.

- **The data-query tool shows the model the URN twice, and one of the two copies is
  percent-encoded.** Its structured result carries `urn: "IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)"`, but
  the text part of the same result opens with a resource header naming
  `statgpt://data_query/IMF%3ADIRECTION_OF_TRADE_STATISTICS%281.0.0%29/…csv`. A report writer that copies
  the second form into a marker produces `[dataset IMF%3ADIRECTION_OF_TRADE_STATISTICS%281.0.0%29]`, which
  matches no catalogue record, and the verbatim rule forbids decoding it to make it match. Observed
  in a real tool call, not inferred.
  → **Mitigation**: none in this change beyond the specified failure mode — the citation keeps its
  marker text. The writer's instruction already says to use the id "as the tool reports it" and the
  structured result reports it unencoded, so the plain form is the one it should reach for. If this
  turns out to happen in practice, the two candidate fixes are a prompt sentence naming the encoded
  form as the wrong one, or a second match attempt against the percent-decoded marker — the latter
  being a deliberate exception to the verbatim rule, which is why it is not taken pre-emptively. This
  is listed as an open question below.

- **A report writer that abbreviates an identifier loses that pill silently.** `IMF:WEO` will
  not match a catalogue record whose id is `IMF:WEO(2.0.1)`, and the verbatim rule forbids
  guessing across the difference.
  → **Mitigation**: the failure mode is the specified one — the marker keeps its text — so the
  reader loses a pill rather than a citation. Note that the report review's citation-format check
  validates the *form* of a marker and not its id against any catalogue, so this will not be caught
  before delivery. The counts on the step's own event are where it shows up.

- **`exclude_none=True` on the annotation dump is a whole-payload rule bought for one field.** A
  later field that is meaningfully null would vanish.
  → **Mitigation**: stated in decision 5 so the next person adding an optional annotation field
  meets it.

- **The card's body is Markdown, and an identifier is server-controlled text inside it.** A dataset
  id carrying a Markdown metacharacter would render as formatting rather than as itself. The ids in
  use are safe — `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` has underscores, and CommonMark does not open
  emphasis on an intraword `_` — but nothing in the contract forbids an id containing `*` or `[`.
  → **Mitigation**: none in this change, since the quote's exact text is specified. Wrapping the id
  in backticks would make it literal and is the obvious fix if a channel ever ships such an id; it is
  left as an open question below rather than done pre-emptively, because backticks change how every
  id reads for a case no server currently produces.

- **A long identifier on a pill that resolved no name loses most of itself.** With the default
  twenty-character budget, `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` shortens to roughly
  `IMF:DIRECTION_OF_TR… dataset`, which names the agency and little else.
  → **Mitigation**: this is the fallback path, reached only when the catalogue reports a dataset
  without a usable name, and the card beside it carries the whole identifier. A channel that hits it
  routinely should raise `max_pill_title_chars` or fix its catalogue, and the gap between the
  requested and resolved counts is not where this shows up — the step's event cannot distinguish it,
  which is the honest limitation.

- **Two dataset servers would now open the wrong page rather than merely read ambiguously.** The
  configuration rule that refuses them already exists and is unchanged; this change raises what it
  is protecting, which the `application-config-schema` delta records.

## Migration Plan

No migration. The change is additive and gated on configuration that does not exist yet: until a
deployment adds `dataset_metadata_tool` to its `statgpt` server entry, every dataset marker is
delivered exactly as it is today. Rolling back is removing that one field from the channel's
application properties, which needs no redeployment of the application.

The one ordering constraint is on the *reader* rather than on the deployment: a dataset pill needs
the same DIAL Chat generation the document pills already need, so no channel gains a dataset pill
that does not already show document pills.

## Open Questions

These can be answered after implementation without changing the specs, the approach, or the task
breakdown:

- Whether the DIAL Chat team will hide the Preview button for a web-link source or point it at the
  URL. Either answer improves the card and neither changes what this application sends.
- Whether a marker carrying a percent-encoded URN should get a second, decoded match attempt, or
  whether the report writer's prompt should instead name the encoded form as the wrong one. Both are
  answerable after watching real reports; neither changes the specs unless it happens.
- Whether the identifier in the card's body should be wrapped in backticks. It would make an id
  containing a Markdown metacharacter render literally, at the cost of rendering every id in code
  style. No channel currently ships such an id, so the question can wait for one that does.
- Whether the References "Datasets" row should reuse the same `DatasetSource` record this change
  introduces. It carries the name and the date that row needs, but the row's shape is the open
  question that roadmap step owns.
