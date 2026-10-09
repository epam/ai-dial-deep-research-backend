## MODIFIED Requirements

### Requirement: Prompts carry the channel's client rules

`prompts` SHALL carry an optional `client_rules` field: a list of quality rules, empty by default.
A client rule is the channel's own rule, in the same shape as the application's generic rules
(see **source-selection**). It SHALL have these fields, and SHALL reject unknown ones
(`extra="forbid"`):

- `name: str` — required, not blank, and a single line; the heading the rule's parts are shown
  under in each step's prompt, which a line break would split.
- `research_agent`, `research_review`, `report_writer`, `report_review_blind`,
  `report_review_grounded` — each an optional string that is not blank, `null` by default; the
  rule's instruction to that step. A step that the rule gives no part receives nothing from it. A
  string of whitespace alone is blank. `report_review_blind` is a check the blind review judges from
  the draft alone; `report_review_grounded` is a check the grounded review judges against the
  research findings. Each field's description SHALL say which review reads it and what that review
  sees. The description of `report_review_blind` SHALL say that it is shown without the rule's
  writer part, so it names what it checks rather than referring to the writer part. The description
  of `report_review_grounded` SHALL say that a check that keeps content out of the report belongs in
  `report_review_blind`, because the removal rule and the check that every fact of the question is
  answered both rely on the blind review knowing what is excluded (see **prohibited-content**).

Validation SHALL reject a rule that sets none of the five parts, since such a rule reaches no
step, SHALL reject a rule that sets both `report_review_blind` and `report_review_grounded`, since a
check is judged by one review, and SHALL reject two rules with the same `name`, since each step
shows the parts under the
name and a duplicate makes two rules indistinguishable. Each error SHALL name the offending rule.

The field description SHALL tell the admin what a client rule is for: what a step must do
differently for this channel's sources, such as how its datasets document their methodology. It
SHALL say that a client rule is shown after the application's generic rules and takes precedence
where it is more specific.

`client_rules` has a default, so the committed `applications-template.json` SHALL NOT set it (see
**local-stack**).

#### Scenario: A channel without client rules validates

- **WHEN** `ApplicationProperties.model_validate` receives `prompts` with the three required
  strings and no `client_rules`
- **THEN** validation SHALL succeed and `prompts.client_rules` SHALL be an empty list

#### Scenario: A client rule with one part validates

- **WHEN** `prompts.client_rules` holds one rule named "Dataset methodology" whose only part is
  `research_agent`
- **THEN** validation SHALL succeed, and the rule's other four parts SHALL be `null`

#### Scenario: A client rule with no part is rejected

- **WHEN** `prompts.client_rules` holds a rule that sets only `name`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming that rule and stating that at
  least one part must be set

#### Scenario: An empty part is rejected

- **WHEN** a client rule sets `report_writer` to an empty string, or to a string of spaces
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the field

#### Scenario: A rule name with a line break is rejected

- **WHEN** a client rule's `name` contains a line break
- **THEN** validation SHALL raise a pydantic `ValidationError` identifying the field

#### Scenario: Duplicate client rule names are rejected

- **WHEN** `prompts.client_rules` holds two rules named "Dates"
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the duplicated name

#### Scenario: An unknown field of a client rule is rejected

- **WHEN** a client rule carries a field `writer` instead of `report_writer`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the unknown field

#### Scenario: The old review field name is rejected

- **WHEN** a client rule sets `report_review`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the unknown field, since the
  field is `report_review_blind`

#### Scenario: A client rule that sets both review parts is rejected

- **WHEN** a client rule sets both `report_review_blind` and `report_review_grounded`
- **THEN** validation SHALL raise a pydantic `ValidationError` naming the rule and stating that a
  rule sets at most one of the two
