## MODIFIED Requirements

### Requirement: A dataset citation is converted when its dataset resolves a web URL

A `[dataset <id>]` marker SHALL be converted — its marker replaced by a marker tag, one annotation
emitted for it — on one condition: **the cited dataset resolved a URL that a browser can open.**

**A dataset's identifier is called its URN throughout this capability**, and the marker's `<id>`
slot carries it: the report's citation form is `[dataset <id>]`, owned by **research-execution**, but
what fills it for every supported dataset server is a URN such as `IMF:WEO(1.0.0)`. The wire
field the list-datasets tool reports it under is `id`, which is the server's key and is not
renamed here; every user-visible mention of it — the fallback labels — reads
`URN`, because that is what the value is and what the dataset server's own documentation calls it.

**The URL a dataset citation opens is the dataset's data explorer link when it has one, and its
page otherwise.** The list-datasets tool reports both, in two places (the contract below states
them): the data explorer link in the result's `_meta` payload, and the dataset's page in the
record's `url`. The app SHALL take the data explorer link when the payload reports a usable one for
that URN, and the record's `url` when it does not. The data explorer link opens the whole dataset,
with no filter and no period, so a reader lands where the data can be looked at rather than on a
page that describes it. Falling back to the page keeps every channel whose dataset server does not
report explorer links able to cite datasets. Wherever this capability speaks of **a dataset's
page** or **its page URL** — the card's open-in-browser action, a References row that opens its
dataset, the page a data-query pill never opens — it means this URL.

A URL is usable when it is **absolute and `http` or `https`**. The app SHALL decide this from the
URL itself, treating any other form — a storage-relative `files/…` path, a scheme it does not
recognise, a value that is not a URL at all — as not usable, for both of the two sources. An
explorer link that is not usable SHALL be read as absent, so the record's `url` is used in its
place. The direction is conservative for the same reason the PDF check on a document is: a dataset
pill exists to take the reader to a page, and a pill that opens nothing is worse than a marker that
at least names its source. A storage-relative URL in particular would make the client offer a file
download rather than a page.

The URN is matched **verbatim**, as **source-attribution** requires: the string the marker carries is
compared to the `id` of each record the tool reported, with no case change, no trimming, no
re-encoding and no version-stripping. A URN carries punctuation — a colon, and often a parenthesised
version — and every character of it is part of the URN.

A dataset citation whose URN the tool did not report, or reported with neither a usable explorer
link nor a usable `url`, SHALL keep
its marker text exactly as the report writer wrote it and SHALL produce no annotation. Conversion
SHALL NOT be partial: a converted dataset citation has both its tag and its annotation, or neither.
The failure mode is a missing pill, never a lost citation.

**Neither a dataset's name nor its last-update date is part of the condition.** A dataset that
resolved a URL but no usable name is still converted, its labels reading `<urn> dataset` in place of
`<name> dataset`, the same shape with a different leading string; a dataset that resolved no date is still converted, its card title simply ending at
` dataset` with no last-update part. This is the same shape of fallback an untitled document gets, for the same reason: a
plainer pill costs the reader less than a missing one.

**Where the marker stands is not a condition**, exactly as for a document citation: the step SHALL
convert a dataset citation in a paragraph, a list item, a table cell, a heading, a blockquote and an
emphasis span alike, and SHALL classify no Markdown block.

#### Scenario: A cited dataset with an explorer link opens the data explorer

- **WHEN** a paragraph reads `…rose by 2.1% [dataset IMF:WEO(1.0.0)] over the period.`, the
  list-datasets tool reported that id with the URL `https://portal.example.org/datasets/imf-weo`,
  and its `_meta` payload reported the explorer link
  `https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)` for the same id
- **THEN** the marker SHALL be replaced by a marker tag, and one annotation SHALL be emitted naming
  that tag and carrying the explorer link

#### Scenario: A cited dataset without an explorer link opens its portal URL

- **WHEN** the list-datasets tool reported the cited dataset with the URL
  `https://portal.example.org/datasets/imf-weo`, and its result carried no `_meta` payload, or a
  payload with no explorer link for that id
- **THEN** the citation SHALL be converted, and its annotation SHALL carry the portal URL

#### Scenario: An unusable explorer link falls back to the portal URL

- **WHEN** the `_meta` payload reports the explorer link `files/bucket/explorer.html` for the cited
  dataset, and its record carries the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** the annotation SHALL carry the portal URL

