# data-sources-discovery Specification

## Purpose

Builds the description of a channel's data sources from what its MCP servers report, so an admin
does not have to write and maintain by hand what changes with the servers' content. Once per turn,
with retries, the app fetches the list of datasets, their structures and the glossary from the
StatGPT server, and the number of documents and the publication dates they cover from the Generic
RAG server. It puts them, together with each server's static description, into the context of the
model calls that plan the research, run it and write the report.

## Requirements

### Requirement: The data sources are fetched once per turn, before preparation

When a channel configures a `statgpt` MCP server, or a `generic_rag` server that sets
`document_stats`, the app SHALL run one **data-sources fetch** per turn, before the preparation
agent's first model call, and SHALL use its result for every model call of the turn, research
included. The fetch has up to three parts, which SHALL run concurrently:

- **the datasets**: whenever the channel configures a `statgpt` server, because such a server
  always names its list-datasets tool (see **application-config-schema**), and, when the server
  also names a `dataset_structure_tool`, the structure of every listed dataset;
- **the glossary**: only when the `statgpt` server configures a `glossary`;
- **the documents**: only when the `generic_rag` server sets `document_stats`.

A turn of the playground deployment SHALL run the data-sources fetch once, before the playground
agent's first model call, under the same rules.

A channel that configures neither a `statgpt` server nor a `generic_rag` server with
`document_stats` SHALL make no data-sources call. A channel with no `statgpt` server SHALL carry
neither a datasets section nor a glossary in its prompts, and a channel whose `generic_rag` server
sets no `document_stats` SHALL carry no document statistics block.

The fetch SHALL call the tools the configuration names, by those names. It SHALL NOT fetch the
server's tool list to find the tools: the names come from the configuration, and a name the server
does not advertise surfaces as a failed call, which the retry rules below already handle. The MCP
client library may still request the tool list during a call, to validate the call's structured
result against the tool's output schema as the MCP specification recommends; that request is part
of the call, under its deadline and its retries. The server's
`tools_to_include` filter SHALL NOT affect the fetch, because the filter states which tools a model
is offered, and the fetch is made by the app.

The fetch SHALL use an MCP client constructed for the turn, with the same connection and
credentials as the turn's other MCP traffic to that server (see **dial-agent-with-mcp**), and each
tool call SHALL run in an MCP session of its own, so a failure that ends one session cannot fail
another call.

Every call SHALL be bounded by a fixed deadline. A call that has not returned by its deadline
SHALL count as a failed call. The bound is needed because the MCP transport's read timeout does not
end a call, and without it one call that never returns would hold the turn before preparation
starts.

The fetched data sources SHALL NOT be persisted to the turn state. They live for the turn only, and
the next turn fetches them again.

A turn that ends before preparation because its conversation already handed off to research SHALL
make no data-sources call: the fetch runs only on a turn that goes on to preparation.

#### Scenario: One fetch serves the whole turn

- **WHEN** a turn on a channel with a `statgpt` server runs preparation and then research
- **THEN** the list-datasets tool SHALL be called in one fetch before the preparation agent's first
  model call, and the research calls SHALL receive the datasets section that fetch produced, with
  no second fetch

#### Scenario: A channel with nothing to fetch makes no call

- **WHEN** a turn runs on a channel whose only MCP server is a `generic_rag` server that sets no
  `document_stats`
- **THEN** no data-sources call SHALL be made, and no prompt SHALL carry a datasets section, a
  glossary or a document statistics block

#### Scenario: A document-only channel fetches the documents

- **WHEN** a turn runs on a channel whose only MCP server is a `generic_rag` server that sets
  `document_stats`
- **THEN** the app SHALL list the documents before the preparation agent's first model call, and
  SHALL make no list-datasets call

#### Scenario: The documents are fetched alongside the datasets

- **WHEN** a turn runs on a channel with a `statgpt` server and a `generic_rag` server that sets
  `document_stats`
- **THEN** the first list-documents call and the list-datasets call SHALL both be sent before
  either of them returns

#### Scenario: A channel without a glossary makes no glossary call

- **WHEN** a turn runs on a channel whose `statgpt` server sets no `glossary`
- **THEN** no list-terms or term-definitions call SHALL be made, and no prompt SHALL carry a
  glossary

#### Scenario: The tool filter does not stop the fetch

- **WHEN** the dataset server's `tools_to_include` names neither the list-datasets tool nor the
  glossary tools, and the document server's `tools_to_include` does not name the list-documents
  tool
- **THEN** the app SHALL still fetch the datasets, the glossary and the documents, and none of
  those tools SHALL be offered to a model

#### Scenario: A call that never returns is cut off

- **WHEN** a term-definitions call receives no response
- **THEN** the call SHALL count as failed once its deadline passes, and its terms SHALL be
  re-requested in the next round

#### Scenario: A stalled list-datasets call is cut off and retried

- **WHEN** the first list-datasets attempt receives no response
- **THEN** that attempt SHALL count as failed once its deadline passes, and the app SHALL make the
  second attempt

#### Scenario: Tools are called by their configured names

- **WHEN** a data-sources fetch starts on a channel that names its list-datasets tool
- **THEN** the app SHALL call that tool by the configured name, without first listing the server's
  tools to find it

#### Scenario: A handed-off conversation makes no call

- **WHEN** a turn arrives on a conversation whose research already started on an earlier turn
- **THEN** the app SHALL make no data-sources call, and the turn SHALL fail as it does today

### Requirement: The list of datasets is requested with at most three attempts

