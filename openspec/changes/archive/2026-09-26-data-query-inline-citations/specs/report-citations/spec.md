## ADDED Requirements

### Requirement: Data-query records are captured from the turn's tool results

A data-query citation needs four things the report does not hold: the address that opens the cited
query in the dataset server's data explorer, the URN of the dataset the query ran against, the
number of series the query returned, and the query's filter, which the citation's card shows. The
dataset server reports all four when it runs a query, in the same tool result the research agent
reads, and the app SHALL take them from there. It SHALL NOT ask the server again at the citation
step: a query id means something only in the result that reported it.

**Which results are captured.** A tool result from the configured `statgpt` server is a data-query
result when its `_meta` carries a payload under the key the server's `data_query_meta_key` names
(**application-config-schema** owns the field), matched character for character. A result without
that payload contributes nothing, whatever tool produced it, so the app SHALL NOT need to know which
of the server's tools runs queries.

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
  `datasetUrn`. Its name, its last-update date and its page URL are what the dataset-metadata tool
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

#### Scenario: An unreadable payload costs only its own records

- **WHEN** a tool result carries a payload under the configured key whose `queries` is not an array
- **THEN** the tool call SHALL succeed for the research agent unchanged, no record SHALL be kept from
  that result, and records kept from other results SHALL be unaffected

#### Scenario: A missing structured result costs the dataset and the filter

- **WHEN** a tool result carries a readable `_meta` payload for a query with a data explorer URL,
  and no structured result
- **THEN** the app SHALL keep the record with its URL, and a citation of that query SHALL still
  become a pill, labelled with its marker text, whose card carries no filter item

### Requirement: A data-query citation is converted when its query has an explorer link

A `[data_query <id>]` marker SHALL be converted — its marker replaced by a marker tag, one
annotation emitted for it — on one condition: **the turn captured a query with an explorer link for
that id**, as the capture requirement defines the term. Whether the query returned data is **not**
part of the condition. The report review is where a citation of a query without data is caught and
revised (**report-composition**); a citation the review leaves in place — its version budget spent,
for instance — is resolved as well as it can be.

The query id SHALL be matched **verbatim** against the captured records' `queryId`s, as
**source-attribution** requires: no case change, no trimming, no re-encoding.

A data-query citation whose id the turn never captured, or captured as a query without an explorer
link, SHALL keep its marker text exactly as the report writer wrote it and SHALL produce no
annotation. It SHALL NOT fall back to the dataset's page: a pill that opens the dataset rather than
the cited data would claim a precision the citation lost. Conversion SHALL NOT be partial, and the
failure mode is a missing pill, never a lost citation.

**Neither the query's dataset, the dataset's name, its last-update date nor the query's filter is
part of the condition.** Each costs only what it is for on the card, as the data-query annotation
requirement states.

**Where the marker stands is not a condition**, exactly as for the other two forms.

The marker form is `[data_query <id>]`, owned by **research-execution**. The `<id>` slot SHALL
accept any run of characters other than a bracket or a line break, and the id SHALL be taken
exactly as written, the way a dataset URN is.

#### Scenario: A cited query with a data explorer link becomes a pill

- **WHEN** a paragraph reads `…grew 2.9% in 2023 [data_query dq_0123abcd45].` and the turn captured
  that id with the URL `https://portal.example.org/explorer?urn=IMF:WEO(1.0.0)&filter=A.DE.GDP`
- **THEN** the marker SHALL be replaced by a marker tag, and one annotation SHALL be emitted naming
  that tag and carrying that URL

#### Scenario: A query id the turn never captured keeps its text

- **WHEN** the report cites `[data_query dq_ffffffffff]` and no tool result in the turn reported
  that id
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A query captured without a link keeps its text

- **WHEN** the report cites a query id the turn captured with no data explorer URL
- **THEN** the marker SHALL remain in the delivered text, no annotation SHALL be emitted for it, and
  no dataset pill SHALL be drawn in its place

#### Scenario: A delivered citation of a query that returned no data still becomes a pill

- **WHEN** the delivered report still cites a query id whose `_meta` element carries a data explorer
  URL and whose structured element carries no `seriesCount`, because the query ran and returned no
  data and the review's version budget ran out before a revision removed the citation
- **THEN** the marker SHALL become a pill opening that URL, and the query's dataset SHALL be listed
  in the References section

#### Scenario: A query the payload does not list keeps its text

- **WHEN** the report cites a query id that the structured result lists and the `_meta` payload of
  the same result does not
- **THEN** the marker SHALL remain in the delivered text, and the query SHALL contribute no
  References row

#### Scenario: A relative link is not convertible

- **WHEN** the captured record's data explorer URL is `explorer?urn=IMF:WEO(1.0.0)`
- **THEN** the citation SHALL NOT be converted, because the URL is not an absolute web URL

### Requirement: A data-query annotation opens the cited query and shows its filter

A converted data-query citation's annotation SHALL carry the fields every annotation carries —
`index` and `target.selector` — exactly as the annotation-payload requirement states them. It SHALL
differ from a **dataset** citation's annotation in its URL, in its labels when the query's dataset
is not known, and in its `body.quote`:

- **`body.source.attachment.type`** SHALL be `text/html`, because the URL is a page on the web, and
  that type is what makes the client's card offer the open-in-browser action.
- **`body.source.attachment.url`** SHALL be the captured data explorer URL, carried verbatim. The
  dataset's page URL SHALL NOT be used by a data-query annotation, even when the dataset-metadata
  tool reports one: the page belongs to a `[dataset <urn>]` citation and to the dataset's References
  row.
- **`body.source.attachment.title`**, the pill, names the query's dataset, and falls back
  through three forms:
  1. **`<name> dataset`**, where the name is the one the dataset-metadata tool reported for the
     query's dataset URN;
  2. **`<urn> dataset`**, the structured element's `datasetUrn`, when the tool reported no name for
     it — the catalogue carries no record for the URN, or the call failed;
  3. **`data_query <id>`**, the marker's own text, when the structured element carries no
     `datasetUrn`, so nothing says which dataset the query ran against. It carries no ` dataset`,
     because it names no dataset.

  The first two are shortened to the channel's budget with ` dataset` appended after the
  shortening, as a dataset pill is. The third SHALL NOT be shortened, for the reason an unresolved
  document label is not: it is short by construction, and a cut could eat the id. The name SHALL
  be taken from the catalogue and not from the data-query result, although the structured result
  may carry a dataset name as well: the reader should see one dataset named one way across every
  pill and every References row.
- **`body.title`**, the card's title, SHALL carry the pill's leading part whole. After a dataset
  name or a URN it goes on with ` dataset`, and then with **` - last update <date>`** when the
  dataset-metadata tool reported a last-update date for the query's dataset URN, as in
  `World Economic Outlook dataset - last update 2025-04-30`. Without a date it SHALL read
  `<name> dataset` or `<urn> dataset` alone. Where the pill reads `data_query <id>`, so does the
  card title.
