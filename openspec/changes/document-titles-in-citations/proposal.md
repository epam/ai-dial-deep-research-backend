## Why

A citation pill in a delivered report reads `doc 207, page 12`. That is the marker's own text, and
it is what the app has: the only human-readable string it holds per cited document is the file name
inside the shared DIAL URL, which is a storage path segment rather than a title. A reader sees an
integer where the publication's name belongs, and two pills from different publications are told
apart only by numbers whose meaning lives in a server they cannot see.

The retrieval server has held the title all along. Generic RAG's channel metadata carries it —
`publication_title` in the channel this was built against, holding a publication's name and its
subtitle — and its administration route has always returned the whole
metadata dict. What was missing was an access path for a consumer: the MCP tool surface maps `title`
from `display_name`, a file path, and drops every non-filterable metadata key as an undeclared
pydantic extra. Generic RAG now serves a templated MCP resource, `documents://metadata/{document_ids}`,
which answers with each requested document's stored metadata. Reading
`documents://metadata/1,5,9` against a deployed Generic RAG channel returns a
JSON object keyed by document id whose values carry `publication_title` and `publication_date`, and
that read goes through DIAL Core, which settles the one thing the cross-repository feature notes had
recorded as never exercised.

Building against that resource forces a second question into the open, and it is the more important
of the two. Deep Research is not independent of the servers plugged into it. It assumes a document
is attributable to a `(document id, page index)` pair, that a dataset is attributable to an id, that
the page is an index into the PDF a citation opens, and that the id in a citation is the id the
server will accept back. Every one of those assumptions is load-bearing and none is written down. The
sharpest is in a prompt: `app/research/prompts.py` tells the report writer that the search tools
report citations "in the compact form `[(207, 1)]`, where the tuple is `(doc_id, page_ix)`". That
string is the tuple repr produced by one f-string in Generic RAG's `PlainAnswer.add_citation`. If
that f-string changes, no test fails, no validation fails and nothing logs a warning — the reports
simply start losing citations. This change writes the contract down before adding another consumer
of it.

## What Changes

- **The marker parser accepts the document keyword written out in full**, so `[document 12, page
  3]` converts exactly as `[doc 12, page 3]` does. This is tolerance rather than a second report
  format: a server's own attribution may read `[Document 12, Page 1]`, which is close enough to the
  report's form that a writer may copy it through, and rejecting the copy would cost that citation
  its pill silently.

- **A new `source-attribution` capability states the citation contract end to end**, from what a
  retrieval server must report about where a fact came from, through the report's fixed inline
  format, to resolving that identifier back against the server. The organizing rule it records is
  that the contract is **semantic where a model reads it and syntactic where code reads it**: the
  report writer translates the server's attribution, so pinning bytes there would over-constrain
  every server and be unenforceable anyway, while a parser and a resolver read exact strings and
  must be given exact strings. Four requirements the chain has always relied on become stated:
  attribution is **self-describing** (the identifier and the page labeled rather than positional, so
  a bare `[(207, 1)]` violates it); a document server attributes to a `(document id, page index)`
  pair and a dataset server to at least a dataset id; the page is a **1-based index into the physical
  pages of the PDF** the file-sharing tool returns for that same id, never the number printed on the
  page; and the identifier in a citation marker is the identifier the server's resolution surfaces
  accept **verbatim**, with no normalization on the app's side. Finer detail a server chooses to add,
  such as a quotation or a figure index, is **ignored** rather than refused.

- **The report writer's prompt stops naming one server's spelling as the form.** The paragraph that
  hardcodes `[(207, 1)]` is rewritten to describe the semantic contract and to offer several example
  forms, so the example still helps the model without making another repository's f-string
  load-bearing for this one.