The app SHALL call the list-datasets tool with no arguments, and SHALL make at most **three
attempts** in total. An attempt SHALL count as failed when the call raises, when the result is
marked as an MCP error, when it does not return by its deadline, or when its structured content
does not carry a `datasets` array, the shape the **report-citations** contract of the tool requires.
Any failed attempt SHALL be retried while attempts remain, whatever the kind of failure. The
attempts SHALL be separated by a growing delay with jitter, on the order of one second before the
second attempt and two seconds before the third.

When all three attempts fail, the datasets section SHALL carry the failure text described in **The
datasets section is rendered as one string**, no structure call SHALL be made, and the turn SHALL
continue.

A list with no datasets SHALL be a successful result, and no structure call SHALL be made.

The successful attempt's result SHALL also be read for the explorer links the list-datasets tool
MAY carry in its `_meta` (the **report-citations** contract of the tool states the payload and what
a missing or unreadable one costs), so the catalogue the turn's citations resolve against carries
them. Only the structured content decides whether an attempt failed: a missing or unreadable
payload SHALL NOT fail an attempt and SHALL NOT be retried. The payload SHALL NOT reach the
datasets section, so no model reads it.

A cancelled turn SHALL NOT be retried or converted into the failure text: cancellation SHALL
propagate.

#### Scenario: A transient failure is retried

- **WHEN** the first list-datasets attempt fails with HTTP 502 and the second succeeds
- **THEN** the app SHALL use the second attempt's answer, and SHALL make no third attempt

#### Scenario: Three failures give the failure text

- **WHEN** all three list-datasets attempts fail
- **THEN** the datasets section SHALL carry the failure text, no structure call SHALL be made, and
  the turn SHALL continue to the preparation agent

#### Scenario: The explorer links reach the catalogue and not the models

- **WHEN** the first list-datasets attempt succeeds and its result carries explorer links under the
  configured `_meta` key
- **THEN** the catalogue the turn's citations resolve against SHALL carry those links, the datasets
  section SHALL carry the structured result alone, and no second attempt SHALL be made

#### Scenario: A result without explorer links is not retried

- **WHEN** the first list-datasets attempt returns a structured result with a `datasets` array and
  no `_meta` payload
- **THEN** the app SHALL use that answer and SHALL make no second attempt

### Requirement: Dataset structures are requested concurrently, one call per dataset

When the server names a `dataset_structure_tool` and the list succeeded, the app SHALL request the
structure of every dataset the list reported.

**The structures add the larger share of the tokens.** A dataset's structure answer is on the
order of 450 tokens, and its record in the list answer on the order of 200. A channel that wants the list without the
structures leaves `dataset_structure_tool` unset: the models see the list alone, and the research
agent calls the structure tool itself when the server's `tools_to_include` filter offers it.

- **The contract.** A tool named as a dataset-structure tool SHALL take one argument,
  `{"dataset_id": <id>}`, where `<id>` is a record's `id` from the list-datasets answer, and SHALL
  return the structure of that one dataset as a JSON object in its MCP **structured result**. The
  app SHALL depend on nothing else about the object: it shows the object to the models as the
  server sent it.
- **Calls.** The app SHALL make one call per distinct string `id` in the list's `datasets` array,
  and SHALL send all of them concurrently. A record without a string `id` gets no call.
- **Attempts.** Each call SHALL have at most **three attempts**, separated by the same growing
  delay as the list attempts. An attempt SHALL count as failed when the call raises, when the
  result is marked as an MCP error, when it does not return by its deadline, or when it carries no
  structured result that is a JSON object.
- **After the last attempt**, a dataset whose structure was not obtained SHALL stay in the
  structures block as a failure entry.

#### Scenario: Every listed dataset gets one structure call

- **WHEN** the list reports 5 datasets and the server names a dataset-structure tool
- **THEN** the app SHALL send 5 concurrent structure calls, each with one dataset's `id` as
  `dataset_id`

#### Scenario: Only the failed call is repeated

- **WHEN** one of the 5 structure calls fails with HTTP 502 and the other 4 succeed
- **THEN** the app SHALL repeat only the failed call, at most twice more

#### Scenario: A structure answer that is not an object is a failed attempt

- **WHEN** a structure call returns structured content that is a JSON array rather than an object
- **THEN** that attempt SHALL count as failed and be retried while attempts remain

#### Scenario: No structure tool means no structure call

- **WHEN** the server names no `dataset_structure_tool`
- **THEN** the app SHALL make no structure call, and the datasets section SHALL carry no structures
  block

### Requirement: The datasets section is designed for a catalogue of about ten datasets

Showing the whole catalogue to every call that receives the data-sources string SHALL be understood
as designed for a channel whose catalogue holds on the order of **ten datasets**. Such a catalogue
costs on the order of 6,500 tokens with its structures, and every call carries all of it. The app SHALL NOT cap, page, filter or shorten the catalogue: a channel with a larger
catalogue is outside what this change designs for, and serving one is deferred.

#### Scenario: A channel of the intended size

- **WHEN** the list reports 5 datasets and the server names a dataset-structure tool
- **THEN** the datasets section SHALL carry the whole list and all 5 structures, with nothing left
  out

### Requirement: The datasets section is rendered as one string

The datasets section SHALL be one string. It SHALL start with the line `Datasets:`, a newline, and
the list-datasets tool's structured result serialized as one-line JSON, exactly as the server sent
it: every field, in the server's order.

When the server names a `dataset_structure_tool` and the list reported at least one dataset with a
string `id`, the section SHALL continue with a blank line, the line `Dataset structures:`, a
newline, and a one-line JSON array. The array SHALL carry one element per dataset the app requested
a structure for, in the order the list reported them:

- for a dataset whose structure was obtained, the structured result of its structure call, exactly
  as the server sent it;
- for a dataset whose structure was not obtained, the object
  `{"dataset_id": <id>, "error": "failed to obtain dataset structure"}`.

