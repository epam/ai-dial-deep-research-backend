## MODIFIED Requirements

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
the one the agent read last. Records SHALL be kept for one research run only: a query id reported
in an earlier run is not resolvable in a later one. A run that failed and is resumed on a later
turn is still one run. Its snapshot saves the records captured so far, and the resumed run SHALL
start with them restored, whole, before it captures anything new (**research-resume**). A query id
reported before the failure therefore resolves in the report the resumed run delivers. A record
the resumed run captures for an id already restored SHALL replace it, as for any repeated query.

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

#### Scenario: A query captured before a failure resolves after the resume

- **WHEN** research-agent captured a record for `dq_0123abcd45` with a data explorer URL, the run
  then failed with a quota error, and on a later turn the resumed run delivers a report citing
  `[data_query dq_0123abcd45]`
- **THEN** the citation SHALL become a pill that opens that URL, exactly as it would had the run not
  failed

#### Scenario: A research run on a new plan starts with no records

- **WHEN** research starts fresh after the user changed the plan, and the history holds a snapshot
  with data-query records for the old plan
- **THEN** the run SHALL start with no records, and a query id from the old run SHALL NOT resolve
