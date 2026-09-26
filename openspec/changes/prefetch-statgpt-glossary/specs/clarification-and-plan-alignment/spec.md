## MODIFIED Requirements

### Requirement: Every preparation LLM call's inputs and outputs are specified

The preparation flow makes exactly three kinds of LLM call, and each one's inputs SHALL be
exactly what is listed here — nothing else reaches a model, and adding an input SHALL require
updating this requirement.

**1. The preparation agent's model call** (one per agent step)

- System prompt: the preparation instructions, filled with the instance's `agent_name`, today's
  date, and the turn's data-sources string: `data_sources_descriptions`, followed by the rendered
  glossary when the channel configures one (see **glossary-prefetch**). It carries no instruction
  to request missing definitions, because this agent has no MCP tools.
- Messages: the **full** conversation history reconstructed from the DIAL request — every user
  message as text, and for every prior assistant turn the persisted message slice (its
  `AIMessage`s and `ToolMessage`s) with image blocks rehydrated to base64 — followed by the
  current turn's accumulated messages. There SHALL be no truncation, windowing, or
  summarization; a turn that outgrows the model's context SHALL fail rather than silently drop
  history.
- Tools bound: the four preparation control tools.
- Output: assistant text and/or tool calls. The text is the user-visible answer, except on a
  turn where research starts (see the silent hand-off rule below).

**2. The query clarity check** (one per `update_query` call)

- System prompt: the intake-check instructions, filled with today's date and the turn's
  data-sources string, the same one the preparation agent receives.
- Messages: one human message carrying the rendered conversation so far and the candidate query.
  The rendering SHALL include only natural-language user and assistant text; tool calls, tool
  results, and system messages SHALL be dropped. No image content SHALL be included.
- Output: a structured `QueryReviewResponse` — a per-dimension assessment, then the clarifying
  questions (empty when the query is ready).

**3. The plan approval check** (one per `approve_plan` call)

- System prompt: the plan-approval instructions, filled with today's date only — no data-source
  descriptions and no glossary.
- Messages: one human message carrying the recorded plan as a numbered list and the rendered
  conversation, filtered exactly as in the clarity check. No image content.
- Output: a structured `PlanReviewResponse` — the assessment, whether the recorded plan matches
  the one last discussed, whether the user approved it, and a user-facing failure reason.

#### Scenario: The agent sees the whole conversation, the checks see only its prose

- **WHEN** a preparation turn runs on a conversation whose earlier turns contain tool calls, tool
  results, and page images
- **THEN** the preparation agent's model call SHALL receive all of it including the images, while
  the clarity check and the approval check SHALL receive only the user and assistant text

#### Scenario: History is never silently shortened

- **WHEN** the reconstructed history is long
- **THEN** the preparation agent SHALL receive every reconstructed message, with no truncation or
  summarization applied

#### Scenario: The agent and the clarity check see the glossary, the approval check does not

- **WHEN** a preparation turn runs on a channel whose glossary listed terms
- **THEN** the preparation agent's system prompt and the clarity check's system prompt SHALL carry
  the same data-sources string ending in the rendered glossary, and the approval check's system
  prompt SHALL carry neither the data-sources descriptions nor the glossary
