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
make no data-sources call: the fetch runs only on a turn that goes on to preparation. A
conversation counts as handed off once its research delivered its report; a conversation whose
research failed is not handed off, so a turn that resumes or restarts that research fetches the
data sources as any other turn does (**research-resume**).

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

- **WHEN** a turn arrives on a conversation whose research delivered its report on an earlier turn
- **THEN** the app SHALL make no data-sources call, and the turn SHALL fail as it does today

#### Scenario: A conversation whose research failed fetches the data sources

- **WHEN** a turn arrives on a conversation whose research failed on an earlier turn
- **THEN** the app SHALL run the data-sources fetch before the preparation agent's first model call,
  as on any turn that goes on to preparation