#### Scenario: A reader reaches the dataset's page from the card

- **WHEN** a reader clicks a converted dataset citation's pill and then its open-in-browser action
- **THEN** the page at `body.source.attachment.url` SHALL open in a new browser tab, and that URL
  SHALL be the string the list-datasets tool reported, unchanged

#### Scenario: A dataset the catalogue does not report keeps its text

- **WHEN** the report cites `[dataset IMF:UNKNOWN(1.0.0)]` and the tool's answer carries no record
  with that id
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A dataset reported without a URL keeps its text

- **WHEN** the tool reports the cited dataset's record with a name but no URL, and its `_meta`
  payload reports no explorer link for that id
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A storage-relative URL is not convertible

- **WHEN** the tool reports the cited dataset with the URL `files/bucket/catalogue.pdf`
- **THEN** the citation SHALL NOT be converted, because the URL is not an absolute web URL and the
  client would offer a download rather than open a page

#### Scenario: A versioned identifier is matched exactly

- **WHEN** the report cites `[dataset IMF:WEO(1.0.0)]` and the tool reports both
  `IMF:WEO(1.0.0)` and `IMF:WEO(2.0.0)`
- **THEN** the citation SHALL resolve against `IMF:WEO(1.0.0)` alone, the identifier being
  matched character for character

### Requirement: Cited datasets are named and linked through a contracted list-datasets tool

A dataset citation needs three things the app does not hold: the dataset's human name, which labels
the pill and the card and leads its References row; the address of its page, which no label shows and
which the reader reaches through the card's open-in-browser action; and its last-update date, which
the card's title carries when the server knows one. All come from **one MCP tool**, the
**list-datasets tool**, and the app SHALL depend on nothing about it beyond the contract stated
here. Which server provides it, what that server names it, and where it keeps the catalogue are all
outside the contract, and the app SHALL behave identically for any server that satisfies it.

**The name comes from configuration.** Each MCP server entry in the application properties SHALL be
able to name that server's list-datasets tool, and the app SHALL call exactly the tool that entry
names (**application-config-schema** owns the field). There SHALL be no default name and no
discovery by convention: the app SHALL NOT infer the tool from a server's advertised tool list, from
a tool's description, or from any naming pattern. Only a **dataset** server may name one, and at
most one dataset server may be configured, so at most one configured server names a list-datasets
tool — which is what makes asking that server about an id correct, since a `[dataset <id>]` marker
names no server.

A dataset server **must** name one, exactly as a document server must name its file-sharing
tool, and for the same reason: the tool is the only thing that turns a cited URN into a name and a
page the reader can open, so a dataset server without it serves datasets that cannot be cited. The
rule lives in **application-config-schema**, which also records what it costs — a channel whose
dataset server advertises no catalogue tool cannot be configured.

A channel that configures **no dataset server at all** remains ordinary: nothing names a
list-datasets tool, no call is made, and a dataset marker in a delivered report keeps its text.
That is the case recorded at DEBUG rather than warned about on every turn (see **logging-policy**).

**The contract.** A tool named as a server's list-datasets tool SHALL satisfy all of the
following. These are requirements on the server, not observations of any one implementation: a named
tool that breaks any of them is a misconfiguration, and it SHALL fail the way the delivery-failure
requirement below prescribes rather than degrade the report.

- **Input**: none. The app SHALL call it with no arguments and SHALL pass no cited ids to it. The
  tool answers with the channel's catalogue, and the app selects from that answer.
- **Output**: one JSON object at the top level carrying a **`datasets`** array. Each element SHALL
  carry a string **`id`**, the URN the report's `[dataset <id>]` markers carry and the
  dataset-query tools accept; a string **`name`**, the dataset's human name; and MAY carry two
  further strings — **`url`**, the address of that dataset's own page, and **`lastUpdated`**, the
  date the dataset was last updated. Any other field an element carries SHALL be ignored for the
  purposes of the pill, and SHALL be available to a References row, which reads the fields its
  columns configure — so a server may report a description, a provider or an indicator count
  without breaking the contract, and a channel may put any of them in a column.

  The two named optional fields are optional in different senses, and the difference is what each
  absence costs. An element whose **`url`** is absent, and whose dataset has no explorer link in
  the `_meta` payload, is a dataset that cannot be cited as a pill at all, because the pill would
  open nothing; it is still a cited dataset and still gets a References row. An element whose
  **`lastUpdated`** is absent is cited normally and simply carries one fewer fact on its card.
  Neither absence is a malformed answer.

  `lastUpdated` SHALL be a date the reader can act on, written as an **ISO 8601 date** such as
  `2025-04-30`. A server that cannot produce one SHALL omit the field rather than send free text it
  failed to parse, because the app displays this value verbatim and cannot tell a date it does not
  understand from one it does. A value that reaches the app as anything but a non-empty string SHALL
  be read as absent.