When the list-datasets tool failed three times, the section SHALL be the line `Datasets:`, a
newline, and the text `failed to obtain list of datasets`, with no structures block.

Characters outside ASCII SHALL be written as themselves rather than as `\u` escapes, because dataset
names and descriptions carry typographic quotes and dashes, and an escape costs tokens and reads
worse.

#### Scenario: A list with structures

- **WHEN** the list reports two datasets and both structure calls succeed
- **THEN** the section SHALL be `Datasets:`, a newline, the list's structured result as one-line
  JSON, a blank line, `Dataset structures:`, a newline, and a JSON array of the two structured
  results in the list's order

#### Scenario: A failed structure is marked in its place

- **WHEN** the list reports datasets `A` and `B` in that order, and only the structure of `A` is
  obtained
- **THEN** the array SHALL carry the structure of `A` first, and then
  `{"dataset_id": "B", "error": "failed to obtain dataset structure"}`

#### Scenario: A failed list gives the failure text

- **WHEN** all three list-datasets attempts fail
- **THEN** the section SHALL be `Datasets:` followed by a newline and
  `failed to obtain list of datasets`

### Requirement: The list of terms is requested with at most three attempts

The app SHALL call the list-terms tool with no arguments, and SHALL make at most **three
attempts** in total. An attempt SHALL count as failed when the call raises, when the result is
marked as an MCP error, when it does not return by its deadline, or when its structured content
does not carry a `terms` array of records with a `term` string. Any failed attempt SHALL be
retried while attempts remain, whatever the kind of failure. The attempts SHALL be separated by a
growing delay with jitter, on the order of one second before the second attempt and two seconds
before the third.

When all three attempts fail, the glossary result SHALL be the failure text described in **The
glossary is rendered as one string**, no term-definitions call SHALL be made, and the turn SHALL
continue.

A list with no terms SHALL be a successful result: no term-definitions call SHALL be made, and the
glossary SHALL render as an empty array.

A cancelled turn SHALL NOT be retried or converted into the failure text: cancellation SHALL
propagate.

#### Scenario: A transient failure is retried

- **WHEN** the first list-terms attempt fails with HTTP 502 and the second succeeds
- **THEN** the app SHALL use the second attempt's list, and SHALL make no third attempt

#### Scenario: Three failures give the failure text

- **WHEN** all three list-terms attempts fail
- **THEN** the glossary result SHALL be the failure text, no term-definitions call SHALL be made,
  and the turn SHALL continue to the preparation agent

### Requirement: Definitions are requested in concurrent batches, in at most three rounds

After the list succeeds, the app SHALL request the definition of every listed term through the
term-definitions tool, whose argument is `{"terms": [<term name>, ...]}`.

- **Batches.** A round SHALL split the terms it requests into batches of at most
  `max_terms_per_definitions_call` names, and SHALL send all of that round's batches concurrently.
  The app SHALL never send a batch larger than the limit, because the server rejects such a call
  whole and fetches nothing for it.
- **Rounds.** The app SHALL run at most **three rounds**. The first round requests every listed
  term. Each later round requests every term that did not resolve in the round before, split into
  new batches, and runs only when at least one such term exists. Later rounds SHALL be separated
  from the round before by a growing delay with jitter, on the order of one second before the
  second round and two seconds before the third.
- **What resolves a term.** A batch call counts as failed under the same conditions as a list-terms
  attempt, with `definitions` in place of `terms`. A term resolves when a successful call's
  `definitions` carries a record whose `term` equals the listed name after surrounding whitespace
  is trimmed from both and both are case-folded. A term does not resolve when its batch call failed,
  when the call reports it under `notFound`, or when the call's answer names it nowhere. A record
  that matches no term the batch requested SHALL be ignored.
- **After the last round**, a term that did not resolve SHALL stay in the glossary without a
  definition.

#### Scenario: A glossary larger than the limit is split into batches

- **WHEN** the list has 25 terms and the limit is 10
- **THEN** the first round SHALL send three concurrent calls, requesting 10, 10 and 5 terms

#### Scenario: Only the unresolved terms are re-requested

- **WHEN** in the first round one batch of 10 fails and the other batches resolve every term they
  requested
- **THEN** the second round SHALL request exactly those 10 terms, and a third round SHALL run only
  if some of them still do not resolve

#### Scenario: A term reported as not found is re-requested

- **WHEN** a successful batch call reports one requested term under `notFound`
- **THEN** that term SHALL be requested again in the next round, while rounds remain

#### Scenario: A term still unresolved after three rounds stays listed

- **WHEN** a term does not resolve in any of the three rounds
- **THEN** it SHALL appear in the glossary without a definition, and no fourth round SHALL run

### Requirement: The glossary is rendered as one string

The glossary result SHALL be one string: the line `Glossary terms:`, a newline, and a JSON array.
The array SHALL carry one object per listed term, in the order the list-terms tool returned them.
Each object SHALL start with an `index` field, an integer counting from 1 in that order, followed
by:

- for a resolved term, every field of its record in the term-definitions answer, in the order the
  answer gives them;
- for an unresolved term, every field of its record in the list-terms answer, with a `definition`
  field set to `null` directly after `term`.

Characters outside ASCII SHALL be written as themselves rather than as `\u` escapes, because
glossary terms carry typographic quotes and dashes, and an escape costs tokens and reads worse.

When the list-terms tool failed three times, the string SHALL be the line `Glossary terms:`, a
newline, and the text `failed to obtain list of terms`.

The rendered objects exist only inside this string, which is never persisted as a list, so the
`index` field cannot be re-slotted by the DIAL SDK's chunk merge.

#### Scenario: Resolved and unresolved terms side by side

- **WHEN** the list returns `Primary Commodity Prices` and `World Economic Outlook` in that order,
  and only the second resolves
