## MODIFIED Requirements

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

### Requirement: A data-sources fetch never fails the turn

No failure of the data-sources fetch SHALL fail the turn. A failed list of datasets or of terms
SHALL become its failure text, a structure that was not obtained SHALL become a failure entry, a
term that did not resolve SHALL stay listed without a definition, and a documents listing that
ended incomplete SHALL render the document statistics block as its failure text. The only exception is
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

## ADDED Requirements

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

### Requirement: The documents fetch is recorded in the logs

Every documents fetch SHALL log one INFO event when it ends, carrying the server name, the number
of pages obtained, the total number of page attempts made, the number of documents the obtained
pages carried (an incomplete listing's included), the `total_count` the first page reported, the number of type groups, whether the listing was
complete, and the fetch's duration. When the first page was not obtained, the event SHALL carry
the reported total as absent rather than as zero, so a failed listing is not read as an empty
collection.

The app SHALL log one WARNING when the listing ended incomplete, naming the server, the `offset`
at which it ended, and why: the kind of the last failure of the page at that offset, that the page
returned no results, or that the page cap was reached. It is not an ERROR, because the turn continues (see **logging-policy**).

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
