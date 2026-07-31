## MODIFIED Requirements

### Requirement: Application properties model

The repository SHALL define a pydantic model (`ApplicationProperties`) that is the single
source of per-channel configuration, replacing the YAML-loaded `ChannelConfig`. The model
SHALL expose:

- `max_research_iterations: int` — default `10`, constrained `ge=1`; the cap on
  research-agent → research-review loops before the report is forced.
- `max_research_graph_steps: int` — default `500`, constrained `ge=1`; the per-graph-run step
  ceiling passed to LangGraph as `recursion_limit` (see the **research-execution**
  capability's step-budget requirement for what it counts).
- `default_report_structure: list[ReportSection]` — the ordered sections a report follows when
  the user asks for no particular format, constrained `min_length=1`. `ReportSection` is a
  nested model with three fields:
  - `name: str` — required, non-empty (`min_length=1`); the section's heading in the report.
  - `description: str` — required, non-empty (`min_length=1`); everything the report writer and
    the review step need to know about this section's content. It is the **single home** for that
    section's rules: no other prompt, model, or spec SHALL carry per-section content
    instructions.
  - `protected: bool` — default `False`; whether user instructions may drop or restyle this
    section (see the **report-composition** capability's protected-sections requirement).

  The default value SHALL be the four sections Key Findings, Detailed Analysis, Conclusion, and
  References, each with its description; References SHALL default to `protected: true`, and its
  description SHALL carry the entry format for every source type a report may cite — publications
  and datasets alike — including what each entry decodes and the columns it carries.

  The list SHALL be constrained to contain at least one section with `protected: true`, so no
  configuration can produce a report whose every section a user instruction may remove. Section
  `name`s SHALL be unique across the list — as MCP `server_name`s already are — since duplicate
  headings make "every configured section is present" and the review step's ordered-section check
  ambiguous.
- `max_report_words: int` — default `2750`, constrained `ge=1`; the report's word ceiling (see
  the **report-composition** capability for how a word is counted and how the ceiling is
  enforced).
- `max_report_revisions: int` — default `2`, constrained `ge=0`; how many revisions the report
  review loop may request before the latest draft is delivered as-is. `0` disables the review.
- `prompts` — a nested required model with three required, non-empty (`min_length=1`) string
  fields: `client_name`, `agent_name`, `data_sources_descriptions`.

The model SHALL NOT carry a deployment id (`channel_name` is dropped — instance identity
lives in DIAL Core) and SHALL NOT carry an Opik project name (moved to the
`OPIK_PROJECT_NAME` env setting).

#### Scenario: Valid properties validate

- **WHEN** `ApplicationProperties.model_validate` receives an object with the three prompt
  strings and no `max_research_iterations`
- **THEN** validation SHALL succeed and `max_research_iterations` SHALL equal `10`

#### Scenario: Empty prompt field is rejected

- **WHEN** `ApplicationProperties.model_validate` receives an object where any of
  `prompts.client_name`, `prompts.agent_name`, or `prompts.data_sources_descriptions` is an
  empty string
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: Report defaults resolve without configuration

- **WHEN** `ApplicationProperties.model_validate` receives an object that configures no report
  properties
- **THEN** validation SHALL succeed, `default_report_structure` SHALL be the four default
  sections in order (Key Findings, Detailed Analysis, Conclusion, References) with References
  carrying `protected: true` and the source-table rules in its description, `max_report_words`
  SHALL equal `2750`, and `max_report_revisions` SHALL equal `2`

#### Scenario: Empty report structure is rejected

- **WHEN** `ApplicationProperties.model_validate` receives `default_report_structure` as an
  empty list, or a section with an empty `name` or `description`
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the offending field

#### Scenario: A structure with no protected section is rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` whose
  every section leaves `protected` at its default of `False`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming
  `default_report_structure` and stating that at least one section must be protected

#### Scenario: Duplicate section names are rejected

- **WHEN** `ApplicationProperties.model_validate` receives a `default_report_structure` containing
  two sections with the same `name`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the duplicated section
  name(s)

#### Scenario: A deployment protects a section of its own

- **WHEN** an instance configures a structure that marks a "Regulatory disclaimer" section
  `protected: true`
- **THEN** validation SHALL succeed and that section SHALL receive the same protection from user
  instructions as the references section does

### Requirement: DIAL application-type schema generation

The properties model SHALL generate a JSON schema conforming to the DIAL application-type
meta-schema (`https://dial.epam.com/application_type_schemas/schema#`). Generation SHALL:

- resolve root-property `$ref`s so each root property carries its own inline schema;
- inject a `dial:meta` object into every root property with `"dial:propertyKind": "server"`
  and a sequential `"dial:propertyOrder"` following field declaration order;
- support an `include_dial_fields` toggle: when enabled, the schema root SHALL additionally
  carry `$schema` (the DIAL meta-schema URI), `$id` (a generic placeholder ending in
  `/custom_application_schemas/deep-research`),
  `"dial:applicationTypeDisplayName": "Deep Research"`, and
  `"dial:appendApplicationPropertiesHeader": false`; when disabled, none of these root
  keywords SHALL be present (DIAL Core supplies them from its `applicationTypeSchemas` entry).

#### Scenario: Root properties carry dial:meta

- **WHEN** the schema is generated
- **THEN** every root property SHALL contain a `dial:meta` object with `dial:propertyKind` equal
  to `"server"` and a unique `dial:propertyOrder` integer

#### Scenario: A list-of-models property is inlined

- **WHEN** the schema is generated for `default_report_structure`, a list of nested
  `ReportSection` models
- **THEN** its `items` schema SHALL carry the `ReportSection` fields inline, with no `$ref` left
  anywhere in the generated schema

#### Scenario: Wrapper keywords only with include_dial_fields

- **WHEN** the schema is generated with `include_dial_fields` disabled
- **THEN** the schema root SHALL NOT contain `$id`, `$schema`, or any `dial:applicationType*`
  keyword, while the per-property `dial:meta` blocks SHALL still be present