- **Structured result**: the tool SHALL return that object as its MCP **structured result**, which
  means declaring the output schema MCP requires for one. The app reads the structured result and
  nothing else — a tool that answers with text content alone SHALL be treated as a failed call. MCP
  carries the same object a second time as serialized text, which the app ignores.
- **Explorer links**: the result MAY carry, in its MCP `_meta` under the key the server's
  `client_meta_key` names (**application-config-schema** owns the field), matched character for
  character, a JSON object carrying a **`datasets`** array. Each element SHALL carry a string
  **`id`**, the same URN the structured result's record carries, and MAY carry a string
  **`dataExplorerUrl`**, the address that opens that whole dataset in the data explorer. The app
  reads nothing else from the payload: any other field, such as a citation URL, SHALL be ignored.
  An element is matched to its record by `id`, verbatim, never by position. The payload is outside
  what a model reads, and the app SHALL NOT show it to one.

  The payload is optional, and so is each element's link. A missing or unreadable payload, a
  missing element, and an element whose link is absent or is not a string SHALL each cost only the
  explorer link of the datasets concerned, which then open their `url`. None of them makes the
  answer a failed call, because the structured result alone still names and links every dataset.
- **Complete for the channel**: the answer SHALL carry every dataset the channel exposes, because
  the app cannot ask about a subset. A dataset absent from the answer is uncitable.
- **Idempotent and read-only**: the app calls the tool once per turn, and repeated calls across
  turns SHALL be safe and SHALL change nothing on the server.

The app SHALL call the tool **once per turn** when it succeeds. The call SHALL be made at the start
of every turn, before the preparation agent's first model call, by the data-sources fetch, which
also shows the answer to the models (see **data-sources-discovery**). On a turn that reaches
research, that answer is the catalogue the report review and the delivery read: every draft's check
and the delivery reuse it (see the requirement on looking cited identifiers up once per turn). When
that fetch failed, the answer is not reused and no catalogue is held, so the first check of a draft
that cites a dataset calls the tool again, and a failure there is again not reused, so the next
check or the delivery calls again. It SHALL NOT call the tool once per cited dataset.

The app SHALL select from the answer **every** record whose `id` equals a cited id, and SHALL ignore
every other record. Selection SHALL NOT depend on what a record carries: a record with no usable page
URL is selected like any other, because the pill is not the only thing that reads it. What a missing
URL costs is decided where the pill is decided, not here. That the answer is the whole catalogue is a
property of the contract rather than a cost the report pays per citation: one call carries however
many datasets the report cites.

#### Scenario: One call serves every cited dataset

- **WHEN** three reviewed drafts and the delivered report cite four datasets, research queried
  three more that no draft cites, and the data-sources fetch's first list-datasets attempt
  succeeds
- **THEN** the app SHALL call the list-datasets tool exactly once, with no arguments, in the
  data-sources fetch at the start of the turn, and SHALL read the four cited ids out of that one
  answer

#### Scenario: A report citing no dataset makes no call

- **WHEN** every reviewed draft and the delivered report cite documents only
- **THEN** the report review and the delivery SHALL NOT call the list-datasets tool, and every
  list-datasets call of the turn SHALL be one the data-sources fetch made at its start

#### Scenario: A failed turn-start call is made again for a cited dataset

- **WHEN** every attempt of the data-sources fetch's list-datasets call failed, and the first
  reviewed draft cites a dataset
- **THEN** the review of that draft SHALL call the list-datasets tool, and a successful answer SHALL
  serve every later check and the delivery

#### Scenario: A record with no page URL is still selected

- **WHEN** a cited dataset's record carries an `id` and a `name` and no `url`, and the `_meta`
  payload reports no explorer link for it
- **THEN** that record SHALL be selected, its citations SHALL keep their marker text for want of a
  page to open, and its References row SHALL carry its name

#### Scenario: An explorer link alone makes a dataset citable

