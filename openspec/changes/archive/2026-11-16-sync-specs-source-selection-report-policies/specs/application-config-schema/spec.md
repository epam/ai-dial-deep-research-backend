## MODIFIED Requirements

### Requirement: Application properties model

The repository SHALL define a pydantic model (`ApplicationProperties`) that is the single
source of per-channel configuration, replacing the YAML-loaded `ChannelConfig`. The model
SHALL expose:

- `max_research_iterations: int` — default `5`, constrained `ge=1`; the cap on
  research-agent → research-review loops before the report is forced.
- `max_research_graph_steps: int` — default `500`, constrained `ge=1`; the per-graph-run step
  ceiling passed to LangGraph as `recursion_limit` (see the **research-execution**
  capability's step-budget requirement for what it counts).
- `default_report_structure: list[ReportSection]` — the ordered sections **the report writer
  writes** when the user asks for no particular format, constrained `min_length=1`. The References
  section is not among them and cannot be: the application builds it and appends it to every
  report (see the **report-citations** capability), and its two strings are the properties below.
  `ReportSection` is a nested model with three fields:
  - `name: str` — required, non-empty (`min_length=1`); the section's heading in the report.
  - `description: str` — required, non-empty (`min_length=1`); everything the writer and the review
    step need to know about that section's content, and the **single home** for that section's
    rules: no other prompt, model, or spec SHALL carry per-section content instructions. The one
    exception is the source-selection rules, which name the default Overview and Additional
    context sections.
  - `protected: bool` — default `False`; whether user instructions may drop or restyle this
    section (see the **report-composition** capability's protected-sections requirement).

  `ReportSection` SHALL reject unknown fields (`extra="forbid"`), so a stored section entry
  carrying the withdrawn `references_section` field fails validation rather than being accepted as
  a section the writer is then asked to write beside the app's own.

  The default value SHALL be the three sections Overview, Key Findings and Additional context,
  each with its description, and Key Findings SHALL default to `protected: true`. What each default
  section holds is summarised in the **report-composition** capability; its rules live in its
  description.

  The list SHALL be constrained to contain at least one section with `protected: true`, so no
  configuration can produce a report whose every section a user instruction may remove.
  Section `name`s SHALL be unique across the list — as MCP `server_name`s already are — since
  duplicate headings make "every configured section is present" and the review step's
  ordered-section check ambiguous.

  **No section may carry the References section's heading.** Validation SHALL reject a structure
  containing a section whose `name` matches `references_section_name`, compared with the
  surrounding whitespace ignored and the letter case folded: the collision is about the heading a
  reader sees, so `references` collides with `References`. The error SHALL name the offending
  section or sections and the property they collide with, since either half is a fix — rename the
  section, or set the property to another heading. The rule exists because the application appends
  its section unconditionally: a section of that name is one the report writer is told to write, by
  the configured structure it must reproduce, and told not to write, by the rule naming the
  appended section.
- `references_section_name: str` — default `References`, non-empty (`min_length=1`); the heading
  the application writes its References section under. A reader sees it, so a channel sets it in
  the language its readers read.
- `references_section_empty_text: str` — default a single sentence saying the report cites no
  source, non-empty (`min_length=1`); what the References section carries when the report cited
  nothing at all. It is the only prose an app-built section holds, and a reader sees it, so a
  channel sets it in the language its readers read.
- `max_report_words: int` — default `2750`, constrained `ge=1`; the report's word ceiling (see
  the **report-composition** capability for how a word is counted and how the ceiling is
  enforced).
- `max_report_versions: int` — default `3`, constrained `ge=1`; how many report versions may be
  written in one turn. Version 1 is the first draft; each later version is a rewrite the review
  demanded. The last permitted version is delivered without another review. `1` disables the
  review: the first draft is delivered unreviewed.
- `prompts` — a nested required model with two required, non-empty (`min_length=1`) string
  fields: `client_name`, `agent_name`. It SHALL NOT carry a `data_sources_descriptions` field: what
  the models are told about a server's sources is that server's `description` (see **An MCP server
  may describe its sources to the models**), and `Prompts` SHALL reject unknown fields, so a stored
  configuration that still sets `data_sources_descriptions` fails validation instead of having its
  text silently dropped.
  `prompts` SHALL also carry the optional `client_rules` list, empty by default, specified in
  **Prompts carry the channel's client rules** below.

The model SHALL NOT carry a deployment id (`channel_name` is dropped — instance identity
lives in DIAL Core) and SHALL NOT carry an Opik project name (moved to the
`OPIK_PROJECT_NAME` env setting).

#### Scenario: Valid properties validate

- **WHEN** `ApplicationProperties.model_validate` receives an object with the two prompt
  strings and no `max_research_iterations`
- **THEN** validation SHALL succeed and `max_research_iterations` SHALL equal `5`

#### Scenario: Empty prompt field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives an object where
  `prompts.client_name` or `prompts.agent_name` is an empty string
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: Report defaults resolve without configuration

- **WHEN** `ApplicationProperties.model_validate` receives an object that configures no report
  properties
- **THEN** validation SHALL succeed, `default_report_structure` SHALL be the three default sections
  in order (Overview, Key Findings, Additional context) with Key Findings alone carrying
  `protected: true`, `references_section_name` SHALL equal `References`,
  `references_section_empty_text` SHALL be the default cited-nothing sentence, `max_report_words`
  SHALL equal `2750`, and `max_report_versions` SHALL equal `3`

#### Scenario: Empty report structure is rejected

- **WHEN** `ApplicationProperties.model_validate` receives `default_report_structure` as an
  empty list, or a section with an empty `name` or `description`
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: A structure with no protected section is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` whose
  every section leaves `protected` at its default of `False`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming
  `default_report_structure` and stating that at least one section must be protected

#### Scenario: A section entry carrying the withdrawn references flag is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` whose
  section entry still carries `references_section: true`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the unknown field, rather
  than accepting a References section the report writer would be asked to write beside the one the
  application appends

#### Scenario: A section claiming the References heading is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing a
  section named `references` while `references_section_name` is at its default `References`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming that section and
  `references_section_name`

#### Scenario: A channel writes the section's strings in its readers' language

- **WHEN** an instance sets `references_section_name` and `references_section_empty_text` to
  strings of its own
- **THEN** validation SHALL succeed, the built section SHALL carry that heading, and a report
  citing nothing SHALL carry that text

#### Scenario: Duplicate section names are rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing
  two sections with the same `name`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the duplicated section
  name(s)

#### Scenario: A deployment protects a section of its own

- **WHEN** an instance configures a structure that marks a "Regulatory disclaimer" section
  `protected: true`
- **THEN** validation SHALL succeed and that section SHALL receive the same protection from user
  instructions as Key Findings does

#### Scenario: The removed descriptions field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives `prompts` carrying
  `data_sources_descriptions`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming `data_sources_descriptions`
  as an unexpected field
