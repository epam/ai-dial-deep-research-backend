## Context

See `proposal.md` for motivation. What shapes the approach is the state of the three things this
change plugs together.

**The citation step already has the shape this work slots into.** `ResearchRunner._run_citation_step`
runs two deterministic alterations over the settled draft, calls the file-sharing tool once between
them, and catches every failure so none can cost the turn. A title lookup is a third input to the
same step, not a fourth alteration of the text.

**The resource answers with the channel's raw metadata.** Generic RAG's merged handler returns
`document.metadata` unchanged, so a value arrives under the channel's own key — `publication_title`
in the channel this was built against — and there is no canonical `title`. An earlier design had
the server answer under a canonical `title`; the implementation went the other way, and this
design follows the implementation, because that is what a deployed server actually serves.

**The MCP client is built per turn and thrown away.** `load_mcp_tools` constructs a
`MultiServerMCPClient`, fetches tools from it, and returns only the tools. A resource read needs the
same client later in the same turn, with the same per-request credentials.

## Goals / Non-Goals

**Goals:**

- A cited document's publication title reaches both annotation labels, with the marker text as the
  fallback.
- The attribution assumptions the chain has always relied on become stated requirements, so the next
  server plugged in is measured against something.
- The prompt stops making one server's formatting load-bearing, without waiting for that server to
  change, and the parser stops punishing the one mistake that change makes likelier.

**Non-Goals:**

- Reading anything from the metadata other than the title. The publication date is in the same
  answer and the References section will want it; nothing here consumes it.
- Any change to how a run of citations folds, or to which citations convert. The marker parser is
  widened in one narrow way — the document keyword written out in full — and nothing else about what
  counts as a citation moves.
- Compliance work on the servers. Generic RAG's `rag_search` violates the self-describing
  requirement; that fix lives in its own repository.

## Decisions

### The channel's title key is named in Deep Research's configuration, not canonicalised by the server

The resource serves raw metadata, so somebody has to name the key. Two places could: the server
(a channel config field naming its title key, answered back under a canonical `title`), or the
consumer (a field on the MCP server entry).

**Chosen: the consumer.** It needs no second repository to move first, and it matches what the
deployed resource already serves. The cost is that a channel-specific key name appears in Deep
Research's configuration, which is the thing the server-side alternative would have avoided.

Rejected: **canonicalise in Generic RAG.** It is the tidier contract, but it needs a channel config
field there plus a release before anything here can use it, and it stops at the title — the
References section's other columns are open-ended, which is the same argument that tells against a
fully canonical shape.

### The two configuration fields are optional and validated as a pair

`file_sharing_tool` is required on a `generic_rag` server, and the obvious move is to make these
required too, for symmetry.

**Chosen: optional, both-or-neither.** The symmetry is false. A document server with no file-sharing
tool loses every pill, which is a server that does not work; a document server with no title key
produces the labels this app has produced all along. A channel whose metadata schema carries no title
genuinely exists, and requiring the fields would make it unconfigurable.

One consequence to keep: because they are optional, `dial_conf/core/applications-template.json` is
**not** touched. That file sets exactly the required properties, and `tests/test_app_properties.py`
enforces it.

### The read happens after the file-sharing call, for the ids that resolved a URL

The two calls are independent and could run concurrently with `asyncio.gather`.

**Chosen: sequential, narrowed to the resolved ids.** Only a document that resolved a URL becomes a
pill, so a title for any other document would be fetched and never rendered. Sequencing also keeps
the two failure paths trivially independent: the share step already swallows its own failures and
returns a possibly-empty mapping, and the title step reads that mapping's keys. The cost is one round
trip of added latency on a step that already makes a slower one — the file copy — before it.

### `convert_citations` takes a title mapping, the way it takes the URL mapping

`citations.py` is pure functions over strings with no I/O, which is what lets every conversion rule
be tested without a server. A title is another per-document input, so it arrives the same way:
`document_titles: Mapping[int, str]`, absent id meaning no title.