- **THEN** the string SHALL be `Glossary terms:` followed by a newline and an array whose first
  object is `{"index": 1, "term": "Primary Commodity Prices", "definition": null}` and whose second
  object starts with `"index": 2` and carries the definition record's fields

#### Scenario: A failed list gives the failure text

- **WHEN** all three list-terms attempts fail
- **THEN** the string SHALL be `Glossary terms:` followed by a newline and
  `failed to obtain list of terms`

### Requirement: The documents are listed page by page, each page with at most three attempts

When the `generic_rag` server sets `document_stats`, the app SHALL list every document of the
collection through the configured list-documents tool.

- **The contract.** The tool SHALL take two integer arguments, `offset` and `limit`, and SHALL
  return in its MCP **structured result** an object with an integer `total_count`, the number of
  documents in the collection, and a `results` array with one object per returned document, whose
  top-level fields carry the document's metadata. This is the shape of the Generic RAG
  `list_documents` tool. The app SHALL send no other argument, so no metadata filter applies and
  the server's default order applies.
- **Pages.** The first call SHALL request `offset` 0 and `limit` equal to `page_size`. Its
  `results` are documents of the listing as well as the source of `total_count`, so the first
  page is never requested twice. While the documents received are fewer than that `total_count`,
  the app SHALL request the next page with `offset` equal to the number of documents received so
  far and the same `limit`. The pages after the first SHALL be requested one at a time, each after
  the one before it returned: when `page_size` covers the collection, one call lists everything,
  and splitting it into concurrent calls would gain nothing.
- **No consistency checks.** The app SHALL NOT check the pages for documents that appear twice or
  not at all. Ordering the collection stably across pages is the server's responsibility.
- **A page that adds nothing.** A successful page whose `results` array is empty while fewer
  documents than `total_count` were received SHALL end the listing as incomplete, because
  requesting the same offset again would repeat it without end.
- **Attempts.** Each page call SHALL have at most **three attempts**, separated by the same growing
  delay as the list-datasets attempts. An attempt SHALL count as failed when the call raises, when
  the result is marked as an MCP error, when it does not return by its deadline, or when its
  structured content is not an object with an integer `total_count` and a `results` array of
  objects.
- **After the last attempt**, a page that was not obtained SHALL end the listing as incomplete: no
  further page SHALL be requested.
- **Page cap.** One listing SHALL request at most `MAX_DOCUMENT_PAGES` pages, which is 10. When
  that many pages were received and the documents received are still fewer than `total_count`,
  the listing SHALL end as incomplete. Every page is one sequential call before preparation
  starts, so the cap bounds how long the listing delays the turn's first reply; with the default
  `page_size` of 1000 it covers ten thousand documents.

An incomplete listing SHALL render the document statistics block as its failure text: the line
`Document statistics:` and the line `failed to obtain list of documents`, with no figures. The
figures of a partial listing would understate the collection, and the models would read them as
complete. The failure text still tells the models that the channel serves documents, which is all
they learn about them when the server sets no `description`.

A cancelled turn SHALL NOT be retried or turned into an incomplete listing: cancellation SHALL
propagate.

#### Scenario: One page covers the collection

- **WHEN** the first call, with `offset` 0 and `limit` 1000, returns 40 results and a
  `total_count` of 40
- **THEN** the app SHALL make no second call, and the statistics SHALL count 40 documents

#### Scenario: A larger collection is listed page after page

- **WHEN** `page_size` is 100 and the first call reports a `total_count` of 250
- **THEN** the app SHALL make two more calls, with `offset` 100 and then `offset` 200, each with
  `limit` 100, the third sent only after the second returned

#### Scenario: A transient page failure is retried

- **WHEN** the second page's first attempt fails with HTTP 502 and its second attempt succeeds
- **THEN** the app SHALL use the second attempt's answer, continue with the next page, and render
  the document statistics block

#### Scenario: A page that fails three times gives the failure text

- **WHEN** all three attempts of the second page fail
- **THEN** the app SHALL request no further page, the document statistics block SHALL be its
  failure text, and the turn SHALL continue

#### Scenario: An empty page ends the listing

- **WHEN** the first page reports a `total_count` of 250 and returns 100 results, and the second
  page returns no results
- **THEN** the app SHALL request no further page and the document statistics block SHALL be its
  failure text

#### Scenario: A collection beyond the page cap

- **WHEN** `page_size` is 100 and the first call reports a `total_count` of 1500
- **THEN** the app SHALL make 10 calls, the last with `offset` 900, request no eleventh page, and
  the document statistics block SHALL be its failure text

#### Scenario: A collection the page cap covers

- **WHEN** `page_size` is 100 and the first call reports a `total_count` of 1000
- **THEN** the app SHALL make 10 calls and render the figures of 1000 documents

#### Scenario: An answer without a total count is a failed attempt

- **WHEN** a page call returns structured content with a `results` array and no `total_count`
- **THEN** that attempt SHALL count as failed and be retried while attempts remain

### Requirement: The document statistics are computed from each document's metadata

From a complete listing the app SHALL compute these figures, reading each document's metadata from
the fields of its object in `results`:

- **Count**: the number of documents the listing received.
- **Publication dates**: the earliest and the latest of the documents' valid dates. A document's
  date is the value under `document_date_key`. It is **valid** when it is a string that parses as
  an ISO 8601 calendar date, such as `2025-04-30`, or as an ISO 8601 date and time, such as
  `2025-04-30T09:00:00`, which contributes its calendar date. A value that is missing, `null`, not
  a string, or a string that does not parse SHALL be ignored for the dates. The document still
  counts.