- **WHEN** a cited dataset's record carries an `id` and a `name` and no `url`, and the `_meta`
  payload reports `https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)` for that id
- **THEN** its citations SHALL become pills opening that explorer link, and its References row SHALL
  open the same link

#### Scenario: An unreadable payload costs the explorer links only

- **WHEN** the list-datasets result carries a structured result with a `datasets` array, and under
  the configured `_meta` key a value that is not an object carrying a `datasets` array
- **THEN** the call SHALL be a successful one, and every cited dataset SHALL open the `url` its
  record carries

#### Scenario: Extra fields in a record are available to a row

- **WHEN** a reported record carries a description and a provider beside its `id`, `name`, `url` and
  `lastUpdated`, and the channel configures a column reading the provider
- **THEN** the record SHALL be accepted, the pill SHALL be built from the `name` and the `url`
  alone, and the References row SHALL carry the provider in its configured column

#### Scenario: A text-only answer is a failed call

- **WHEN** the named tool returns its catalogue as text content with no structured result
- **THEN** the call SHALL be treated as failed, every dataset citation SHALL keep its marker text,
  and the report SHALL be delivered

### Requirement: The list-datasets tool is called by the app and stays available to the agent

At the citation step, when the turn-start fetch did not obtain the catalogue, the app SHALL find
the list-datasets tool in its server's **full advertised tool list**,
independently of that server's `tools_to_include` filter, because that filter states what the
research agent may call rather than what the app may call. A configuration whose filter omits the
tool SHALL still leave the app able to call it at the citation step.

That call SHALL read the **MCP result itself**, in a session of its own on the turn's connection to
the server, rather than the tool message the research agent would read, because the tool message
carries the structured result and drops `_meta`, where the explorer links are. It SHALL read the
same two parts the turn-start fetch reads, by the same rules, so a catalogue obtained by either
call opens the same URLs. The call carries no deadline of its own beyond the connection's
timeouts.

The list-datasets tool SHALL, however, **remain available to the research agent** whenever that
server's filter would otherwise offer it. This is the one point on which it differs from the
file-sharing tool, which the app removes from every tool list bound to a model, and the difference
is deliberate: a catalogue listing is how a research agent discovers which datasets exist before it
queries one, so removing it would spend the research to buy the citation. Naming a tool here SHALL
change only who else calls it, never whether the agent still can.

#### Scenario: Naming the tool does not hide it from the agent

- **WHEN** a server names its list-datasets tool and that tool passes the server's
  `tools_to_include` filter
- **THEN** the tools bound to the research agent SHALL still include it

#### Scenario: A filter that omits it does not hide it from the app

- **WHEN** a server's `tools_to_include` names only its data-query tool, and its list-datasets
  tool is configured
- **THEN** the app SHALL still be able to call the list-datasets tool at the citation step, and
  the agent SHALL NOT be offered it

#### Scenario: The citation-step call keeps the explorer links

- **WHEN** every attempt of the turn-start list-datasets call failed, the report review calls the
  tool, and its result carries explorer links under the configured `_meta` key
- **THEN** the dataset citations the delivery converts SHALL open those explorer links

### Requirement: Data-query records are captured from the turn's tool results

A data-query citation needs four things the report does not hold: the address that opens the cited
query in the dataset server's data explorer, the URN of the dataset the query ran against, the
number of series the query returned, and the query's filter, which the citation's card shows. The
dataset server reports all four when it runs a query, in the same tool result the research agent
reads, and the app SHALL take them from there. It SHALL NOT ask the server again at the citation
step: a query id means something only in the result that reported it.

**Which results are captured.** A tool result from the configured `statgpt` server is a data-query
result when its `_meta` carries, under the key the server's `client_meta_key` names
(**application-config-schema** owns the field), matched character for character, a payload that
carries a `queries` field. A result without that payload contributes nothing, whatever tool produced
it, so the app SHALL NOT need to know which of the server's tools runs queries. The same key carries
other tools' payloads too — the list-datasets tool's carries a `datasets` array and no `queries` —
so a payload without a `queries` field SHALL contribute no record and SHALL NOT count as an
unreadable payload.

**Where the app reads them.** A data-query result carries two parts the app reads. The structured
result is also serialized into the text content the model reads. The `_meta` payload is outside
what a model reads, which is why a channel keeps the data explorer URL there and out of the
structured result:

