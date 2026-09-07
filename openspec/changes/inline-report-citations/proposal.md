## Why

The delivered report cites its sources as inline text: `[doc <id>, page <ix>]` for a document and
`[dataset <id>]` for a dataset. A reader who wants to check a figure has no way to open the cited
page — the marker names a document id, and the document itself is not reachable from the chat at
all (issue #65).

DIAL Chat has already shipped the rendering side. Its `libs/quotations` library reads
`custom_content.annotations` off a finished assistant message, renders an inline citation pill in
the message text, and opens the cited PDF in its side canvas. Nothing in this stack produces those
annotations, so none of it is reachable today.

Two things that used to block the producer side are now settled. A local spike on this
repository's `annotations-spike` branch (`src/dial_deep_research/app/annotations_spike/`, never
merged to `development`) drove the whole payload end to end, logged in as a real end user rather
than with a development key, and confirmed that the pills render, open the cited file, and scroll to
the cited page. Its most consequential finding was that a citation may only point at a file inside
the **caller's own** DIAL bucket, under `appdata/{deployment-id}` — the one folder an application may
write into someone else's bucket — because DIAL Core grants a normal user session access only to
resources in that user's own bucket. The document-retrieval MCP path returned no file reference at
all and copied nothing, which left nothing to cite. That path now exposes a tool that performs the
copy and returns the resulting URL, so the producer side can finally be built against it.

## What Changes

- **A citation step runs after the report loop settles and before the report reaches the user.**
  It finds the settled draft's `[doc <id>, page <ix>]` markers, calls the configured file-sharing
  tool once with every distinct cited document id, replaces each convertible marker with an empty
  citation marker tag (`<cit data-id="…"></cit>`), and emits one `custom_content.annotations` array
  carrying one annotation per tag. The report itself is written exactly as it is today: the prompts,
  the review loop and the word ceiling do not change, only the delivered text is post-processed.

- **Which citations are convertible is a stated rule, not a heuristic.** A citation becomes a pill
  only when two independent conditions hold. First, the cited document has a URL the reader can
  open, returned by the file-sharing tool, and that file is a PDF — ours, and the reason a dataset
  never qualifies, since a dataset is not a file. PDF-only because the client opens a citation for
  exactly that content type and the cited page is a PDF page; anything else keeps its text marker
  rather than getting a pill that opens nothing. Second, the marker stands where the client draws a pill: inside a paragraph
  or a list item, in ordinary text rather than in a table cell, a heading of either Markdown form, a
  blockquote, a fenced or indented code block, or inside emphasis or a code span — the client's
  renderer, which no prompt or setting can talk out of it. A citation failing either one keeps its marker text, so the failure mode is a missing pill
  and never a lost citation. Both intended readers — DIAL Chat and the DIAL overlay, which embeds
  the chat application in an iframe rather than reimplementing it — run the same renderer, so the
  second condition is one rule rather than one per reader.

- **The report may cite nothing but the retrieved sources, so it carries no hyperlinks.** A
  Markdown link is a citation of something the research never retrieved, and today nothing stops the
  writer from producing one. The rule is enforced at three points: the report writer's instructions
  say only the inline citation forms may reference a source; the app checks every reviewed draft for
  links, images, autolinks and bare URLs and reports each as a violation, which joins the review
  model's list so a revision is written and the finding shows in the review's stage; and the
  delivery step leaves nothing pointing outward, even in a draft the version budget left unrevised —
  a link keeps its label and loses its URL, an image is dropped whole, an autolink or bare URL,
  which has no label to keep, is deleted, and a reference-style link or a raw HTML anchor is treated
  like its Markdown counterpart. The two layers owe different things, which is the point:
  the review loop is where a link is properly fixed, so its violation asks for the **sentence to be
  rewritten** rather than for the URL to be deleted, because only the report writer can produce a
  sentence that reads well without it; the delivery step owes only the guarantee, and accepts that a
  hard removal can leave a sentence ending mid-thought, since by then the draft has already had its
  revision chance. The repair also stops at removal: the app does not interpret a link, does not
  match its target against the retrieved documents, does not keep the URL anywhere, and does not
  rewrite the prose around it — the spec states that boundary explicitly.

  **This rule has no configuration switch.** Unlike the citation conversion below, it applies to
  every deployment as soon as the research turn is wired: an instance that names no file-sharing
  tool still gets the writer instruction, the review violation and the removal at delivery. That is
  deliberate — the removal needs the deterministic pass over the settled draft that this change
  introduces, and the rule is what makes the inline forms the only way a report references a source,
  which is the premise the citation parser rests on. The same pass is where later deterministic
  edits of the delivered report belong, starting with the code-built references section this change
  defers.

