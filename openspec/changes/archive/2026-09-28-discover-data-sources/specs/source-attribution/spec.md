## MODIFIED Requirements

### Requirement: A cited identifier resolves against its server verbatim

Syntactic requirement.

The identifier a citation marker carries SHALL be the identifier that server's resolution surfaces
accept, unchanged. Between reading an identifier out of the delivered report and resolving it, the
app SHALL NOT change its case, trim it, re-encode it, renumber it, or transform it in any other way.

**Resolving** covers both forms the resolution takes. An identifier sent back to the server as a
tool argument — a document id passed to the file-sharing tool, or into a metadata resource URI — goes
out exactly as the marker wrote it. An identifier **matched locally** against what the server
already answered is compared exactly as the marker wrote it, against the server's own value
likewise untransformed. Two identifiers are matched locally: a dataset id compared to the `id` of
each record the list-datasets tool reported, and a query id compared to the query id of each
data-query record the server's tool results carried during the turn. The rule is the same rule
because the risk is the same: a comparison that case-folds, trims or strips a version can match the
wrong record as easily as a rewritten argument can fetch the wrong file.

A document identifier is a positive integer, and it is the same integer for every surface of one
server: the attribution that reported it, the file-sharing tool, and the document-metadata resource.
A dataset identifier is an opaque string that may carry punctuation, such as the colon in
`IMF:WEO`. A query identifier is an opaque string as well, and it is the same string in the tool
result the model reads and in the data-query record the app reads.

A citation marker names no server, so nothing in the report says which server an identifier belongs
to. What decides it is the configuration rule that at most one server of each supported type may be
configured (see **application-config-schema**); without that rule, two servers each numbering their
own documents would make an identifier ambiguous and a pill could open the wrong document.

#### Scenario: A document identifier is sent back as written

- **WHEN** the delivered report cites `[doc 207, page 12]`
- **THEN** the app SHALL ask the server about document `207`, the integer the marker carried

#### Scenario: A dataset identifier survives the round trip

- **WHEN** a dataset identifier carries punctuation, such as `IMF:WEO`
- **THEN** whatever the app later sends back to that server SHALL carry the identifier exactly as the
  marker wrote it, with its punctuation and its case intact

#### Scenario: A dataset identifier is matched against the catalogue exactly

- **WHEN** the delivered report cites `[dataset IMF:WEO(1.0.0)]` and the list-datasets tool's
  answer carries records with the ids `IMF:WEO(1.0.0)` and `imf:weo`
- **THEN** the app SHALL select the record whose id is `IMF:WEO(1.0.0)`, comparing the strings
  character for character, and SHALL NOT treat the case-folded id as a match

#### Scenario: A query identifier is matched against the captured records exactly

- **WHEN** the delivered report cites `[data_query DQ_0123ABCD45]` and the turn captured a
  data-query record whose query id is `dq_0123abcd45`
- **THEN** the citation SHALL NOT resolve against that record, and it SHALL keep its marker text
