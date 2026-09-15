## ADDED Requirements

### Requirement: A References section that could not be built is one WARNING

The citation step builds the report's References section from the metadata it has already resolved
(see **report-citations**). A failure of that build SHALL be recorded as **one WARNING** owned by
the citation step, naming the failure kind, beside the (8c) event, which fires either way.

It is a WARNING rather than an ERROR because it costs the section and nothing else: the report is
delivered, every pill the conversion earned is delivered with it, and no citation is lost. It is a
WARNING rather than a DEBUG because, unlike an absent file-sharing tool or an absent
dataset-metadata tool, it is never a configuration a deployment chose — the build reads data the
step already holds, so a failure in it is a fault in this application.

The record SHALL carry the failure kind and nothing drawn from a source: a row's cell values are
server-reported content, and a document title, a dataset's name, a cited id and a URL are each
already outside the content allowlist at every level. How many sources the section would have listed
is already readable from the requested-document and requested-dataset counts on the (8c) event, so
the warning adds no count of its own.

**A structure that declares no references section SHALL NOT be recorded at all**, at any level. No
build is attempted, nothing failed, and a channel whose report structure omits the section would
otherwise emit a record on every report it delivers.

#### Scenario: A failed build warns once and delivers the report

- **WHEN** the citation conversion has finished and building the References section raises
- **THEN** exactly one WARNING SHALL name the failure kind, the (8c) event SHALL fire with its
  counts unchanged, the report SHALL be delivered with its pills and without the section, and the
  turn SHALL complete successfully

#### Scenario: The warning names no source

- **WHEN** a References build fails for a report citing three documents and two datasets
- **THEN** the WARNING SHALL carry the failure kind and SHALL NOT carry a document title, a dataset
  name, a cited id, a URL, or any cell value

#### Scenario: A structure with no references section is silent

- **WHEN** an instance whose configured structure sets `references_section` on no section delivers a
  report citing two documents
- **THEN** no record about the References section SHALL be emitted at any level