- **Several sources behind one statement render as one pill.** Markers standing next to each other,
  separated only by spaces, commas or semicolons, are converted as a run: one marker tag for the
  whole run, one annotation per source naming that tag, and the client draws a single pill whose
  popup steps through them. `[doc 1, page 2], [doc 2, page 2], [doc 1, page 2]` therefore becomes one
  pill carrying two sources, the repeated pair counted once, rather than three pills in a row.

- **The annotation payload is the tag form DIAL Chat added on `feat/cit-html-tag-annotations`.**
  Each annotation carries a sequential `index` from 0; a `target.selector` of type `html_tag`
  naming the tag (`cit`) and the id of that citation's tag in the text; `body.title` reading
  `doc <id>, page <ix>`, which keeps the References section's `id` column connected to something the
  reader can still see; a nested `body.source.attachment` of `{type, url, title}` whose `type` is
  stated explicitly as `application/pdf` and whose `title` labels the pill with the same
  `doc <id>, page <ix>` text, since the app has no document title to show and will not read one out
  of a storage path; and a `body.selector` that is a zero-size `pdf_bbox`
  (`x1=y1=x2=y2=0`) carrying the cited page, which the spike confirmed scrolls the viewer to that
  page and draws nothing. No `body.quote` is sent. The array is emitted in a single `ArbitraryChunk`
  through `choice.send_chunk` after the report content is appended, because `aidial-sdk` has no
  annotations API and that is the same mechanism the SDK's own state and attachment chunks use.

- **Grouping becomes ours rather than the client's.** DIAL Chat groups tag-anchored annotations by
  tag id, so what shares a pill is exactly what we decide shares a tag: a document cited in six
  paragraphs renders six pills, each opening its own page, while several sources behind one statement
  render as one. Anchoring by tag also removes the alternative's whole apparatus — no character
  offsets, and nothing needs to know how much text the preparation agent streamed into the message
  earlier in the turn.

- **Nothing about citations can fail the turn.** A server with no configured citation tool, a tool
  error, an unparseable response, or an id the server did not resolve leaves the affected markers
  as plain text and delivers the report unannotated, with one warning logged. One INFO record
  reports what the step did in counts; per the content allowlist, the returned URLs are a tool
  response body and are never logged.

- **A flag-gated demo completion, built first.** A second chat completion, registered only when its
  environment flag is set, answers with a fixed report that exercises every behaviour of the
  mechanism: a lone citation, a run that folds into one pill, one document cited in several places,
  a citation in a list item, two pages of one document, citations in a table cell and a heading that
  keep their text, a citation whose document has no URL, a Markdown link delivered as its label, and
  a bare URL deleted. It builds its annotations with **the same code** a research turn uses, so a
  behaviour shown there holds in a real report; the only difference is that it ships PDF fixtures and
  copies them into the caller's `appdata` folder itself, since a demo must be self-contained and
  identical on every environment. Its text says what each part demonstrates, because its audience is
  someone verifying how a reply renders — including the DIAL Chat team.

- **Build order.** The shared citation code and the demo completion come first, and are shareable on
  their own. Wiring the research turn — the MCP tool call, the configuration field, the delivery
  step — follows. The demo is how the mechanism gets verified before any of it can affect a real
  report: until the research turn is wired, and with the demo's flag off, the app behaves exactly as
  it does today. Once it is wired, the hyperlink rule applies everywhere and only the citation
  conversion stays configuration-gated.

- **Not in this change.** Dataset citations: a dataset is not a file, so there is nothing to copy
  into the reader's bucket and nothing for the document viewer to open, which is the first condition
  failing rather than a limit of the annotation model. What a dataset pill should link to, and where
  such a link should open, is undecided, so `[dataset <id>]` markers keep their plain text as
  specified behavior rather than as an omission. Also deferred: a References section built by code
  and document metadata read from the MCP server, both of which need a metadata contract that does
  not exist yet.