- **A cited document's publication title becomes the pill's label and the popup entry's label.**
  After the file-sharing call returns, the app reads the configured document-metadata resource for
  the ids that resolved a URL, and both `body.source.attachment.title` and `body.title` read
  `<publication title>, page <ix>` instead of `doc <id>, page <ix>`. The page stays in both labels
  because Generic RAG attributes at page level: two pages of one publication are two sources, and
  they must read as two entries in a popup even when a run of adjacent citations folds them behind a
  single pill. A document whose title does not resolve keeps the label it has today, so the failure
  mode is a plainer pill and never a lost one.

- **Two optional configuration fields name the resource and the title key.** An MCP server entry may
  carry `document_metadata_resource`, the resource URI template with a `{document_ids}` placeholder,
  and `document_title_key`, the metadata key holding the human title in that channel's schema. Only
  a `generic_rag` server may set them and they are validated as both-or-neither, since a URI with no
  key names nothing to read and a key with no URI has nothing to read from. They are **optional**,
  unlike the required `file_sharing_tool`, because a channel's metadata schema may genuinely carry
  no title key, and a missing title costs a label rather than a link.

- **The pill's copy of the title is shortened; the card's is not.** DIAL Chat does not trim a
  label that overflows — measured in the browser against a real report, where the pills ran long —
  so the app shortens the one copy that has no room. The budget is the channel property
  `max_pill_title_chars`, defaulting to 20, because what fits on a pill depends on the client the
  channel's readers use. The cited page is appended after the shortening and is never lost to a
  long title.

- **The annotations demo is untouched.** `convert_citations` takes the titles as a parameter that
  defaults to empty, so the demo keeps calling the same code and keeps rendering the marker labels —
  which is the fallback case, a real behaviour of the mechanism rather than a divergence from it.

## Capabilities

### New Capabilities

- `source-attribution`: what a retrieval MCP server must report about the source of a fact, how the
  report writer turns that into the report's inline citation form, and how the resulting identifier
  resolves back against the server. Owns the semantic-versus-syntactic rule, the self-describing
  requirement, the page basis, the verbatim identifier, and what a violation costs.

### Modified Capabilities

- `report-citations`: a citation's two labels read the cited document's publication title with the
  page, falling back to the marker text when no title resolves; a new contract for the
  document-metadata resource the titles come from; the marker parser also recognizes the document
  keyword written out in full.
- `application-config-schema`: the two new optional fields on an MCP server entry, their
  generic-RAG-only restriction and their both-or-neither validation.
- `research-execution`: the report writer's citation instructions describe the attribution
  contract rather than one server's spelling.
- `logging-policy`: the citation-step INFO event carries one more count, the number of cited
  documents a title resolved for.

## Impact

- **Code**: a new `app/research/document_metadata.py` reading the resource and extracting titles;
  `app/research/citations.py` taking a title mapping and building both labels from it;
  `app/research/runner.py` calling the read between the file-sharing call and the conversion, with
  its own failure kinds; `app/mcp_tools.py` returning the per-request `MultiServerMCPClient` that is
  built and discarded today; `app_properties.py` gaining the two fields and their validator;
  `app/research/prompts.py` for the rewritten citation paragraph.
- **Configuration**: two optional properties on an MCP server entry. Because they are optional,
  `dial_conf/core/applications-template.json` is not touched — it sets exactly the required
  properties. `docs/generated-app-schema.json` is regenerated by `make format`. No environment
  variable is added, so the README table is unchanged.
- **Dependencies**: none added. The read uses `MultiServerMCPClient.get_resources`, already present
  in the installed `langchain-mcp-adapters`.
- **Servers**: Generic RAG satisfies the new contract on four of its five tools. `rag_search` does
  not, because `PlainAnswer.add_citation` renders a bare tuple; fixing that, and then simplifying
  this repository's prompt paragraph once it is fixed, is tracked as the next roadmap step rather
  than done here.
- **Out of scope, in the order the work is planned**: converting dataset citations into pills backed
  by a portal link, which the cross-repository feature document already specifies and which would
  change this capability's "dataset citations are never converted" rule; building the References
  section in code; and the Generic RAG `rag_search` fix above.