- **`body.selector`** SHALL be omitted, as for a dataset citation.
- **`body.quote`** SHALL be a Markdown list describing what the query asked for, and nothing else:
  1. **One item per filter**, in the order the structured result reported them:
     `* <dimension>: <value>, <value>, …`. The dimension is the filter's `dimensionName`, or its
     `dimensionId` when no name was reported. Each value is its `name`, or its `id` when no name was
     reported, and the values are joined with `, `. Only an `in` filter carrying at least one value
     contributes an item; a filter with any other operator SHALL be left out rather than guessed
     at, because a list of values would misstate a range or an exclusion.

     **An item longer than the channel's `data_query_card_filter_max_line_chars`
     (**application-config-schema**), 80 by default, SHALL be cut to exactly that many
     characters, the ellipsis `…` counted within them**, with any whitespace left at the cut
     removed before the ellipsis, the way a pill's leading part is cut. The whole line counts, the
     `* ` and the dimension included. A filter on 35 countries therefore reads as its first few
     names and an ellipsis: the card shows what kind of selection the query made, and the data
     explorer link opens the whole of it.
  2. **One period item**, from the requested period: `* From <start> until <end>` when both bounds
     were reported, `* From <start>` when only the start was, and `* Until <end>` when only the end
     was. The item SHALL be omitted when the query reported no requested period or neither bound.
     The requested period is used rather than the period the data covers because it is the period
     the data explorer link opens. The line budget does not apply to it, because a period item is
     short by construction.

  The list carries no URN and no last-update item: the URN is what the dataset's References row
  names, and the date is in the card's title. Dates SHALL be carried with no reformatting. An item
  the app has nothing for SHALL be omitted rather than rendered as a placeholder, so a query whose
  structured result was not captured has an empty list, and then `body.quote` SHALL be omitted.

**A data query is its own source.** Within a run, two markers naming the same query id SHALL produce
one annotation. Two markers naming different query ids SHALL produce two annotations, even when both
queries ran against one dataset: they cite different data, and each entry opens its own. A
data-query citation and a `[dataset <urn>]` citation of the same dataset in one run are likewise two
sources, one opening the data and one opening the dataset's page.

#### Scenario: A data-query card shows the filter in words

- **WHEN** a converted data-query citation's captured record carries, in this order, an `in` filter
  on `Series` with the value names `Real GDP growth` and an `in` filter on `Country` with the value
  names `United States` and `Germany`, a requested period from `2020-01-01` to `2024-12-31`, and the
  catalogue reports `World Economic Outlook` last updated `2025-04-30`
- **THEN** the pill SHALL read `World Economic Outlook dataset`, the card title SHALL read
  `World Economic Outlook dataset - last update 2025-04-30`, and `body.quote` SHALL read
  `* Series: Real GDP growth`, `* Country: United States, Germany` and
  `* From 2020-01-01 until 2024-12-31`, one item per line in that order

#### Scenario: A long filter item is cut to the default budget

- **WHEN** the channel sets no `data_query_card_filter_max_line_chars`, and a captured query's
  `Country` filter carries 35 value names, so its item runs past 80 characters
- **THEN** the item SHALL be 80 characters long and end with `…`

#### Scenario: A channel's line budget sets the item length

- **WHEN** the channel sets `data_query_card_filter_max_line_chars` to `40`, and a query's card
  carries one filter item of 60 characters and one of 30
- **THEN** the first item SHALL be 40 characters long and end with `…`, and the second SHALL be
  carried whole

#### Scenario: An open-ended period names its one bound

- **WHEN** a captured query's requested period carries an `endPeriod` of `2030-01-01` and no
  `startPeriod`
- **THEN** the period item SHALL read `* Until 2030-01-01`

#### Scenario: A query with no period has no period item

- **WHEN** a captured query's structured element carries no requested period
- **THEN** `body.quote` SHALL carry no period item, and the filter items SHALL be rendered as usual

#### Scenario: A non-set operator is left out

- **WHEN** a captured query's filter carries the operator `excluded`
- **THEN** `body.quote` SHALL carry no item for that filter, and every other item SHALL be rendered
  as usual

#### Scenario: A catalogue failure costs only the name and the date

- **WHEN** a cited query was captured with a data explorer URL and a `datasetUrn`, and the
  dataset-metadata call fails
- **THEN** the citation SHALL still become a pill, labelled `<urn> dataset`, and its card title SHALL
  read `<urn> dataset` with no last-update part

#### Scenario: A query with no dataset URN is labelled with its marker text

- **WHEN** a cited query `dq_0123abcd45` was captured with a data explorer URL, and its structured
  element carries no `datasetUrn`
- **THEN** the citation SHALL become a pill opening that URL, and both the pill and the card title
  SHALL read `data_query dq_0123abcd45`

#### Scenario: A data-query pill never opens the dataset's page

- **WHEN** a cited query was captured with a data explorer URL, and the catalogue reports a page URL
  for the query's dataset
- **THEN** the annotation's URL SHALL be the data explorer URL, and the dataset's page URL SHALL
  appear in no data-query annotation

#### Scenario: Two queries of one dataset in one run are two entries

- **WHEN** a run reads `[data_query dq_0000000001] [data_query dq_0000000002]`, both captured with a
  data explorer URL and both run against `IMF:WEO(1.0.0)`
- **THEN** the run SHALL become one marker tag claimed by two annotations, each opening its own
  query's URL

### Requirement: A cited data query cites the dataset it ran against

Wherever this capability speaks of the datasets the delivered report cites, a `[data_query <id>]`
citation of a **query with an explorer link** whose record names **the query's dataset** (the
capture requirement defines both terms) SHALL count as a citation of that dataset, at the position
of that marker. This covers exactly two things:

- **The dataset-metadata call.** The app SHALL call the dataset-metadata tool on a turn whose report
  cites at least one dataset directly or through such a query, and SHALL select the catalogue
  records of both sets of URNs, still in one call.
- **The References section.** The dataset table SHALL carry one row for each distinct dataset cited
  either way, ordered by where the dataset is first cited in either form. The row is the row a
  `[dataset <urn>]` citation of the same dataset produces: its cells read the catalogue record, its
  first cell falls back to the URN, and it is openable on the dataset citation's condition, opening
  the **dataset's page**, never a query's data explorer link. A References row names the source,
  and the source a query draws on is its dataset.

It SHALL NOT cover inline conversion: a data-query citation converts on its own condition, and a
dataset marker on its own.

**A query whose dataset is not known gets a row of its own.** A cited query with an explorer link
whose structured element carries no `datasetUrn` names no dataset to list, yet it is a cited
source, and every cited source gets a row. It SHALL contribute one row to the dataset table, at the
position of its first citation. The row's first cell SHALL carry `data_query <id>`, the marker's
own text, and its other cells SHALL be empty. The row SHALL NOT be openable: a References row opens
a dataset's page, and this query names no dataset. Two citations of one such query id share one
row.