Defaulting the parameter to empty is what keeps the annotations demo out of this change: it goes on
calling the same function, passing no titles, and goes on rendering the marker labels — which is the
fallback case rather than a divergence from the mechanism.

### `load_mcp_tools` returns the client it already builds

The alternative is building a second `MultiServerMCPClient` at delivery time from the properties and
the bearer token. That means threading the bearer token into the delivery step and holding two
clients per turn for no gain.

`MultiServerMCPClient` holds only the connection map; `get_tools` and `get_resources` each open their
own session, so reusing the instance later in the turn opens a fresh session with the same
credentials. Returning it from `LoadedMcpTools` is the smallest change.

### The URI is built by substituting the placeholder, not by `str.format`

`str.format` would choke on any other brace in a URI template and would silently accept a template
with extra placeholders. The app replaces the literal `{document_ids}` and nothing else, and
validation at configuration time rejects a template that does not carry exactly one.

### A metadata failure is graded one step below a file-sharing failure

The existing rule warns on every file-sharing failure except an absent tool, because each costs a
pill. A title failure costs a label. So: the read raising or answering unreadably is a WARNING (a
misconfiguration or a server in breach); an instance naming no resource is DEBUG (optional
configuration, would otherwise warn on every report); and a document that simply carries no title
warns not at all — that is data variance, and the gap between the resolved and titled counts on the
step's INFO event is the whole record of it.

### The prompt lists several attribution spellings rather than dropping the example

The rewritten paragraph could name no concrete form at all. That would satisfy the new requirement
and lose the concrete anchor a model benefits from.

**Chosen: several examples, framed as examples.** It satisfies the requirement — no sentence claims
the tools use one particular form — while keeping a concrete anchor, and it needs no coordination
with the Generic RAG fix that is in flight: a report writer that meets either the old tuple or the
new labelled form has seen something like both.

## Risks / Trade-offs

- **Generic RAG's `rag_search` output changes under us while this lands** (its PR makes the citation
  self-describing) → The rewritten prompt names both the tuple and the labelled form as examples, so
  the writer handles either. Nothing in this change's code path reads `rag_search` output.
- **The spec states a requirement the deployed server does not yet meet.** `rag_search` violates the
  self-describing requirement until its fix ships → The requirement is on servers and its violation
  costs citations rather than turns, which the capability states explicitly. The fix is open as a
  pull request rather than pending.
- **The resource answers with more than the title.** A document's metadata in that channel carries a
  `publication_short_summary` holding a paragraph of HTML, so a twenty-document read moves tens of
  kilobytes to extract twenty strings → Acceptable: the answer is read by code and never enters a
  model's context, and narrowing it would need a server-side field marker, which is the open question
  below.
- **A long title on a narrow pill may render badly** → Unmeasured by design. The app shortens
  nothing, and the longest publication title in that channel is 121 characters, so an ordinary
  report renders one. The reading is taken off the screen before any trimming is written.
- **A title is content and must never reach a log record** → Already forbidden by the content
  allowlist; this change restates it in `report-citations` and `logging-policy` because a new value
  now passes through the step that those records describe.

## Migration Plan

No data migration and no breaking change. The two properties are optional, so every existing channel
keeps validating and keeps delivering the labels it delivers today. Enabling titles for a channel is
adding two properties to its `applicationProperties` — no deploy, since DIAL Core serves application
properties — and the DIAL admin form picks them up from the regenerated schema.

Rolling back is removing the two properties from the channel: the labels return to the marker text
and nothing else changes.

## Open Questions

- **What shape the References section reads its metadata in.** One consumer-side configuration field
  per column does not scale past the title and the date. The alternatives are the server marking its
  reference fields — its metadata schema already carries `enable_filtering` and
  `enable_in_mcp_retrieve_chunks` markers, so a third is cheap — or the server serving a canonical
  row shape. Deferrable: it changes nothing about the title, which is one field either way.
- **Whether DIAL Chat's citation card previews a non-PDF external `http(s)` URL.** The annotation's
  attachment type is fixed to `application/pdf` and `report-citations` states the client opens only
  that type. This blocks dataset pills backed by a portal link, not anything here.
