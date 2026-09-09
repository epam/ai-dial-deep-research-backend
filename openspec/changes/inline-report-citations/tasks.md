Two phases, marked in every group heading below.

**Demo (groups 1 to 5)** is the deliverable of the first merge request: the shared citation code,
the demo completion and the local stack that shows it. It ships on its own — with the demo's flag
off the app behaves exactly as it does today — and it is what the DIAL Chat team can run against
their build. No task in it depends on a task from the second phase.

**Research turn (groups 6 and 7)** is the follow-up merge request, once DIAL Chat's marker-tag
rendering reaches their development branch. Until then every task in it stays unchecked, and the
change stays active rather than archived.

## 1. Demo — shared citation code

- [x] 1.1 Create `src/dial_deep_research/app/research/citations.py` with no DIAL and no LangChain
      imports, so every function below is testable over plain strings.
- [x] 1.2 Parse citation markers: `[doc <id>, page <ix>]` and `[dataset <id>]`, integer id and page,
      keyword matched case-insensitively. A page range, a non-numeric id, a page-less document
      citation and a nested bracket are not citations and keep their text. Do not reuse
      `report_length.py`'s `_CITATION_RE` — it errs the other way on purpose.
- [x] 1.3 Convert a marker wherever it stands, classifying no Markdown block: a table cell, a
      heading, a blockquote and an emphasis span each carry a pill, because the client's `cit`
      component override is keyed by tag name alone. A marker inside code delivers a tag the reader
      sees as text, and that is accepted rather than detected.
- [x] 1.4 Detect runs of adjacent markers (separated only by spaces, commas or semicolons) and fold
      each run into one tag: separators inside the run go with the markers they joined, surviving
      unconvertible markers follow the tag single-spaced in their original order, and two markers
      naming the same document and page collapse to one annotation.
- [x] 1.5 Detect and repair hyperlinks, one definition of "a hyperlink" that both the delivery pass
      and the report rule import: a Markdown link keeps its label, an image is dropped whole, an
      autolink or bare URL is deleted, a reference-style link keeps its label and loses both bracket
      pairs with its `[ref]: url` definition line deleted, a raw HTML anchor keeps its text and a
      raw HTML image tag is dropped. Nothing is interpreted, matched against the retrieved
      documents, or preserved anywhere.
- [x] 1.6 Replace each convertible marker (or run) with `<cit data-id="…"></cit>`, ids opaque and
      each appearing on exactly one tag in the message.
- [x] 1.7 Build the annotation payload: 0-based unique `index`, `target.selector` of type `html_tag`
      naming tag `cit` and the tag's `data-id` value in its `id` field, `body.title` reading
      `doc <id>, page <ix>`, `body.source.attachment` of `{type: "application/pdf", url, title}`
      with the URL carried verbatim and the title the same string as `body.title`, `body.selector` a
      `pdf_bbox` with the cited page and a zero-size box, and no `body.quote`.
- [x] 1.8 Order the two alterations: hyperlink repair first, then citation conversion over the text
      it produced, each failing independently of the other.
- [x] 1.9 Unit tests for 1.2 to 1.8, including the marker grammar's rejections, each Markdown block
      a citation can stand in, run folding with a mixed run, the repeated same-page pair, each
      hyperlink form, and the payload's field-by-field shape.

## 2. Demo — DIAL annotations emission

- [x] 2.1 Add an emission helper under `src/dial_deep_research/utils/` that sends the annotations
      array as one `ArbitraryChunk` through `choice.send_chunk` on the open choice, after the text
      has been appended. Note at the call site that the import path is unexported.
- [x] 2.2 Test the chunk's shape, and that the helper is the only place that builds it.

## 3. Demo — the flag-gated completion

- [x] 3.1 Add the settings flag (default `False`) and register the demo completion in
      `src/dial_deep_research/app/factory.py` only when it is set, on a deployment id of its own,
      as the playground channel is registered.
- [x] 3.2 Rewrite `src/dial_deep_research/app/annotations_spike/` into the demo package: it reads no
      application properties, runs no research, and calls no model.
- [x] 3.3 Take the cited documents from the caller's PDF attachments on the last message, in the
      order they arrive. Refuse an attachment that is not a PDF, carries no URL, or whose URL the
      shared PDF-URL rule rejects. Too few usable attachments fails the turn with a message saying
      what to attach, rather than answering with an incomplete demonstration.
- [x] 3.4 Check each attachment holds every page the report cites, reading the deepest cited page
      out of the report itself. A shallower attachment fails naming the file and its page count.
      Point each annotation at the attachment's own URL, which the caller can already open, so the
      demo copies nothing anywhere.
- [x] 3.5 Write the fixed report. Every case introduced by a sentence saying what it is and what
      should appear: a lone citation in a paragraph; a run folding into one pill; one document cited
      in several separate places; a citation in a list item; two pages of one document; a citation
      in a table cell and one in a heading, both rendering a pill there; a citation whose
      document has no URL; a Markdown link delivered as its label; a bare URL deleted. No dataset
      citation, no research prose, and no Markdown beyond what a case needs to exist.
- [x] 3.6 Build the reply through the group-1 and group-2 code — the same parsing, folding, link
      removal, tag replacement, payload building and emission — with nothing reimplemented locally.
- [x] 3.7 Emit the (8c) INFO event from the demo path: ids requested, resolved, annotations emitted,
      markers left as written, hyperlinks removed, duration. Counts only — no URL, file name,
      document title or id in any record.
