## MODIFIED Requirements

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
  report reviewer SHALL be given the report-composition rule "Glossary terms" as a check only if
  the research agent obtained a successful glossary tool result

#### Scenario: A failed list of datasets still reaches the prompts

- **WHEN** all three list-datasets attempts failed
- **THEN** every call that receives the data-sources string SHALL receive it with a datasets
  section carrying `failed to obtain list of datasets`