- **The `_meta` payload**, a JSON object carrying a **`queries`** array. Each element SHALL carry a
  string **`queryId`**, and MAY carry a string **`dataExplorerUrl`**, the address that opens that
  query's data in the data explorer. The app reads nothing else from the payload.
- **The structured result**, which MAY carry a **`queries`** array whose elements carry a string
  `queryId`. An element MAY carry a string **`datasetUrn`**, the URN of the queried dataset; an
  integer **`seriesCount`**, the number of series the query returned; **`filters`**; and a
  **`requestedPeriod`**. Each filter carries a `dimensionId`, an `operator`, and a `values` array
  whose elements carry an `id`, the code the query used; a filter MAY carry a `dimensionName`, and
  a value MAY carry a `name`. The requested period MAY carry a `startPeriod` and an `endPeriod`.

The data explorer URL SHALL be read from the `_meta` element and from nothing else. Every other
field a citation uses SHALL be read from the structured element. The dataset URN comes from the
structured element because that is the spelling the writer saw in the tool's text content, so the
URN the catalogue is searched for is the URN a `[dataset <urn>]` citation of the same dataset would
carry.

**One result may report several queries**, one per element of `queries[]` — a query that ran
against two datasets, for example, reports one query per dataset. Every element SHALL become its own
record, and the two parts SHALL be joined element to element by `queryId`, never by position. A query
id present in only one of the two parts still becomes a record, carrying what that part reported.
The structured result's **`candidateDatasets`** are read as well: each element MAY carry a
`query`, which becomes the structured-content element of a record for its `queryId`. A candidate is
a query the server offers to run on another dataset. It did not run, so its record has no `_meta`
element, has no explorer link and did not return data (the terms are defined below). It is kept so
the report review can tell a writer that cited it that the query returned no data, rather than that
its id is unknown.

The fields named above are the only ones the app reads. It SHALL NOT refuse an element for carrying
other fields, and it SHALL keep each element whole on its record (see below). A missing or
unreadable part SHALL cost only what that part is for. A missing `_meta` element costs the pill and
the References row. A missing structured element costs the dataset, the series count and the
filter. An unreadable filter costs its own item on the card.

**Assumptions about the data-query server.** This capability relies on the following, which hold
for the StatGPT data-query tool on a correctly configured channel; a channel's configuration faults
are out of scope:

1. A query that ran and **returned data** carries a `seriesCount` greater than zero in its
   structured element and a `dataExplorerUrl` in its `_meta` element.
2. A query that ran and **returned no data** carries no `seriesCount`, and may carry a
   `dataExplorerUrl`. It backs no value. The report review asks the writer to replace or drop a
   citation of it (**report-composition**); one that survives the review is still resolved as well
   as it can be.
3. A query that **did not run** — constructed only, or offered for a candidate dataset — carries no
   `seriesCount` and no `dataExplorerUrl`, and a candidate has no `_meta` element at all.
4. A query id identifies one query within the turn, and the same query run on the same day reports
   the same id.

**What a model reads is unchanged.** Capturing SHALL NOT alter the content a tool result delivers to
the research agent, SHALL NOT add a data explorer URL or anything else to it, and SHALL NOT fail or
delay the tool call. A payload that cannot be read SHALL cost that result's records and nothing
else: the tool call succeeds for the agent exactly as it would with no capture at all, and the
citation step reports the count (see **logging-policy**).

**What the capture keeps.** The app SHALL keep, for the rest of the turn, a map from each
`queryId` to one record with exactly two keys:

- **`_meta`** — that query's element of the `_meta` payload's `queries`, whole, as the server sent
  it; absent when the payload did not report the id.
- **`structured_content`** — that query's element of the structured result's `queries`, or the
  `query` of its `candidateDatasets` element, whole; absent when the structured result did not
  report the id.

Nothing is renamed, derived or dropped at capture. Everything a citation uses is read out of those
two elements: the data explorer URL from the `_meta` element, and the dataset URN, the series
count, the filters and the requested period from the structured element.

**Three terms describe a captured record.** This capability and **report-composition** use them,
and each is decided by one field:

- **A query with an explorer link** is a record whose `_meta` element carries a `dataExplorerUrl`
  that a browser can open: an absolute `http` or `https` URL, judged by the rule a dataset
  citation's URL is judged by. This term decides the delivery. A citation of such a query becomes a
  pill and contributes a References row; a citation of any other query stays text and contributes
  no row.