- [x] 3.8 Tests: the flag off registers nothing; the fixed report's ten cases produce the tags and
      annotations the specs require; too few attachments and a shallow one each fail with their
      message.

## 4. Demo — local stack overlay

- [x] 4.1 Rewrite `docker-compose.spike.yml` as the annotations overlay: **add** a next-generation
      chat and a themes service of its own beside the base pair rather than replacing them, and
      rename the file accordingly. Pin the themes image to the `epam/ai-dial-chat-themes` tag
      that chat line expects, run the chat on the moving `epam/ai-dial-chat:development` tag, and
      record at that tag why this one service is not pinned to a version.
- [x] 4.2 Serve the next-generation chat on host port 4207, the one port the OIDC client accepts
      that the base chat and the app's default do not already hold, and note that constraint in the
      file.
- [x] 4.3 Take the OIDC credentials from `.env` only, with nothing inlined in the committed file.
- [x] 4.4 Rename `dial_conf/core/spike-applications.json` to the demo's core configuration file,
      rewrite its application entry, and append it to `aidial.config.files` from the overlay alone,
      never from the base stack.
- [x] 4.5 Turn the `spike-*` Makefile targets into the overlay's up, down and logs targets.
- [x] 4.6 Document in `.env.example` the identity-provider variables the next-generation chat needs
      and the demo's flag, and add the flag to the README's environment-variables table.
- [x] 4.7 Document the demo for the audience that will run it: how to enable it, which deployment id
      to call, what to attach and how deep it must be, and what to look for in the reply.
- [x] 4.8 Check the constraint D14 leaves open: whether the app must still be moved off host port
      5000 under this overlay now that the next-generation chat takes 4207. Record the answer where
      the constraint is stated, and drop the note if it no longer applies.
- [x] 4.9 Confirm `make infra-up` with no next-generation values in `.env` still starts the base
      stack alone and fails for nothing.

## 5. Demo — verify it, then ship it

- [ ] 5.1 Bring up the overlay against a chat build carrying the marker-tag rendering and the
      `data-id` attribute, log in as a real end user rather than with the development key, and call
      the demo deployment.
- [ ] 5.2 Check each case renders as its sentence says: a pill at every convertible citation, none
      where a citation was left as text, one pill for the run, separate pills for the repeated
      document, each opening its own page, and no raw tag or placeholder text anywhere.
- [ ] 5.3 Call the demo as a second user and confirm the pills open their files for that user too.
- [ ] 5.4 Open the same reply in the base chat and confirm what a client that does not understand
      the tags shows.

## 6. Research turn — wiring

- [ ] 6.1 Add the optional `file_sharing_tool` string field to `MCPClientSettings` with its
      description, and a validator rejecting more than one server that names one, its error naming
      the offending servers. Regenerate `docs/generated-app-schema.json` with `make format`.
- [ ] 6.2 Split `load_mcp_tools` so one `tools/list` fetch per server yields the agent's tools and
      the application-called tool separately, resolving the named tool from the server's full
      advertised list rather than through `tools_to_include`, and set `handle_tool_error` to `False`
      on it explicitly — the adapter installs a handler by default.
- [ ] 6.3 Follow that signature at its other callers: `app/playground/runner.py`, and
      `tests/test_mcp_client.py`, `tests/test_status_stages.py`, `tests/test_research_dispatch.py`.
- [ ] 6.4 Call the file-sharing tool once per turn with the distinct integer document ids of the
      citations that only need a URL, invoked tool-call-shaped so the `ToolMessage` carries its
      artifact, and validate `artifact["structured_content"]` into a typed id-to-URL model.
- [ ] 6.5 Add the no-hyperlink `ReportRule` to `report_rules.py`, importing the detection from
      `citations.py`, its writer instruction and its violation wording in the one class, its
      violations joining the review model's list.
- [ ] 6.6 Update the report-review prompt: its "Not your job" paragraph names the hyperlinks beside
      the headings and the length. Keep its citation-format check — the app now parses the markers
      that check enforces.
- [ ] 6.7 Run the citation step in `ResearchRunner` between the graph finishing and the report being
      appended: the post-processed text is what is appended and what is persisted, the annotations
      are emitted after it, and the step's activity stage opens only when it has work and closes
      before the content is appended.
- [ ] 6.8 Implement the failure paths: DEBUG when no server names a tool, one WARNING for each of
      the five real failure kinds, a failed link pass delivering the settled draft, a failed
      conversion delivering the link-free text, and a failed emission leaving its tags unclaimed.
      No citation failure fails the turn.
- [ ] 6.9 Tests: the at-most-one-server validator, the agent's tools excluding the file-sharing tool
      whatever `tools_to_include` says, the tool-call-shaped invocation, a partial response, an
      unreadable response, and each failure path's delivered text.
- [ ] 6.10 Update `docs/architecture.md`: the report-delivery step and what it emits, the
      app-checked-rules bullet (now three rules, and what report-review is told), and the list of
      what report-review is left to judge.

## 7. Research turn — enabling it for a reader

- [ ] 7.1 Name the file-sharing tool in one instance's `mcp_servers` entry and run a real research
      turn, whose prose carries tables, bullets and emphasis unlike the demo's report.
- [ ] 7.2 Check the same things as 5.2 on that report, plus whether the annotations survive a
      conversation reload and a re-share — the design's open question, which changes what we can
      promise a client.
