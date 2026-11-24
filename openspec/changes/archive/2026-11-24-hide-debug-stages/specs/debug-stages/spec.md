# Spec Delta

## Purpose

Separates the stages that tell a user what the research is doing from the stages that help the
people who run Deep Research, and lets each deployment decide whether the second kind is emitted.

## ADDED Requirements

### Requirement: The deployment decides whether debug stages are emitted

The app SHALL read a boolean environment variable `SHOW_DEBUG_STAGES`, default `false`. When it is
`true`, the app SHALL emit every debug stage. When it is `false`, the app SHALL emit no debug stage
at all, in every deployment the process serves. A turn cannot change this setting.

#### Scenario: Debug stages are hidden by default

- **WHEN** `SHOW_DEBUG_STAGES` is unset and a research turn calls a tool
- **THEN** the turn SHALL emit no `[TOOL]` result stage

#### Scenario: A deployment that shows debug stages emits them

- **WHEN** `SHOW_DEBUG_STAGES` is `true` and a research turn calls a tool
- **THEN** the turn SHALL emit the tool's `[TOOL]` result stage

#### Scenario: A deployment that hides debug stages emits none

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and a research turn calls tools, reviews its research and
  reviews its report
- **THEN** the turn SHALL emit no `[TOOL]`, `[RESEARCH REVIEW RESULT]` or `[REPORT REVIEW RESULT]`
  stage

#### Scenario: The playground follows the same setting

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and the playground deployment calls a tool
- **THEN** the playground SHALL emit no `[TOOL]` result stage

### Requirement: The debug stages are the tool, review, revision and snapshot stages

These stages SHALL be debug stages: tool result stages (`[TOOL]`), research-review stages
(`[RESEARCH REVIEW RESULT]`, the exhausted-budget one included), report-review stages
(`[REPORT REVIEW RESULT]`, the delivered-without-review one included), the failed-revision stage
(`[REPORT REVISION FAILED]`) and the snapshot stages (`[DEBUG]`). The activity stage SHALL NOT be a
debug stage. Requirements elsewhere that describe these stages describe their content when they are
emitted.

#### Scenario: The activity stage stays when debug stages are hidden

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and research moves from one step to the next
- **THEN** the turn SHALL still emit the activity stage naming the current step

#### Scenario: A budget-exhausted announcement is hidden with the reviews

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and the iteration cap leaves the last iteration unreviewed
- **THEN** the turn SHALL emit no exhausted-budget stage

#### Scenario: A failed revision is hidden

- **WHEN** `SHOW_DEBUG_STAGES` is `false` and the report call writing a revision fails, so the
  previous draft is delivered
- **THEN** the turn SHALL emit no `[REPORT REVISION FAILED]` stage and SHALL still deliver the
  previous draft

### Requirement: Hiding debug stages changes only the stages

When `SHOW_DEBUG_STAGES` is `false`, the app SHALL produce the same assistant content, attachments,
state and log records as when it is `true`. Only the debug stages are left out of the response.

#### Scenario: Logs and state do not depend on the setting

- **WHEN** the same research turn runs once with `SHOW_DEBUG_STAGES` set to `true` and once with
  `false`
- **THEN** both runs SHALL write the same log records and the same state, and their responses SHALL
  differ only in the debug stages
