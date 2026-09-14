## MODIFIED Requirements

### Requirement: A dataset server attributes a fact to at least a dataset

Semantic requirement.

A dataset server SHALL attribute every fact it reports to at least the dataset the fact was drawn
from, identified as that server reports it. Attribution to an individual series within a dataset is
**deferred**: a server MAY report it, and the app ignores it today.

This requirement is load-bearing twice over. It bounds what the report may claim about a
dataset-sourced fact, and it is also what a reader clicks: a dataset citation is converted into a
pill whose link opens that dataset's page (see **report-citations**), and the identifier in the
attribution is what the app sends back to the server to find that page. An attribution that names
the wrong dataset therefore produces a pill that opens the wrong dataset, not merely a sentence that
credits the wrong source.

#### Scenario: A dataset-sourced fact names its dataset

- **WHEN** a dataset server reports a fact drawn from a dataset
- **THEN** the attribution SHALL carry that dataset's identifier, and the report SHALL cite the fact
  with that identifier rather than with a document-and-page citation

#### Scenario: The identifier a fact is attributed to is the one a pill resolves

- **WHEN** a dataset server attributes a fact to the dataset it reports as `IMF:WEO(1.0.0)`
- **THEN** the report SHALL cite that fact as `[dataset IMF:WEO(1.0.0)]`, and the pill that
  marker becomes SHALL open the page the same server reports for that same identifier

### Requirement: A cited identifier resolves against its server verbatim

Syntactic requirement.

The identifier a citation marker carries SHALL be the identifier that server's resolution surfaces
accept, unchanged. Between reading an identifier out of the delivered report and resolving it, the
app SHALL NOT change its case, trim it, re-encode it, renumber it, or transform it in any other way.

**Resolving** covers both forms the resolution takes. An identifier sent back to the server as a
tool argument — a document id passed to the file-sharing tool, or into a metadata resource URI — goes
out exactly as the marker wrote it. An identifier **matched locally** against what the server
already answered — a dataset id compared to the `id` of each record the dataset-metadata tool
reported — is compared exactly as the marker wrote it, against the record's own value likewise
untransformed. The rule is the same rule because the risk is the same: a comparison that
case-folds, trims or strips a version can match the wrong record as easily as a rewritten argument
can fetch the wrong file.

A document identifier is a positive integer, and it is the same integer for every surface of one
server: the attribution that reported it, the file-sharing tool, and the document-metadata resource.
A dataset identifier is an opaque string that may carry punctuation, such as the colon in
`IMF:WEO`.

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

- **WHEN** the delivered report cites `[dataset IMF:WEO(1.0.0)]` and the dataset-metadata tool's
  answer carries records with the ids `IMF:WEO(1.0.0)` and `imf:weo`
- **THEN** the app SHALL select the record whose id is `IMF:WEO(1.0.0)`, comparing the strings
  character for character, and SHALL NOT treat the case-folded id as a match