- **Per type**, only when `document_type_key` is set: the documents grouped by the value under
  that key, and for each group the same count and dates. A group is formed by every string value,
  including an empty string and a string of only whitespace, and two values form the same group
  only when they are equal character for character: a type is not trimmed or case-folded. A
  document whose type is missing, `null` or not a string SHALL belong to no group, and still
  counts in the overall count.

A malformed value is ignored rather than treated as a failure because the metadata a document
carries is whatever was ingested with it, and one document with a malformed date says nothing about
the others.

#### Scenario: A malformed date is ignored

- **WHEN** a complete listing returns three documents whose dates are `2024-05-01`, `May 2024` and
  absent
- **THEN** the statistics SHALL count 3 documents, with the earliest and the latest date both
  `2024-05-01`

#### Scenario: A date and time contributes its date

- **WHEN** a document's date is `2025-04-30T09:00:00`
- **THEN** the date it contributes SHALL be `2025-04-30`

#### Scenario: A whitespace-only type is a group of its own

- **WHEN** `document_type_key` is set and the documents' types are `Annual report`, ` ` and
  `annual report`
- **THEN** the statistics SHALL carry three groups, `Annual report`, ` ` and `annual report`

#### Scenario: A document without a usable type counts only overall

- **WHEN** `document_type_key` is set and one of 10 documents has no type and another has the
  list `["Annual report"]` as its type
- **THEN** the overall count SHALL be 10, and those two documents SHALL belong to no group

### Requirement: The document statistics block is rendered as one string

The document statistics block SHALL be one string of lines. It SHALL start with the line
`Document statistics:` and continue with the overall line:

- `<count> documents, published from <earliest> to <latest>.` when at least one date is valid;
- `<count> documents, publication dates unknown.` when none is.

`<count>` SHALL be written as a plain integer, and the word SHALL be `document` when the count is 1.
A date SHALL be written as an ISO 8601 calendar date, `YYYY-MM-DD`.

When `document_type_key` is set and at least one group was formed, the block SHALL continue with
the line `By <document_type_key>:`, which names the metadata key the models can filter by, and one
line per group, ordered by the type value in code-point order:

- `- <type>: <count> documents, published from <earliest> to <latest>`, or
- `- <type>: <count> documents, publication dates unknown`,

where `<type>` is the type value written as a JSON string, so it stands in double quotes, an
all-whitespace type stays visible, and a double quote inside it is escaped. Characters outside
ASCII SHALL be written as themselves rather than as `\u` escapes, for the reason the datasets
section gives.

When `document_type_key` is not set, or no group was formed, the block SHALL carry no `By` line.

#### Scenario: A collection with types

- **WHEN** a complete listing returns 3 documents, two of type `Newsletter` dated `2024-01-10`
  and `2024-06-10`, and one of type `Annual report` with no date, and `document_type_key` is
  `publication_type`
- **THEN** the block SHALL be the lines `Document statistics:`,
  `3 documents, published from 2024-01-10 to 2024-06-10.`, `By publication_type:`,
  `- "Annual report": 1 document, publication dates unknown` and
  `- "Newsletter": 2 documents, published from 2024-01-10 to 2024-06-10`

#### Scenario: A collection without a type key

- **WHEN** a complete listing returns 40 documents and `document_type_key` is not set
- **THEN** the block SHALL be the line `Document statistics:` and one overall line, with no `By`
  line

#### Scenario: An empty collection

- **WHEN** the first page reports a `total_count` of 0 and returns no results
- **THEN** the block SHALL be the lines `Document statistics:` and
  `0 documents, publication dates unknown.`

### Requirement: The data-sources string reaches the calls that plan, research and write

The **data-sources string** of a turn SHALL be built from these parts, in this order, each
present only under its condition:

1. the document statistics block, when the channel configures a `generic_rag` server that sets
   `document_stats`: its figures when the listing was complete, and its failure text when it was
   not (see **The documents are listed page by page**);
2. the `generic_rag` server's `description`, inside a `<documents_description>` tag, when that
   server sets one;
3. the datasets section, when the channel configures a `statgpt` server;
4. the `statgpt` server's `description`, inside a `<datasets_description>` tag, when that server
   sets one;
5. the rendered glossary string, when that server configures a `glossary`.

The parts present SHALL be joined with one blank line between each two. A part that is absent
SHALL leave nothing behind: no heading and no blank line. A part belongs to the server type that
serves it, so a part never appears on a channel that does not configure that server type. A
`generic_rag` server sets a `description` or `document_stats` (see **application-config-schema**),
and a `statgpt` server always gives a datasets section, so the string is never empty.

The parts SHALL be written one after another, with no tag or heading that groups them by server.

**A description is wrapped in a tag of its own.** It SHALL be written as the opening tag on a line
of its own, the description as configured, and the closing tag on a line of its own, each
separated by a newline: `<documents_description>` and `</documents_description>` around the
`generic_rag` server's, `<datasets_description>` and `</datasets_description>` around the
`statgpt` server's. An admin writes a description, and it often carries Markdown headings of its
own; the tag marks where it ends, so the part that follows it is not read as belonging under its
last heading. The fetched parts SHALL NOT be wrapped: each already starts with a label line of its
own.

The data-sources string SHALL be what every model call receives as the description of the
channel's data sources: the preparation agent and the query clarity check (see
**clarification-and-plan-alignment**), and the playground agent. It SHALL also be what every call
of the research graph receives — research-agent, research-review, the report writer and
report-review (see **research-execution**).

The plan approval check SHALL receive neither the data-sources string nor any part of it: it judges
whether the user approved the recorded plan, which none of it bears on.

**The playground agent.** Its system prompt SHALL carry the data-sources string in the place that
describes the data sources. Its other inputs are unchanged.

#### Scenario: The combined string reaches the preparation agent