## Capabilities

### New Capabilities

- `report-citations`: how the delivered report's document citations become DIAL inline citation
  annotations — the citation step's position in the turn, the two conditions that decide which
  citations it converts, how adjacent citations fold into one pill, why dataset citations are not
  converted, the contract the file-sharing tool must satisfy, the annotation payload and how it is
  emitted, and what happens when any of it fails.

### Modified Capabilities

- `research-execution`: the report node's requirement that the settled draft is the only assistant
  content now has to say that the delivered text is the settled draft with each converted citation's
  marker replaced by a marker tag, and that `custom_content.annotations` is emitted alongside it.
  The requirement that fixes every research LLM call's inputs changes too, as it obliges: the report
  writer's system prompt gains the rule that a source is referenced only by an inline citation form,
  and the report-review message now says the app checks the hyperlinks as well as the headings and
  the length.
- `report-composition`: the inline citation format is already specified as a machine-readable
  interface rather than a style choice; it is now literally parsed by application code, and the
  reviewed draft and the delivered text are no longer byte-identical. It also gains the rule that a
  report cites only the retrieved sources and carries no hyperlinks, and the no-hyperlink check joins
  the rules the app checks in Python rather than asking the review model to judge.
- `dial-agent-with-mcp`: MCP tool loading gains a tool the application calls and the agent must
  never see, loaded outside the `tools_to_include` filter and without the agent's
  `handle_tool_error` conversion; and citations require the server to be reached in deployment
  mode, because `appdata` resolves only for a per-request key.
- `application-config-schema`: `MCPClientSettings` gains the optional citation-tool field, with a
  validator allowing at most one server to set it.
- `logging-policy`: the INFO request skeleton gains one event for the citation step, and the
  warning cases above are named.
- `local-stack`: both chat generations become runnable side by side through an opt-in overlay that
  adds the next-generation chat and its own themes service rather than replacing the base ones, and
  the demo deployment gains its opt-in registration in DIAL core. This supersedes the throwaway
  `inline-annotations-spike` change, whose planning artifacts are removed with this one; its code
  stays as the starting point for the demo and the overlay.

## Impact

**New files**

- `src/dial_deep_research/app/research/citations.py` — detecting and repairing the hyperlinks a
  report may not carry, parsing the markers, classifying which Markdown block each one sits in,
  replacing the convertible ones with marker tags, and building the annotation payload. The
  hyperlink detection lives here rather than in `report_rules.py` so that one definition of "a
  hyperlink" backs both the review violation and the removal at delivery; the rule imports it. Pure
  functions over strings, with no DIAL objects, so all of it is unit testable.
- A DIAL annotations emission helper under `src/dial_deep_research/utils/` — the
  `ArbitraryChunk` shape and the one call that sends it.
- A demo chat completion under `src/dial_deep_research/app/`, its PDF fixtures kept out of git, and
  a settings flag gating its registration in `src/dial_deep_research/app/factory.py`. The existing
  `annotations_spike` package is what this rewrites: same place in the tree, respecified contents,
  and its hand-built payload replaced by calls into the shared citation module.
- The committed core configuration file holding the demo's application entry, appended to
  `aidial.config.files` only by the annotations overlay. The spike already ships one
  (`dial_conf/core/spike-applications.json`, already appended by the overlay alone), so this is a
  rename and a rewritten entry rather than a new file.
- Tests under `tests/` for the parser and the two eligibility conditions, the marker grammar
  (a page range, a non-numeric id and a page-less document citation are all left as text), the
  hyperlink rule, the tag-replacement and payload builders, the run folding, the
  at-most-one-server validator, and the failure paths — including that the file-sharing tool is
  invoked tool-call-shaped, since a plain-argument call silently loses the structured result and
  degrades into the specified failure path rather than raising.

**Modified files**

- `src/dial_deep_research/app/research/runner.py` — runs the citation step between the graph
  finishing and the report being appended, appends the post-processed text, and emits the
  annotations.
- `src/dial_deep_research/app/mcp_tools.py` — `load_mcp_tools` returns the agent's tools and the
  application-called citation tool separately, fetching each server's tool list once, and sets
  `handle_tool_error` to `False` on the citation tool so a failure is detectable rather than
  delivered as result text. Explicitly `False`, not merely left alone: the MCP adapter installs an
  error handler on every tool it builds.
