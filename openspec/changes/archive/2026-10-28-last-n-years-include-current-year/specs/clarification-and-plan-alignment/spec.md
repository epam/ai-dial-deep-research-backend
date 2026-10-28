# Spec Delta

## ADDED Requirements

### Requirement: A span of years counted back from today ends with the current year

A span of N years counted back from today ("the last N years", "the past N years") SHALL end with
the current year, which counts as one of the N although it has not ended, so the span starts N-1
years earlier. The default span the agent applies when the user declines to choose the time
period, the last 10 years, SHALL be counted the same way. The preparation agent's prompt and the
query check's prompt SHALL both state the rule with an example whose years are computed from
today's date.

#### Scenario: The last two years include the current year

- **WHEN** in October 2026 the user asks for GDP growth in Germany over the last 2 years
- **THEN** the query the agent records and the plan SHALL give the period as 2025–2026, and
  SHALL NOT give it as 2024–2025

#### Scenario: The default span on a declined time choice ends with the current year

- **WHEN** in 2026 the user declines to choose the time period
- **THEN** the agent SHALL apply 2017–2026 as the last 10 years, and SHALL tell the user that
  range

#### Scenario: The query check accepts a span resolved this way

- **WHEN** in 2026 the user asks how inflation in Germany changed over the last three years, and
  the agent restates the period as 2024–2026
- **THEN** the query check SHALL record no question about the time period

#### Scenario: A span given in months runs to today

- **WHEN** in October 2026 the user asks for developments over the last 6 months
- **THEN** the period SHALL run from April 2026 to today, and the rule on years SHALL NOT
  stretch it to the whole of 2026