- **WHEN** a turn runs on a channel whose `generic_rag` server sets a `description` and
  `document_stats` whose pages were all obtained, and whose `statgpt` server sets no
  `description`, names a dataset-structure tool and configures a glossary that listed terms
- **THEN** the preparation agent's system prompt SHALL carry the document statistics block, a
  blank line, the document server's description inside its `<documents_description>` tag, a blank
  line, the datasets section with its structures block, a blank line, and the rendered glossary
  string, in that order

#### Scenario: The dataset server's description follows the datasets section

- **WHEN** a turn runs on a channel whose `statgpt` server sets a `description` and configures a
  glossary
- **THEN** the data-sources string SHALL carry the datasets section, a blank line, the description
  inside its `<datasets_description>` tag, a blank line, and the rendered glossary string, in that
  order

#### Scenario: A description's headings stay inside its tag

- **WHEN** the `generic_rag` server's `description` starts with `## Publication types` and ends
  inside a `### Newsletter` subsection, and the channel has a `statgpt` server
- **THEN** the data-sources string SHALL carry the line `<documents_description>`, the description,
  the line `</documents_description>`, a blank line, and then the datasets section, so the
  datasets section stands outside the description's headings

#### Scenario: A description of an unconfigured server type cannot appear

- **WHEN** a turn runs on a channel whose only MCP server is a `generic_rag` server that sets a
  `description` and no `document_stats`
- **THEN** the data-sources string SHALL be that description inside its `<documents_description>`
  tag, with no datasets section and no glossary

#### Scenario: A failed documents listing gives its failure text

- **WHEN** a page of the documents listing could not be obtained, and the `generic_rag` server
  sets a `description`
- **THEN** the data-sources string SHALL start with the lines `Document statistics:` and
  `failed to obtain list of documents`, followed by a blank line and the description inside its
  `<documents_description>` tag, and SHALL carry no document figures

#### Scenario: A failed fetch still reaches the prompts

- **WHEN** all three list-terms attempts failed
- **THEN** the preparation agent, the query clarity check, the playground agent and every call of
  the research graph SHALL receive the data-sources string ending in the failure text, and the
  report reviewer SHALL be given the glossary-terminology check only if the research agent obtained
  a successful glossary tool result

#### Scenario: A failed list of datasets still reaches the prompts

- **WHEN** all three list-datasets attempts failed
- **THEN** every call that receives the data-sources string SHALL receive it with a datasets
  section carrying `failed to obtain list of datasets`

### Requirement: An agent that can call the dataset tools is told which calls are done and which failed

The system prompt of the research agent SHALL tell the agent, for each of the two dataset tools,
whether the app's own calls succeeded. A tool whose answer the datasets
section shows SHALL NOT be called again for that answer. A tool whose call failed after the app's
retries SHALL be called by the agent when it needs the answer, because the agent's call is the
fallback for a failure the app's retries did not overcome. The instruction SHALL name each tool as
the agent is offered it, and SHALL carry these parts:

- **The list succeeded**: the datasets section holds the list-datasets tool's answer, so the agent
  SHALL NOT call the list-datasets tool.
- **The list failed**: the app could not obtain the list of datasets, so the agent SHALL call the
  list-datasets tool when it needs to know which datasets exist, making **at most three**
  list-datasets calls in the whole research.
- **Structures were fetched**: the structures block holds the dataset-structure tool's answer for
  every dataset whose entry is not a failure entry. The agent SHALL NOT call the structure tool for
  such a dataset, and SHALL call it for a dataset whose entry is a failure entry when it needs that
  structure, making **at most three** structure calls for that dataset in the whole research.
- **The list failed and the server names a dataset-structure tool**: no structure was fetched, so
  the agent SHALL call the structure tool for each dataset whose structure it needs, making **at
  most three** structure calls for each dataset in the whole research. This part SHALL appear only
  when the list-datasets tool is bound too, because without the list the agent has no dataset id to
  pass.

The limit of three calls is the same bound the research agent's failed-tool rule sets, one call and
two repeats (see **research-execution**), and the same limit the glossary instruction states.

Each part about a tool SHALL appear only when that tool is among the tools bound to the agent.

**The playground agent** SHALL carry only the parts about a failed call — the failed list and the
failure entries — and never a part that tells it not to call a tool. The playground exists to
exercise the MCP tools, and its user may ask it to call either tool whatever the fetch obtained.

No other model call SHALL carry any part of the instruction.

#### Scenario: Both tools succeeded and are bound

- **WHEN** a research turn runs on a channel whose list and structure calls all succeeded, and the
  research agent's tools include both tools
- **THEN** the research agent's system prompt SHALL tell it not to call either tool for the
  datasets the section shows, naming both tools

#### Scenario: A failed list tells the agent to call the tool

- **WHEN** all three list-datasets attempts failed, and the list-datasets tool is bound to the
  research agent
- **THEN** the research agent's system prompt SHALL tell it to call the list-datasets tool when it
  needs to know which datasets exist, at most three times

#### Scenario: A failed structure tells the agent to request it

- **WHEN** the structures block carries a failure entry for dataset `B`, and the structure tool is
  bound to the research agent
- **THEN** the research agent's system prompt SHALL tell it to call the structure tool for the
  datasets whose entry is a failure entry, and not to call it for the others

#### Scenario: The structure tool is filtered out

- **WHEN** the server's `tools_to_include` omits the dataset-structure tool
- **THEN** no system prompt SHALL carry a part about the structure tool, and the structures block
  SHALL still reach every call that receives the data-sources string

#### Scenario: A failed list without the list tool gives no structure part

- **WHEN** all three list-datasets attempts failed, and the research agent's tools include the
  structure tool but not the list-datasets tool
- **THEN** the research agent's system prompt SHALL NOT tell it to call the structure tool

#### Scenario: The playground is never told not to call a tool