**A query without an explorer link contributes no row.** A data-query citation contributes to the
References section on exactly the condition its pill is drawn, so a data-query citation is either a
pill with a row or plain text with neither. That is the one exception to the rule that every cited
source gets a row. For an id the turn never captured it is forced: nothing the app holds says which
dataset it belongs to. For a captured query without a link it is chosen: on a correctly configured
channel a query that returned data carries a link (the capture requirement's first assumption), so
a query without one is a query the report should not have cited.

#### Scenario: A dataset cited only through queries is listed

- **WHEN** the report cites `[data_query dq_0000000001]` and `[data_query dq_0000000002]`, both
  captured with a data explorer URL and the `datasetUrn` `IMF:WEO(1.0.0)`, and never cites
  `[dataset IMF:WEO(1.0.0)]`
- **THEN** the dataset-metadata tool SHALL be called once, and the dataset table SHALL carry exactly
  one row for `IMF:WEO(1.0.0)`, opening the dataset's page when the catalogue reported one

#### Scenario: A dataset cited both ways is listed once

- **WHEN** the report first cites `[dataset IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)]`, then a data
  query whose dataset is `IMF:WEO(1.0.0)`, then a data query whose dataset is
  `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)`, both queries captured with a data explorer URL
- **THEN** the dataset table SHALL carry two rows, the direction-of-trade dataset first and the
  World Economic Outlook dataset second

#### Scenario: An uncaptured query id contributes no row

- **WHEN** the report's only dataset-server citation is `[data_query dq_ffffffffff]`, which the turn
  never captured
- **THEN** the dataset-metadata tool SHALL NOT be called, and the section SHALL carry no dataset
  table

#### Scenario: A query without an explorer link contributes no row

- **WHEN** the report's only dataset-server citation is a query captured with the `datasetUrn`
  `IMF:WEO(1.0.0)` and no data explorer URL
- **THEN** the dataset-metadata tool SHALL NOT be called, and the section SHALL carry no dataset
  table

#### Scenario: A query without a dataset URN gets a text row

- **WHEN** the report cites `[data_query dq_0123abcd45]`, captured with a data explorer URL and with
  no structured element
- **THEN** the dataset table SHALL carry a row whose first cell reads `data_query dq_0123abcd45` as
  text, whose other cells are empty, and for which no annotation is emitted

### Requirement: Cited identifiers are looked up once per turn and shared by the review and the delivery

The report review checks that every dataset and document a draft cites is one its server knows
(**report-composition** owns the checks and their wording). It learns that from the same two
surfaces the delivery reads — the dataset-metadata tool and the document-metadata resource — and
the two SHALL share one set of lookups per turn rather than ask the servers twice:

- **The catalogue** is fetched by the first check of a draft that cites a dataset, directly or
  through a cited query with an explorer link and a dataset URN, and a successful answer serves
  every later check and the delivery.
- **Document metadata** is read, per check, for the cited document ids not yet looked up, in one
  resource read per check. An id's answer, including its absence from the answer, serves every
  later check and the delivery; the delivery reads only ids no check has looked up.

**What "known" means.** Known means available on the server — never "seen in an earlier tool
response", for the reason the identifier checks in **report-composition** give. A dataset URN is
known when the catalogue, the list of datasets the server makes available, carries a record whose
`id` equals it, character for character. A document id is known when the document-metadata
resource's answer carries it. For the second to hold, the resource SHALL omit from its answer **exactly** the ids its
channel does not know: an id it knows SHALL be present, even when its metadata object is empty. This
tightens the partial-answer allowance in the document-metadata requirement, which permits an
unknown id's absence without saying that absence means unknown.

**A failed lookup decides nothing.** When the catalogue call or a resource read fails, or its answer
cannot be read, the ids it was asked about SHALL be treated as not looked up: no check reports them
as unknown, and the next check or the delivery asks again. A check that cannot tell whether an id
is valid SHALL stay silent about it, because a false violation makes the writer remove a citation
the report needs.

Page indices are **not** checked: whether a cited page exists in a document is deferred.

#### Scenario: A document looked up during review is not read again at delivery

- **WHEN** a reviewed draft cites documents `207` and `442`, the check reads both, and the delivered
  report cites the same two
- **THEN** the delivery SHALL read no document metadata, and SHALL use the answer the check read for
  the pills' titles and the References rows

#### Scenario: An id the resource omits is unknown

- **WHEN** a reviewed draft cites document `999` and the resource's answer for `207,999` carries
  `207` only
- **THEN** document `999` SHALL be treated as unknown, and document `207` as known

#### Scenario: A failed catalogue call flags nothing

- **WHEN** a reviewed draft cites `[dataset IMF:WEO(1.0.0)]` and the dataset-metadata call fails
- **THEN** the review SHALL report no dataset as unknown, and the delivery SHALL call the tool again

## MODIFIED Requirements

### Requirement: A converted citation is a marker tag in the text and an annotation that names it

Conversion produces two halves that find each other by a shared id.

**In the report text**, one empty citation marker tag, `<cit data-id="…"></cit>`, stands where the
citation's marker stood. An id SHALL be opaque and SHALL appear on exactly one tag in the message:
one tag per converted position, whether that position held a single citation or a run of adjacent
ones. Two citations of the same document and page in **different** positions therefore carry
different ids and render as two pills. The tag SHALL be emitted empty — it anchors a pill at its own
position and does not enclose the cited sentence.

**In `custom_content.annotations`**, one entry per converted citation — so a run of three sources
behind one tag contributes three entries that share that tag's id — carrying the fields below. The
References section adds one entry per row it makes openable, after these; that entry's labels and
page are owned by the References requirement, and every other field is the one below. Each entry
carries:

- **`index`** — the entry's 0-based position in the array, unique across it. The array is an indexed
  list: the DIAL SDK treats a list whose elements carry an `index` as a streaming delta and merges
  by it, and the client uses it both to merge those deltas and to identify the region it scrolls to.
  Uniqueness is load-bearing for a run: the client treats two annotations that share a tag id and
  carry no `index` as one annotation. A caller that asks for a non-streamed response is served by
  the SDK's block path, which strips `index` from every list element of the assembled message, so a
  run's sources may reach such a caller merged into one entry. The field SHALL be emitted regardless
  — the streaming readers this feature is written for keep it — and nothing in the app may depend on
  it surviving to a non-streaming caller.
- **`target.selector`** — type `html_tag`, naming the tag (`cit`) and, in its `id` field, the value
  of that tag's `data-id` attribute. The two SHALL match exactly; an annotation naming a value no tag
  carries renders nothing, and a tag no annotation names is shown to the reader as text. The
  selector's field is `id` while the tag's attribute is `data-id` — an asymmetry of the client's
  contract, not a choice open to this app.
- **`body.title`** — the label of this citation's entry inside the pill's popup. It SHALL read
  **`<title>, page <ix>`**, naming the cited document's publication title and the cited page, when a
  title resolved for that document through the document-metadata resource; and **`doc <id>, page
  <ix>`**, the text the marker carried, when none did. In a run's popup these labels are what tells
  the sources apart, and the page belongs in the label because a document server attributes at page
  level: two pages of one publication are two sources and must read as two entries. A **dataset**
  citation's label SHALL read **`<name> dataset`** when the dataset-metadata tool reported a usable
  name, and **`<urn> dataset`** — the URN the marker carried — when it did not. When the tool
  reported a last-update date for the dataset, the card's label SHALL go on to
  **` - last update <date>`**, as in `World Economic Outlook dataset - last update 2025-04-30`;
  without a date it SHALL end at ` dataset`. The date is the one fact about a dataset's currency the
  reader needs to judge it, and the title is where the card shows it.

  The trailing word is not decoration: a dataset's name is often a bare noun phrase such as
  `World Economic Outlook`, which says nothing about what kind of source it is, and a URN alone says less
  still. It is present in **both** cases on purpose, so that a pill and a card read the same way
  whether or not a name resolved — the two differ in what fills the leading slot and in nothing else.
  A reader meeting one of each in the same report should not be able to tell that one of them fell
  back.

  The label SHALL carry **no URL**; the address the citation opens lives in
  `body.source.attachment.url`, which is the field the client follows, and showing it again would
  spend the card's most prominent line on a string the reader does not have to read. A dataset cited
  twice in one run is one source cited once, a dataset server attributing to the dataset rather than
  to a location inside it.
- **`body.source.attachment`** — `{type, url, title}`, nested under `source`: the URL this citation
  opens, carried verbatim, and the label the pill itself shows.

  **The type SHALL be stated explicitly and SHALL say what is cited**: `application/pdf` for a
  document citation, whose URL is the DIAL file URL the file-sharing tool returned, and `text/html`
  for a dataset citation, whose URL is the page the dataset-metadata tool returned. The type is
  load-bearing rather than decorative, because the client branches on it twice: it opens a citation
  into its document viewer only for `application/pdf`, and it offers the reader an open-in-browser
  action — the one action that reaches a page on the web — only for an HTML type. A dataset citation
  labelled `application/pdf` would therefore offer a download of a page that is not a file.

  **This field is the only place a dataset's address exists in the payload, and the only way a reader
  reaches it.** The reader's path is two clicks and both belong to the client: clicking the pill
  opens the citation card, and the card's open-in-browser action opens `url` in a new browser tab.
  The pill's own click does **not** follow the URL — it opens the card — and the app cannot change
  that, because what a pill does on click is the client's behaviour and no field of the annotation
  selects it. Where a run of citations shares one pill, that action applies to whichever source the
  card's switcher is showing, so a dataset cited beside a document is reached by stepping to its
  entry first.

  The app SHALL carry the URL into this field exactly as the dataset-metadata tool reported it,
  decoding nothing and re-encoding nothing, for the reason the file-sharing URL is carried verbatim:
  the client resolves it, and any rewriting risks an address that no longer names the page.

  **This label is what the pill itself shows, and it is not `body.title`.** For a **document**
  citation it carries the same two parts as `body.title` — the publication title and the cited page —
  differing only in that **the title is shortened to a configured budget**, the ellipsis counted
  within it, or carried whole where the channel names no budget (**application-config-schema** owns
  the field, its default and its null case); the cited page SHALL be appended **after** the
  shortening, so a long title never costs the reader the page. For a **dataset** citation it carries the
  same two parts its `body.title` carries — the name, or the URN when no name resolved, followed by
  `dataset` — with **`dataset` appended after the shortening**, exactly as a document's cited page is
  appended after its title's. So the pill reads **`<shortened name> dataset`** or
  **`<shortened urn> dataset`**, and never loses the word that says what the leading string names.

  Appending after the shortening is what makes the two cases the same shape. A URN has no bounded
  length — `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` is forty characters against a budget of
  twenty — so a fallback label must be shortened or it overflows, and shortening it without
  re-appending the word would leave a truncated string with nothing saying what it is. Applying the
  same rule to the resolved case costs one word of width and buys a pill whose structure does not
  betray whether the lookup succeeded.

  A **document** citation that resolved no title is the one label that is not shortened at all: its
  `doc <id>, page <ix>` is short by construction, and cutting it would lose the id or the page.

  No label SHALL carry a URL. A dataset's address reaches the reader only as the link the pill
  follows.

  The app shortens, where a channel sets a budget, because the client does not: a pill is a narrow
  inline element carrying the client's own count marker when it stands for a run, and a label that
  overflows is not trimmed for it. A channel that sets no budget gets every label whole, which is
  the default. The popup card has the room, which is why `body.title` keeps the title whole — a reader who
  needs the full name opens the pill. The app SHALL derive no label from the URL and SHALL decode no
  part of one: the file name inside a shared URL is a storage path segment rather than a title, the
  trailing segment of a portal URL is a slug rather than a name, and the contracted metadata surfaces
  are the only source of a real one. No URL SHALL appear in any label, in whole or in part, on either
  the pill or the card. A pill behind a run takes its
  label from the run's first citation and marks how many further sources it carries, which the
  client does on its own. A flat source without the nested attachment is not a valid entry in this
  container and is discarded by the client before rendering.
- **`body.selector`** — for a **document** citation, a `pdf_bbox` carrying the cited page, with a
  zero-size box
  (`x1 = y1 = x2 = y2 = 0`). The page is carried here and nowhere else: the tag in the text carries
  no page, and the page SHALL NOT be appended to the URL as a `#page=N` fragment, which the client's
  citation preview does not strip and which therefore breaks opening the file. For a **dataset**
  citation the field SHALL be **omitted** entirely: a dataset citation names no location inside what
  it cites, and a page selector on a source that is not a PDF would name a page of a file that does
  not exist.

**A citation's labels have the same shape whether or not its metadata resolved.** This holds for
documents and datasets alike, and it is a requirement rather than a consequence.

Every label is a **leading part** naming the source, followed by a **fixed trailing part** saying
what kind of source it is and, for a document, which page of it:

| Citation | Resolved | Not resolved |
|---|---|---|
| document | `<title>, page <ix>` | `doc <id>, page <ix>` |
| dataset | `<name> dataset` | `<urn> dataset` |

A dataset's **card** label adds ` - last update <date>` after the trailing part when a date was
reported, and nothing when none was. The pill never carries the date: it is the narrowest label,
and the date is not what tells two sources apart.

What a failed lookup changes is **only what fills the leading slot** — the server's name for the
source, or the identifier the report's marker carried. It SHALL NOT change the shape, SHALL NOT drop
the trailing part, and SHALL NOT mark the citation as degraded in any way a reader can see: no
"unknown", no "untitled", no bracket, no icon. A reader meeting a resolved and an unresolved citation
in the same report SHALL NOT be able to tell which is which from the label's structure. Whether the
app reached a metadata surface is the app's problem, and a reader who is shown it learns nothing they
can act on while being invited to trust one citation less than another that is equally real.

The trailing part is **appended after any shortening**, so it survives a leading part of any length.
The one label that is not shortened at all is an **unresolved document's**: `doc <id>, page <ix>` is
short by construction, and at the minimum configurable budget shortening it could eat the id. An
unresolved dataset's is shortened, because a URN has no bounded length.

**A document citation SHALL send no `body.quote`**: the app does not have the cited passage's source
text, and an empty quote reserves blank space in the popup.

**A dataset citation SHALL send no `body.quote` either.** Its name is in the title, and so is its
last-update date, the one fact about its currency; the URN is not shown on the card, because a
reader cannot act on it and the dataset's References row names the dataset already. An empty quote
would reserve blank space in the popup, as it would for a document. A missing date SHALL NOT produce
an empty title part, a `null`, or a placeholder such as "unknown": the reader learns nothing from a
title that says the app knows nothing, and an absent date is ordinary rather than a fault.

The date SHALL be carried **exactly as the tool reported it**, with no reformatting, no locale
rendering and no relative phrasing ("3 months ago"), for the reason **source-attribution** gives for
identifiers: the app is not the authority on what the server's value means.

A **data-query** citation is the one kind that sends a `body.quote`, carrying its filter; its fields
are owned by the data-query annotation requirement. The field is Markdown rather than plain text
because the client renders it through its Markdown renderer, unlike `body.title`.

The array SHALL be emitted **once**, after the report text has been appended to the choice, as a
single streamed delta on the same choice while it is still open. Annotations SHALL NOT be emitted
through the attachment API, which assigns its own indices and would renumber them.

Emitting after the content costs no pill. The client hides a supported marker tag while the message
is still streaming and resolves no annotations until the message completes, so every pill appears
when the message finishes rather than as the report streams.

#### Scenario: A converted citation's two halves agree

- **WHEN** the step converts a lone citation of document 442, page 3
- **THEN** the delivered text SHALL carry `<cit data-id="X"></cit>` where the marker stood, and the
  annotations array SHALL carry exactly one entry whose `target.selector` names tag `cit` and id `X`

#### Scenario: A titled document labels both halves with its publication title

- **WHEN** the step converts a citation of document 12, page 13, and the document-metadata resource
  reported that document's title as `Market Outlook 2025`
- **THEN** the annotation's `body.title` and its `body.source.attachment.title` SHALL both read
  `Market Outlook 2025, page 13`, and no part of the shared URL SHALL appear in
  either

#### Scenario: An untitled document falls back to the marker's own text

- **WHEN** the step converts a citation of document 12, page 13, and no title resolved for that
  document
- **THEN** both labels SHALL read `doc 12, page 13`, and the citation SHALL still become a pill

#### Scenario: A titled and an untitled document produce the same label shape

- **WHEN** one report converts a document citation whose title resolved and another whose title did
  not
- **THEN** both labels SHALL end `, page <ix>` and both SHALL differ only in whether the leading part
  is the publication title or `doc <id>`, and neither SHALL carry any marker of having fallen back

#### Scenario: A long title is shortened on the pill and whole on the card

- **WHEN** a resolved publication title is longer than the configured pill budget
- **THEN** `body.source.attachment.title` SHALL carry the title shortened to that budget with an
  ellipsis, followed by the cited page, and `body.title` SHALL carry the whole title with the page

#### Scenario: A title within the budget is untouched

- **WHEN** a resolved title is no longer than the configured budget
- **THEN** both labels SHALL read identically, with no ellipsis

#### Scenario: The pill keeps the page however long the title

- **WHEN** a resolved title is many times the budget
- **THEN** the pill's label SHALL still end with the cited page, because the page is appended after
  the shortening

#### Scenario: Two pages of one publication are two entries

- **WHEN** two adjacent citations name pages 4 and 9 of one titled document and fold into one pill
- **THEN** the pill's popup SHALL carry two entries, their labels differing only in the page, so the
  reader can tell the two cited pages apart

#### Scenario: A run's annotations share one tag id and keep separate indices

- **WHEN** the step converts a run of two citations behind one tag
- **THEN** both annotations SHALL name that tag's id, and they SHALL carry different `index` values,
  so the client keeps them as two sources behind one pill rather than merging them into one

#### Scenario: The same page cited in two places gets two pills

- **WHEN** the same document and page are cited in two different paragraphs
- **THEN** the two positions SHALL carry different tag ids and SHALL produce two annotations, so the
  reader sees a pill at each position rather than one shared between them

#### Scenario: Indices are sequential and unique

- **WHEN** the step emits seven annotations, however many tags they are spread across
- **THEN** the emitted array SHALL carry indices 0 through 6, each used once, in report order

#### Scenario: The page travels in the selector, not the URL

- **WHEN** two citations name page 3 and page 9 of the same document
- **THEN** both annotations SHALL carry the same attachment URL with no fragment, and SHALL differ
  only in the page their `pdf_bbox` selector names

#### Scenario: Annotations follow the content

- **WHEN** the citation step has annotations to emit
- **THEN** the report text SHALL be appended to the assistant content first and the annotations
  SHALL be emitted after it, on the same open choice

#### Scenario: A dataset citation carries a web source and no page

- **WHEN** the step converts `[dataset IMF:WEO(1.0.0)]`, the dataset-metadata tool reported the
  name `World Economic Outlook`, the URL `https://portal.example.org/datasets/imf-weo` and no
  last-update date
- **THEN** the annotation's `body.source.attachment.type` SHALL be `text/html`, its `url` SHALL be
  that portal URL unchanged, `body.title` SHALL read `World Economic Outlook dataset`,
  `body.source.attachment.title` SHALL read `World Economic Outlook` shortened to the channel's budget
  followed by ` dataset`, `body.quote` SHALL be absent, `body.selector` SHALL be absent, and no label SHALL carry the URL

#### Scenario: An unnamed dataset falls back to the marker's own text

- **WHEN** the step converts a citation of dataset `IMF:WEO(1.0.0)`, a portal URL resolved for
  it and the catalogue reported no usable name
- **THEN** `body.title` SHALL read `IMF:WEO(1.0.0) dataset`,
  `body.source.attachment.title` SHALL read the URN shortened to the channel's budget with `dataset`
  appended after the shortening, and the citation SHALL still become a pill

#### Scenario: A named and an unnamed dataset produce the same label shape

- **WHEN** one report converts a dataset citation whose name resolved and another whose name did not
- **THEN** both pills SHALL read `<leading string, shortened> dataset` and both cards SHALL read
  `<leading string> dataset`, the two differing only in whether the leading string is the name or the
  URN

#### Scenario: The pill and the card say different things about one dataset

- **WHEN** a dataset citation resolves the name `Primary Commodity Prices` and a portal URL, and the
  channel's pill budget is 20 characters
- **THEN** the pill SHALL read that name shortened to 20 characters followed by ` dataset`, the word
  appended after the shortening, and the card SHALL read `Primary Commodity Prices dataset`, the whole
  name with the same trailing word

#### Scenario: A dataset whose last-update date is unknown has no date in its title

- **WHEN** the dataset-metadata tool reports the cited dataset with an id, a name and a URL but no
  last-update date
- **THEN** `body.title` SHALL read `<name> dataset` and end there, with no dash, no empty date and no
  placeholder text, and `body.quote` SHALL be absent

#### Scenario: The last-update date is carried as the tool reported it

- **WHEN** the tool reports the cited dataset `World Economic Outlook` with the last-update date
  `2025-04-30`
- **THEN** `body.title` SHALL read `World Economic Outlook dataset - last update 2025-04-30`, that
  date unchanged, the pill SHALL carry no date, and the app SHALL NOT reformat the date into another
  format or into a relative phrase

### Requirement: The References section is built by the app from the cited sources' metadata

The app SHALL write the report's References section itself as part of the citation step of every
turn that delivers a report, and the report writer SHALL NOT write it. Only a failure earlier in
that step leaves a delivery without the section (see the citation-failure requirement). The section is no part of the
configured report structure: its heading comes from `references_section_name` and its cited-nothing
text from `references_section_empty_text` (**application-config-schema**), and what the writer is
given and checked against is owned by **report-composition**. Every row SHALL be built from what a
server reported about a cited source, never from what a model recalled about it — which is the whole
reason the section moves into the app.

**What the section contains.** The section SHALL open with a `##` heading carrying
`references_section_name`. It SHALL then carry **one table per configured MCP server whose sources the delivered
report cites**, in the order the servers are configured. Each table SHALL open with a `###`
sub-heading carrying that server's configured table title, and its header row SHALL be the columns
that server's `references_table` configures, in the configured order.

A server whose sources the report does not cite SHALL contribute no table at all. Where the report
cites no source of any kind, the section SHALL carry no table and SHALL carry
`references_section_empty_text` instead, so a report with nothing to cite says so rather than
showing a bare heading.

**One row per cited source.** Each table SHALL carry one row for each distinct source of its kind the
delivered report cites, ordered by where that source is first cited in the report. A source SHALL be
listed **whether or not its metadata resolved, and whether or not its citations became pills**. The
row is what tells a reader which source a citation names, so a source that lost its pill is the one
whose reader needs the row most.

Two citations of one document on different pages are one source and therefore one row: a References
row names the source, never the cited location.

**How a cell is filled.** Each cell SHALL carry the value the row's source reported under that
column's configured key — for a document, that key in the document's metadata object; for a dataset,
that field of the dataset's catalogue record. A value SHALL be rendered by these rules, so what the
channel stores decides the cell rather than the app's ability to interpret it:

- a string carrying something other than whitespace, as written but stripped of the whitespace
  around it;
- a number or a boolean, as its text;
- a list, as its items joined with `, `, each item rendered by these same rules;
- anything else, and any absent, empty or whitespace-only value, as an empty cell.

A rendered value SHALL be escaped so that it cannot break the table it sits in: a `|` SHALL be
escaped, and a line break SHALL become a space.

**The first column names the source, and it is the column that degrades.** Where the first column's
key resolves nothing — including a value that is present but carries only whitespace, which is
nothing a reader can identify a source by — that cell SHALL carry the source's identifier instead — `doc <id>` for a
document, the URN as the marker carried it for a dataset — which is the fallback a citation pill's
label already uses. Every other column SHALL be left empty when its key resolves nothing. Nothing in
a row SHALL mark it as degraded, for the reason no pill label does: which lookup failed is the
application's problem, and a reader shown it is only invited to trust one real source less than
another.

**A row whose source can be opened carries a pill in its first cell.** A row SHALL be openable on
exactly the condition an inline citation of its source is converted: a document row when the
file-sharing tool returned a PDF URL for that document, and a dataset row when the dataset-metadata
tool reported a URL a browser can open for that dataset. The first cell of an openable row SHALL
carry one empty marker tag, `<cit data-id="…"></cit>`, **in place of** the text it would otherwise
carry, and one annotation of its own SHALL claim that tag, so the client renders the source's name as
a pill inside the cell. The tag's id SHALL be unique across the message, like every other tag's, and
exactly one annotation SHALL claim it. Every other cell of the row SHALL be filled as for any row. A
row whose source is not openable SHALL keep its first cell as text, with no tag, and no annotation
SHALL be emitted for it.

A row is opened through an annotation rather than a link because a document's shared URL is
storage-relative, so an ordinary Markdown link to it opens nothing. The annotation is the one
mechanism that opens both kinds of source, and a row reusing it opens exactly what an inline pill of
the same source opens.

**A row's annotation is an inline citation's annotation with its own labels and page.** It SHALL
carry the attachment type and the URL that a converted citation of the same source carries (the
requirement "A converted citation is a marker tag in the text and an annotation that names it"),
and, like that citation, no `body.quote`. It SHALL differ from it in two things:

- **The label is the row's name alone.** `body.title` SHALL carry the text the first cell would have
  carried: the value under the first column's key, rendered by the cell rules above, or the source's
  identifier where that key resolves nothing. The `|` escape SHALL NOT be applied, because the label
  is not table text and a reader would see the backslash; a line break still becomes a space. The
  label SHALL carry **no trailing part** — no `, page <ix>`, no ` dataset` and no
  ` - last update <date>` — because the row already sits under a sub-heading naming its kind of
  source, a References row names the source, never the cited location, and a row's other cells
  carry whatever else the channel configured, a last-update column among them. A dataset row's
  pill and card therefore both read the dataset's title alone, such as `World Economic Outlook`. `body.source.attachment.title` SHALL carry the same text,
  shortened to the channel's pill budget exactly as an inline pill's leading part is, or whole where
  the channel names no budget (**application-config-schema** owns the field). A document row labelled
  `doc <id>` SHALL NOT be shortened, for the reason an unresolved inline document label is not: it is
  short by construction, and a cut could eat the id.
- **A document row opens its document at page 1.** Its `pdf_bbox` selector SHALL carry page 1,
  whichever pages the report cites. A row names the whole document rather than a location in it, so
  it opens where the document begins; the selector is still sent, because the document viewer needs
  a page to open at. A dataset row carries no selector, like a dataset citation.

**Row annotations share the array with the inline ones.** They SHALL be emitted in the same
`custom_content.annotations` array as the conversion's annotations, **after** all of them, in the
order the rows are written, with `index` values continuing the array's sequence. The array is still
emitted once, after the content.

A marker tag is not a hyperlink, so an openable row does not breach the no-hyperlink guarantee
(**report-composition**): no cell SHALL carry a Markdown link, an HTML anchor, a URL, or any markup
other than the marker tag. The no-hyperlink rule governs what the report writer writes, and the app
writes no link of its own, so the rule needs no exemption for an app-written section.

**Where it is appended.** The built section SHALL be appended to the text the citation conversion
produced — after the link-removal pass and after the conversion — and SHALL therefore reach both the
assistant message content and the persisted report message. It SHALL NOT be searched for citation
markers or for hyperlinks: the app wrote it, and it carries neither — its only markup is the marker
tags of its openable rows, which the build writes together with their annotations.

**A section the draft wrote anyway is left where it is.** The app SHALL NOT remove text from a
draft to make room for the built section. A draft that writes its own references section carries an
extra `##` heading, which the structure check reports on every reviewed draft and the revision acts
on (**report-composition**), so the loop is what removes it while a version remains; its words count
toward the ceiling like any other, because a violation must not earn length budget. A draft that
exhausts the version budget still carrying one SHALL be delivered with that section followed by the
built one.

The duplication is deliberate, and it is the cheaper failure: removing a heading and the text after
it removes whatever the writer put below that heading, which a reader cannot see has happened,
while two References sections are visible and cost a reader nothing. It also keeps the rows true —
the cited ids are read before the section is appended and nothing is removed after, so every source
a row lists is one the delivered report cites.

#### Scenario: Every cited source gets a row

- **WHEN** a delivered report cites three documents and two datasets, and the file-sharing tool
  resolved URLs for two of the three documents
- **THEN** the built section SHALL carry a documents table of three rows and a datasets table of two
  rows, each row ordered by where its source is first cited

#### Scenario: A source whose metadata did not resolve keeps its row

- **WHEN** the metadata answer omits one cited document, and the catalogue omits one cited dataset
- **THEN** each SHALL still have a row, the document's named `doc <id>` and the dataset's named by
  the URN the marker carried, its other cells empty, and nothing in either row SHALL mark it as
  incomplete. The name SHALL be the first cell's text where the row is not openable, and its pill's
  label where it is

#### Scenario: A server with nothing cited contributes no table

- **WHEN** a channel configures a document server and a dataset server, and the delivered report
  cites documents only
- **THEN** the section SHALL carry the documents table alone, and no datasets sub-heading and no
  empty datasets table SHALL appear

#### Scenario: A report citing nothing carries the configured text

- **WHEN** a delivered report cites no document and no dataset
- **THEN** the section SHALL be present, SHALL carry no table, and SHALL carry
  `references_section_empty_text`

#### Scenario: A draft that wrote the section anyway keeps every section it wrote

- **WHEN** a draft that exhausted its version budget carries a `## References` heading with rows the
  model wrote, followed by a `## Conclusion` section
- **THEN** the delivered text SHALL still carry that Conclusion, the model's references heading and
  rows SHALL still be there, and the built section SHALL follow them

#### Scenario: A source cited only inside the draft's own references section still gets a row

- **WHEN** a draft cites one document in its body and a second document only inside the references
  section it wrote itself
- **THEN** both documents SHALL have a row, both citations SHALL be converted where their
  conditions hold, and no row SHALL name a source the delivered text does not cite

#### Scenario: A value that only looks filled leaves its cell empty

- **WHEN** a cited document that resolved no URL has a first-column key holding a string of spaces,
  and its other column holds a value padded with spaces
- **THEN** the first cell SHALL carry the source's identifier rather than the spaces, and the other
  cell SHALL carry its value with the padding gone

#### Scenario: A value that would break the table is escaped

- **WHEN** a cited document that resolved no URL has a title containing a `|` and a publication date
  field holding a value spanning two lines
- **THEN** the `|` SHALL be escaped and the line break SHALL be rendered as a space, so the table
  keeps its columns

#### Scenario: A document row with a PDF URL opens at page 1

- **WHEN** a delivered report cites document 12 first at page 13 and later at page 4, the
  file-sharing tool returned a PDF URL for it, and the documents table's first column reads the
  title `Market Outlook 2025`
- **THEN** that row's first cell SHALL carry one marker tag and no other text, and exactly one
  annotation SHALL claim the tag, with type `application/pdf`, that URL, a `pdf_bbox` selector on
  page 1, no `body.quote`, and both `body.title` and `body.source.attachment.title` reading
  `Market Outlook 2025` with no page

#### Scenario: A dataset row with a portal URL opens its page

- **WHEN** a delivered report cites `IMF:WEO(1.0.0)`, and the dataset-metadata tool reported the name
  `World Economic Outlook` and the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** that row's first cell SHALL carry one marker tag, and its annotation SHALL carry type
  `text/html`, that URL unchanged, no `body.quote`, no selector, and both labels reading
  `World Economic Outlook` with no ` dataset` and no last-update part, even when the catalogue
  reported a last-update date

#### Scenario: A row whose source cannot be opened stays text

- **WHEN** a delivered report cites a document the file-sharing tool returned no URL for, and a
  dataset whose catalogue record carries no URL
- **THEN** both rows SHALL carry their first cell as text, neither SHALL carry a marker tag, and no
  annotation SHALL be emitted for either row

#### Scenario: A row named by its identifier is labelled with it

- **WHEN** a cited document resolved a PDF URL and no metadata, and the channel sets a pill budget
  of 10
- **THEN** its row's pill and card SHALL both read `doc <id>`, unshortened

#### Scenario: The pill budget shortens a row's pill and not its card

- **WHEN** the channel sets a pill budget and an openable row's name is longer than it
- **THEN** `body.source.attachment.title` SHALL carry the name shortened to that budget with an
  ellipsis, and `body.title` SHALL carry it whole

#### Scenario: A row's label is not escaped for the table

- **WHEN** an openable document row's title contains a `|` and a line break
- **THEN** both labels SHALL carry the `|` without a backslash and the line break as a space, and the
  cell SHALL carry the marker tag alone, so the table keeps its columns

#### Scenario: Row annotations follow the inline ones

- **WHEN** the conversion emitted five annotations, and the section makes two rows openable
- **THEN** the array SHALL carry the two row annotations at indices 5 and 6, in the order their rows
  are written, and each row's tag id SHALL differ from every inline tag id

#### Scenario: The built section carries no hyperlink

- **WHEN** the section is built for a report citing a document whose URL resolved and a dataset whose
  catalogue record carries an absolute portal URL
- **THEN** neither row SHALL carry a Markdown link, an HTML anchor, a URL, or any markup other than
  its marker tag, and the delivered text SHALL still satisfy the no-hyperlink guarantee

### Requirement: A dataset citation is converted when its dataset resolves a web URL

A `[dataset <id>]` marker SHALL be converted — its marker replaced by a marker tag, one annotation
emitted for it — on one condition: **the cited dataset resolved a URL that a browser can open.**

**A dataset's identifier is called its URN throughout this capability**, and the marker's `<id>`
slot carries it: the report's citation form is `[dataset <id>]`, owned by **research-execution**, but
what fills it for every supported dataset server is a URN such as `IMF:WEO(1.0.0)`. The wire
field the dataset-metadata tool reports it under is `id`, which is the server's key and is not
renamed here; every user-visible mention of it — the fallback labels — reads
`URN`, because that is what the value is and what the dataset server's own documentation calls it.

The dataset-metadata tool must have reported a record for that URN carrying a URL, and that
URL must be **absolute and `http` or `https`**. The app SHALL decide this from the URL itself,
treating any other form — a storage-relative `files/…` path, a scheme it does not recognise, a value
that is not a URL at all — as not convertible. The direction is conservative for the same reason the
PDF check on a document is: a dataset pill exists to take the reader to a page, and a pill that
opens nothing is worse than a marker that at least names its source. A storage-relative URL in
particular would make the client offer a file download rather than a page.

The URN is matched **verbatim**, as **source-attribution** requires: the string the marker carries is
compared to the `id` of each record the tool reported, with no case change, no trimming, no
re-encoding and no version-stripping. A URN carries punctuation — a colon, and often a parenthesised
version — and every character of it is part of the URN.

A dataset citation whose URN the tool did not report, or reported without a usable URL, SHALL keep
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

#### Scenario: A cited dataset with a portal URL becomes a pill

- **WHEN** a paragraph reads `…rose by 2.1% [dataset IMF:WEO(1.0.0)] over the period.` and the
  dataset-metadata tool reported that id with the URL `https://portal.example.org/datasets/imf-weo`
- **THEN** the marker SHALL be replaced by a marker tag, and one annotation SHALL be emitted naming
  that tag and carrying the portal URL

#### Scenario: A reader reaches the dataset's page from the card

- **WHEN** a reader clicks a converted dataset citation's pill and then its open-in-browser action
- **THEN** the page at `body.source.attachment.url` SHALL open in a new browser tab, and that URL
  SHALL be the string the dataset-metadata tool reported, unchanged

#### Scenario: A dataset the catalogue does not report keeps its text

- **WHEN** the report cites `[dataset IMF:UNKNOWN(1.0.0)]` and the tool's answer carries no record
  with that id
- **THEN** the marker SHALL remain in the delivered text, and no annotation SHALL be emitted for it

#### Scenario: A dataset reported without a URL keeps its text

- **WHEN** the tool reports the cited dataset's record with a name but no URL
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

### Requirement: Cited datasets are named and linked through a contracted dataset-metadata tool

A dataset citation needs three things the app does not hold: the dataset's human name, which labels
the pill and the card and leads its References row; the address of its page, which no label shows and
which the reader reaches through the card's open-in-browser action; and its last-update date, which
the card's title carries when the server knows one. All come from **one MCP tool**, the
**dataset-metadata tool**, and the app SHALL depend on nothing about it beyond the contract stated
here. Which server provides it, what that server names it, and where it keeps the catalogue are all
outside the contract, and the app SHALL behave identically for any server that satisfies it.

**The name comes from configuration.** Each MCP server entry in the application properties SHALL be
able to name that server's dataset-metadata tool, and the app SHALL call exactly the tool that entry
names (**application-config-schema** owns the field). There SHALL be no default name and no
discovery by convention: the app SHALL NOT infer the tool from a server's advertised tool list, from
a tool's description, or from any naming pattern. Only a **dataset** server may name one, and at
most one dataset server may be configured, so at most one configured server names a dataset-metadata
tool — which is what makes asking that server about an id correct, since a `[dataset <id>]` marker
names no server.

A dataset server **must** name one, exactly as a document server must name its file-sharing
tool, and for the same reason: the tool is the only thing that turns a cited URN into a name and a
page the reader can open, so a dataset server without it serves datasets that cannot be cited. The
rule lives in **application-config-schema**, which also records what it costs — a channel whose
dataset server advertises no catalogue tool cannot be configured.

A channel that configures **no dataset server at all** remains ordinary: nothing names a
dataset-metadata tool, no call is made, and a dataset marker in a delivered report keeps its text.
That is the case recorded at DEBUG rather than warned about on every turn (see **logging-policy**).

**The contract.** A tool named as a server's dataset-metadata tool SHALL satisfy all of the
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
  absence costs. An element whose **`url`** is absent is a dataset that cannot be cited as a pill at
  all, because the pill would open nothing; it is still a cited dataset and still gets a References
  row. An element whose **`lastUpdated`** is absent is cited normally and simply carries one fewer
  fact on its card. Neither absence is a malformed answer.

  `lastUpdated` SHALL be a date the reader can act on, written as an **ISO 8601 date** such as
  `2025-04-30`. A server that cannot produce one SHALL omit the field rather than send free text it
  failed to parse, because the app displays this value verbatim and cannot tell a date it does not
  understand from one it does. A value that reaches the app as anything but a non-empty string SHALL
  be read as absent.
- **Structured result**: the tool SHALL return that object as its MCP **structured result**, which
  means declaring the output schema MCP requires for one. The app reads the structured result and
  nothing else — a tool that answers with text content alone SHALL be treated as a failed call. MCP
  carries the same object a second time as serialized text, which the app ignores.
- **Complete for the channel**: the answer SHALL carry every dataset the channel exposes, because
  the app cannot ask about a subset. A dataset absent from the answer is uncitable.
- **Idempotent and read-only**: the app calls the tool once per turn, and repeated calls across
  turns SHALL be safe and SHALL change nothing on the server.

The app SHALL call the tool **once per turn** when it succeeds, and only on a turn where a reviewed
draft or the delivered report cites at least one dataset. The first draft the report review checks
that cites a dataset makes the call; every later draft's check and the delivery reuse that answer
(see the requirement on looking cited identifiers up once per turn). A failed call is not reused,
so the next check or the delivery calls again. It SHALL NOT call the tool once per cited dataset,
and SHALL NOT call it for a dataset that research touched but no draft cites.

The app SHALL select from the answer **every** record whose `id` equals a cited id, and SHALL ignore
every other record. Selection SHALL NOT depend on what a record carries: a record with no usable page
URL is selected like any other, because the pill is not the only thing that reads it. What a missing
URL costs is decided where the pill is decided, not here. That the answer is the whole catalogue is a
property of the contract rather than a cost the report pays per citation: one call carries however
many datasets the report cites.

#### Scenario: One call serves every cited dataset

- **WHEN** three reviewed drafts and the delivered report cite four datasets, and research queried
  three more that no draft cites
- **THEN** the app SHALL call the dataset-metadata tool exactly once, with no arguments, during the
  review of the first draft, and SHALL read the four cited ids out of that one answer

#### Scenario: A report citing no dataset makes no call

- **WHEN** every reviewed draft and the delivered report cite documents only
- **THEN** the app SHALL NOT call the dataset-metadata tool

#### Scenario: A record with no page URL is still selected

- **WHEN** a cited dataset's record carries an `id` and a `name` and no `url`
- **THEN** that record SHALL be selected, its citations SHALL keep their marker text for want of a
  page to open, and its References row SHALL carry its name

#### Scenario: Extra fields in a record are available to a row

- **WHEN** a reported record carries a description and a provider beside its `id`, `name`, `url` and
  `lastUpdated`, and the channel configures a column reading the provider
- **THEN** the record SHALL be accepted, the pill SHALL be built from the `name` and the `url`
  alone, and the References row SHALL carry the provider in its configured column

#### Scenario: A text-only answer is a failed call

- **WHEN** the named tool returns its catalogue as text content with no structured result
- **THEN** the call SHALL be treated as failed, every dataset citation SHALL keep its marker text,
  and the report SHALL be delivered