- **A query that returned data** is a record whose structured element carries a `seriesCount`
  greater than zero. This term decides the report review: only such a query may be cited
  (**report-composition**).
- **The query's dataset** is the dataset whose URN the record's structured element carries as
  `datasetUrn`. Its name, its last-update date and its page URL are what the list-datasets tool
  reports for that URN.

The first two terms are independent of each other. A query that returned data may lack an explorer
link, on a channel that publishes none for its dataset: its citation passes the review and is
delivered as text. A query with an explorer link may have returned no data: the review catches its
citation, and a citation the review leaves in place is still delivered as a pill, because a pill
that opens the query the report named serves the reader better than a bare id.

Keeping the elements whole means a later feature that shows more of a query reads a field the
record already holds, rather than a change to the capture. When a later result reports a `queryId`
already kept, the later record SHALL replace the earlier one. A query id is stable for the same
query run on the same day, so a repeated query reports the same id, and the latest report of it is
the one the agent read last. Records SHALL be kept for one turn only: a query id reported in an
earlier turn is not resolvable in a later one.

**Why capture rather than read the tool messages.** The MCP adapter the app builds its tools with
passes the structured result on to the tool message and discards `_meta`, so by the time a tool
message exists the data explorer URL is gone. The capture is the only point in the turn where both
parts are in hand.

#### Scenario: An executed query is captured with its link

- **WHEN** a data-query tool result carries, under the configured `_meta` key, a query with
  `queryId` `dq_0123abcd45` and a `dataExplorerUrl`
  `https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE+US.GDP`, and its structured
  result carries the same `queryId` with `datasetUrn` `IMF:WEO(1.0.0)` and `seriesCount` `2`
- **THEN** the app SHALL keep a record for `dq_0123abcd45` carrying that URL, that URN and that
  series count, and the tool message the research agent reads SHALL carry no URL it did not carry
  before

#### Scenario: A constructed query that did not run is captured without a link

- **WHEN** a tool result reports a query that the server constructed but did not run, so its
  `_meta` element carries a `queryId` and no `dataExplorerUrl`, and its structured element carries
  no `seriesCount`
- **THEN** the app SHALL keep a record for that id that has no explorer link and did not return data

#### Scenario: One result reporting two queries yields two records

- **WHEN** a data-query result's `_meta` payload and structured result each carry two query
  elements, `dq_0000000001` against `IMF:WEO(1.0.0)` and `dq_0000000002` against
  `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)`, listed in a different order in the two parts
- **THEN** the app SHALL keep two records, each joining the `_meta` element and the structured
  element that carry its own `queryId`

#### Scenario: A record keeps the elements whole

- **WHEN** a structured-result element carries `querySummary`, `datasetName` and `factualPeriod`
  beside the fields the app reads
- **THEN** the record SHALL hold that element with all of those fields, although no citation reads
  them

#### Scenario: Candidate queries are kept without a link

- **WHEN** a result asks for a dataset to be selected, so its structured result carries
  `candidateDatasets` whose elements each carry a query with a `queryId`
- **THEN** the app SHALL keep a record for each of those ids carrying only `structured_content`, and
  none of them SHALL have an explorer link or count as a query that returned data

#### Scenario: A result without the configured key contributes nothing

- **WHEN** a tool result carries a `_meta` payload under a key other than the configured one, or
  no `_meta` at all
- **THEN** the app SHALL keep no record from it, and SHALL NOT read query ids out of its structured
  result or its text content

#### Scenario: A list-datasets payload under the same key is not a data-query payload

- **WHEN** the research agent calls the list-datasets tool, and its result carries under the
  configured key a payload with a `datasets` array and no `queries` field
- **THEN** the app SHALL keep no record from it, and SHALL NOT count it as an unreadable payload

#### Scenario: An unreadable payload costs only its own records

- **WHEN** a tool result carries a payload under the configured key whose `queries` is not an array
- **THEN** the tool call SHALL succeed for the research agent unchanged, no record SHALL be kept from
  that result, and records kept from other results SHALL be unaffected

#### Scenario: A missing structured result costs the dataset and the filter

- **WHEN** a tool result carries a readable `_meta` payload for a query with a data explorer URL,
  and no structured result
- **THEN** the app SHALL keep the record with its URL, and a citation of that query SHALL still
  become a pill, labelled with its marker text, whose card carries no filter item