- **WHEN** a playground turn runs on a channel whose list and structure calls all succeeded
- **THEN** the playground agent's system prompt SHALL carry no part of the dataset-tools
  instruction

#### Scenario: The preparation calls are never told to call a dataset tool

- **WHEN** all three list-datasets attempts failed
- **THEN** neither the preparation agent's nor the query clarity check's system prompt SHALL tell
  the model to call the list-datasets tool or the dataset-structure tool, because preparation has
  no MCP tools

### Requirement: Preparation plans around a failed list of datasets

A failed list of datasets SHALL NOT stop preparation. When all three list-datasets attempts failed,
the preparation agent's system prompt SHALL carry an instruction with two parts:

- the failure SHALL NOT hold up clarification or the plan, and the agent SHALL NOT ask the user to
  wait, to retry, or to choose datasets it cannot name;
- when the query needs data the datasets would hold, the plan SHALL carry an item that asks
  research to search the available datasets for that data, and that says the list of datasets
  could not be obtained at the moment, so no specific dataset can be suggested yet. An example of
  such an item: "Search the available datasets for X. The list of datasets could not be obtained at
  the moment, so no specific datasets can be suggested yet."

The instruction SHALL also state that the preparation rule requiring the plan to name every data
source that plausibly covers the query topic does not apply to a data source whose listing failed,
which today means the datasets. The search item takes the place of the named datasets. Without this
exception the two rules would contradict each other, because no dataset can be named.

The instruction SHALL NOT appear when the list succeeded, or on a channel with no dataset server.
The query clarity check gets no such instruction, because it does not ask the user to choose a
dataset in any case.
The research agent needs no such instruction: the plan item reaches it through the approved plan,
and its own instruction tells it to call the list-datasets tool when the app's list failed.

#### Scenario: A failed list adds a search item to the plan

- **WHEN** all three list-datasets attempts failed, and the user asks for GDP growth forecasts
  that the datasets would hold
- **THEN** the preparation agent's system prompt SHALL carry the instruction, and the plan the agent
  records SHALL carry an item asking research to search the available datasets for GDP growth,
  saying that no specific dataset can be suggested because the list could not be obtained

#### Scenario: A successful list gives no such instruction

- **WHEN** the list-datasets call succeeded
- **THEN** the preparation agent's system prompt SHALL NOT carry the instruction about a failed
  list

### Requirement: An agent that can call the glossary tools is told which calls are done and which failed

The system prompt of the research agent and of the playground agent SHALL tell the agent to repeat,
with its own tool calls, the parts of the glossary fetch that failed after the app's retries. The
agent's calls are the fallback for a failure the app's retries did not overcome. When the fetch
obtained the whole glossary, the research agent SHALL be told not to call the glossary tools. The
instruction SHALL name each tool as the agent is offered it, and SHALL carry these parts:

- **The list of terms failed**: the app could not obtain the glossary's terms, so the agent SHALL
  call the list-terms tool to obtain them, making **at most three** list-terms calls in the whole
  research.
- **Some terms have no definition**, or the list failed: the agent SHALL call the term-definitions
  tool for the terms that have no definition and whose names look relevant to the task, requesting
  each term's definition in **at most three** calls in the whole research.
- **The glossary is complete**: the list of terms succeeded and every listed term resolved, so the
  agent SHALL NOT call the list-terms tool or the term-definitions tool. The part SHALL name each of
  the two tools that is bound, and SHALL appear only when at least one of them is bound.

The limit of three calls is the same bound the research agent's failed-tool rule sets, one call and
two repeats (see **research-execution**), so the agent's retries stay bounded when the server keeps
failing.

The part about the list-terms tool SHALL appear only when the list failed and that tool is among
the tools bound to the agent. The part about the term-definitions tool SHALL appear only when that
tool is bound and the list failed or at least one listed term did not resolve.

**The playground agent** SHALL carry only the parts about a failed call, and never the part about a
complete glossary, because its user may ask it to call either tool whatever the fetch obtained.

No other model call SHALL carry any part of the instruction. Every other call sees an unresolved term only as a `null` definition, and
a failed list only as the failure text.

**What the agent's retries reach.** A term or a definition the agent obtains is a tool result:
research-review sees it in the rendered findings, and the report writer sees it in the transcript.
The report reviewer receives no tool results except these: the app selects the agent's successful
results of the two configured glossary tools by name and passes their text to the reviewer (see
**research-execution**). So the writer's rule and the reviewer's check both count the agent's
results (see **report-composition**), and the References section's glossary table reads a cited
term's definition from them when the app's fetch did not resolve it (see **report-citations**).

#### Scenario: A failed list tells the agent to list the terms

- **WHEN** all three list-terms attempts failed, and the research agent's tools include the
  list-terms tool and the term-definitions tool
- **THEN** the research agent's system prompt SHALL tell it to call the list-terms tool at most
  three times, and to request the definitions of the relevant terms it obtains, each in at most
  three calls

#### Scenario: Unresolved terms are re-requested by the agent

- **WHEN** the glossary listed 25 terms, 2 did not resolve, and the research agent's tools include
  the term-definitions tool
- **THEN** the research agent's system prompt SHALL tell it to request the definitions of those of
  the 2 terms that look relevant, each in at most three calls, and SHALL NOT tell it to call the
  list-terms tool

#### Scenario: A complete glossary tells the research agent not to call the glossary tools

- **WHEN** the glossary listed 25 terms and all 25 resolved, and the research agent's tools include
  the list-terms tool and the term-definitions tool
- **THEN** the research agent's system prompt SHALL tell it not to call either tool, naming both,
  and SHALL NOT tell it to call either tool

#### Scenario: The playground is never told not to call a glossary tool