- `src/dial_deep_research/app/playground/runner.py` — follows `load_mcp_tools`'s new return shape.
  The playground is not incidental breakage: the citation tool must reach no model's tool list, and
  the playground binds one.
- `tests/test_mcp_client.py`, `tests/test_status_stages.py` and `tests/test_research_dispatch.py` —
  they assert on `load_mcp_tools`'s return value or stub it, so the split reaches them.
- `src/dial_deep_research/app_properties.py` — the new `MCPClientSettings` field and the
  at-most-one-server validator.
- `src/dial_deep_research/app/research/report_rules.py` — a new `ReportRule` for the no-hyperlink
  rule, carrying both the writer's instruction and the check whose violations join the review's list.
- `src/dial_deep_research/app/research/prompts.py` — the report-review prompt's "Not your job"
  paragraph gains the hyperlinks beside the headings and the length, matching how those two are
  already handled. This is an addition, not a removal: the prompt asks nothing about links today,
  and its citation-format check (check 5) stays, since the app now parses the markers it enforces.
  The report writer's own instructions gain the no-hyperlink rule through `report_rules.py`.
- `docs/generated-app-schema.json` — regenerated from the model by `make format`.
- `docker-compose.spike.yml` — rewritten as the annotations overlay: it **adds** a next-generation
  chat and its own themes service instead of replacing the base pair, and appends the demo's core
  configuration file. Renamed accordingly.
- `Makefile` — the `spike-*` targets become the annotations overlay's up, down and logs targets.
- `.env.example` — documents the identity-provider variables the next-generation chat needs, and the
  demo's flag.
- `README.md` — the environment-variables table gains the demo's flag, which the repository's own
  rule requires whenever a variable is added. Its per-server `mcp_servers` prose is deliberately
  **not** extended for the new field: that paragraph already defers the authoritative property list
  to `docs/generated-app-schema.json`, which the model regenerates, and the at-most-one-server rule
  is a cross-server constraint that reads better in the validator's error than in prose.
- `openspec/changes/inline-annotations-spike/` — **removed.** Its `local-stack` delta is superseded
  by this change's, and archiving it would have written a deployment `development` never had into the
  main specs as current behaviour.
- `docs/architecture.md` — the report-delivery step and what it now emits, plus two passages this
  change makes wrong: the app-checked-rules bullet, which says there are two such rules and that
  report-review is told the app checks "both", and the list of what report-review is left to judge.

**Not affected**

- `dial_conf/core/applications-template.json` — the new property is optional, and the template
  carries exactly the required ones.
- `src/dial_deep_research/app/research/report_length.py` and the report review loop's control flow —
  the word ceiling, the version budget and the routing are untouched; the no-hyperlink rule joins the
  existing app-checked rules rather than changing how they are applied.
- `src/dial_deep_research/app/preparation/runner.py` and `app/completion.py` — anchoring by tag
  needs no character offsets, so nothing has to know how much text preceded the report.

**External dependencies, all outside this repository**

- **No DIAL Chat release carries the marker-tag rendering yet.** It exists on their branch, and they
  are pushing the `data-id` attribute change on top of it. So the mechanism can be built and shared
  now, but seeing it render needs a build from that team. This gates verification, not
  implementation.
- **Integration with StatGPT is deferred, not solved.** It relays a sub-deployment's
  `custom_content` but forwards only `state`, `attachments` and `stages`, so `annotations` are
  dropped — and because a converted citation keeps nothing readable in the text, such a report loses
  the citation rather than degrading to a visible marker. Testing that chain is explicitly out of
  this change; it is recorded as later work, and until it is done this feature is for readers who
  reach Deep Research directly.
- **Preview lands on the wrong page for a repeat citation of one document**, read from
  `feat/cit-html-tag-annotations` rather than observed: the canvas still resolves the clicked
  annotation's group by attachment URL, which is ambiguous now that groups are keyed by tag id, so
  for every citation of a document after its first the viewer is handed another citation's
  highlights and no scroll target. A research report cites the same document repeatedly, so this
  affects most pills until DIAL Chat fixes it. It is raised with them, along with the
  paragraph-and-list-item limitation. They have confirmed `data-id` as the marker tag's attribute
  and are pushing the change, so validation needs a build that carries it.