- **WHEN** a playground turn runs on a channel whose glossary listed 25 terms and all 25 resolved
- **THEN** the playground agent's system prompt SHALL carry no part of the glossary instruction

#### Scenario: The tool is filtered out

- **WHEN** the server's `tools_to_include` omits the term-definitions tool
- **THEN** neither the research agent's nor the playground agent's system prompt SHALL carry the
  part about it, and the glossary SHALL still reach them

### Requirement: A data-sources fetch never fails the turn

No failure of the data-sources fetch SHALL fail the turn. A failed list of datasets or of terms
SHALL become its failure text, a structure that was not obtained SHALL become a failure entry, a
term that did not resolve SHALL stay listed without a definition, and a documents listing that ended
incomplete SHALL render the document statistics block as its failure text. The only exception is
cancellation, which SHALL propagate.

#### Scenario: A cancelled turn is not turned into a failure text

- **WHEN** the turn is cancelled while the data-sources fetch is waiting for a call
- **THEN** the cancellation SHALL propagate, no further attempt SHALL be made, and no failure text
  SHALL be rendered

#### Scenario: The server is unreachable

- **WHEN** every data-sources call fails because the server cannot be reached
- **THEN** the turn SHALL continue to the preparation agent with the failure texts of the list of
  datasets, the list of terms and the documents listing in its data-sources string, and no error
  SHALL be delivered to the user for the data sources

### Requirement: The datasets fetch is recorded in the logs

Every datasets fetch SHALL log one INFO event when it ends, carrying the server name, the number of
list-datasets attempts made, the number of listed datasets, the number of structures requested,
the number obtained, the number not obtained, and the fetch's duration. When the list failed, the
event SHALL carry the listed count as absent rather than as zero, so a failed list is not read as
an empty catalogue.

The app SHALL log one WARNING when the list-datasets tool failed three times, naming the server and
the kind of the last failure. It SHALL log one WARNING when at least one structure was not
obtained, naming the server and the number not obtained. Neither is an ERROR, because the turn
continues (see **logging-policy**).

These records follow the **logging-policy** content allowlist: names, counts, durations and failure
kinds. They SHALL NOT carry a dataset id, a dataset name, a tool's answer, or a failure's own text,
because the catalogue is the client's content.

#### Scenario: A complete fetch

- **WHEN** a fetch lists 5 datasets and obtains all 5 structures
- **THEN** one INFO event SHALL state one list attempt, 5 listed, 5 requested, 5 obtained, 0 not
  obtained and the duration, and no WARNING SHALL be logged

#### Scenario: Failed structures are counted, not named

- **WHEN** two structures are not obtained after three attempts each
- **THEN** one WARNING SHALL state the server name and the number 2, and no log record SHALL carry
  either dataset's id

### Requirement: The glossary fetch is recorded in the logs

Every glossary fetch SHALL log one INFO event when it ends, carrying the server name, the number of
list-terms attempts made, the number of listed terms, the number of resolved terms, the number of
unresolved terms, the number of definition rounds run, and the fetch's duration. When the list
failed, the event SHALL carry the listed count as absent rather than as zero, so a failed list is
not read as an empty glossary.

The app SHALL log one WARNING when the list-terms tool failed three times, naming the server and
the kind of the last failure. It SHALL log one WARNING after the last round when at least one term
did not resolve, naming the server and the number of unresolved terms. Neither is an ERROR, because
the turn continues (see **logging-policy**).

These records follow the **logging-policy** content allowlist: names, counts, durations and failure
kinds. They SHALL NOT carry a term name, a definition, a tool's arguments, a tool's answer, or a
failure's own text, because term names and definitions are the client's content.

#### Scenario: A complete fetch

- **WHEN** a fetch lists 25 terms and resolves all of them in the first round
- **THEN** one INFO event SHALL state one list attempt, 25 listed, 25 resolved, 0 unresolved, one
  round and the duration, and no WARNING SHALL be logged

#### Scenario: Unresolved terms are counted, not named

- **WHEN** two terms do not resolve after three rounds
- **THEN** one WARNING SHALL state the server name and the number 2, and no log record SHALL carry
  either term's name

### Requirement: The documents fetch is recorded in the logs

Every documents fetch SHALL log one INFO event when it ends, carrying the server name, the number of
pages obtained, the total number of page attempts made, the number of documents the obtained pages
carried (an incomplete listing's included), the `total_count` the first page reported, the number of
type groups, whether the listing was complete, and the fetch's duration. When the first page was not
obtained, the event SHALL carry the reported total as absent rather than as zero, so a failed
listing is not read as an empty collection.

The app SHALL log one WARNING when the listing ended incomplete, naming the server, the `offset` at
which it ended, and why: the kind of the last failure of the page at that offset, that the page
returned no results, or that the page cap was reached. It is not an ERROR, because the turn
continues (see **logging-policy**).

These records follow the **logging-policy** content allowlist: names, counts, offsets, durations
and failure kinds. They SHALL NOT carry a document's title, metadata, type or date, or a tool's
answer, because the collection is the client's content.

#### Scenario: A complete fetch

- **WHEN** a fetch lists 250 documents in three pages, each on its first attempt, with 4 type
  groups
- **THEN** one INFO event SHALL state 3 pages, 3 attempts, 250 documents, a total of 250, 4
  groups, a complete listing and the duration, and no WARNING SHALL be logged

#### Scenario: A failed page is logged by its offset

- **WHEN** `page_size` is 100, the first page reports a `total_count` of 250, and the page at
  `offset` 100 fails three times with HTTP 502
- **THEN** one WARNING SHALL name the server, the offset 100 and the failure kind, the INFO event
  SHALL state 1 page, 4 attempts and 100 documents, and no log record SHALL carry a document's
  title, type or date
