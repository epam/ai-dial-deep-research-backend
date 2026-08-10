## ADDED Requirements

### Requirement: Every preparation LLM call's inputs and outputs are specified

The preparation flow makes exactly three kinds of LLM call, and each one's inputs SHALL be
exactly what is listed here — nothing else reaches a model, and adding an input SHALL require
updating this requirement.

**1. The preparation agent's model call** (one per agent step)

- System prompt: the preparation instructions, filled with the instance's `agent_name`, today's
  date, and `data_sources_descriptions`.
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

- System prompt: the intake-check instructions, filled with today's date and
  `data_sources_descriptions`.
- Messages: one human message carrying the rendered conversation so far and the candidate query.
  The rendering SHALL include only natural-language user and assistant text; tool calls, tool
  results, and system messages SHALL be dropped. No image content SHALL be included.
- Output: a structured `QueryReviewResponse` — a per-dimension assessment, then the clarifying
  questions (empty when the query is ready).

**3. The plan approval check** (one per `approve_plan` call)

- System prompt: the plan-approval instructions, filled with today's date only — no data-source
  descriptions.
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

## MODIFIED Requirements

### Requirement: start_research hard-gates and stops at readiness

The `start_research()` tool SHALL fail with an error naming the missing
precondition unless the working query is set, the clarifications are resolved, and
the plan is approved. On a passing gate the tool SHALL mark research as started and
return a ready-to-research summary (the finalized query and the approved plan). The
tool itself SHALL NOT run research, review, or report generation: the turn
coordinator launches the research graph after the preparation agent's run finishes
(see the **research-execution** capability), so the flag is the hand-off signal.

Once the gate has passed and research is marked as started, the preparation agent SHALL make **no
further model call** in that turn — so there is no acknowledgement, no "research is starting"
message written after the hand-off. This SHALL hold regardless of what the model would have
written: the app SHALL end the preparation agent's run as soon as research is marked as started,
rather than relying on the prompt to keep it quiet.

**Accepted limitation — one case remains outside that guarantee, by construction.** Text the model
emits on the **same** assistant message that carries the `start_research` call has already been
streamed by the time the tool executes, so nothing downstream of the call can withhold it, and DIAL
content cannot be retracted. Such text is contracted to reach the assistant content anyway (see
**dial-agent-with-mcp**'s assistant-content requirement, which carries text from intermediate
messages that also carry tool calls).

A launch turn MAY therefore still open with a stray sentence ahead of the report. The only guard is
that the preparation instructions no longer ask the agent to announce the hand-off, and the
instructions SHALL keep not asking for it. This is a knowingly accepted gap in the "the response is
the report alone" goal, not an omission: closing it would mean buffering all preparation text until
the agent run ends, at the cost of streaming clarifying questions live. The delivered content SHALL
be the report alone in every case the app can control.

A gate **failure** SHALL leave the agent free to continue: it receives the error, and it SHALL
still reply to the user — a rejected `start_research` SHALL never produce a turn with no
answer.

#### Scenario: Gate failure names the missing precondition
- **WHEN** `start_research` is called with the plan not yet approved
- **THEN** it SHALL fail with an error that names plan approval as the missing precondition, and SHALL NOT mark research as started

#### Scenario: Gate pass returns the ready-to-research summary
- **WHEN** `start_research` is called with the query clear and the plan approved
- **THEN** it SHALL mark research as started and return a summary containing the finalized query and the approved plan; the tool call itself SHALL NOT produce a research report

#### Scenario: Hand-off is silent
- **WHEN** `start_research` passes its gate during a turn
- **THEN** the preparation agent SHALL make no further model call in that turn, and no text written after the hand-off SHALL reach the assistant content

#### Scenario: Text on the calling message is the one case not suppressed
- **WHEN** the model emits natural-language text on the same assistant message that calls `start_research`
- **THEN** that text SHALL already have been streamed and SHALL remain in the assistant content, ahead of the report; ending the agent run cannot retract it, and only the prompt discourages it

#### Scenario: Gate failure still answers the user
- **WHEN** `start_research` is rejected because the plan is not approved
- **THEN** the preparation agent SHALL continue its run and reply to the user with what is still needed, and the turn SHALL NOT end with empty assistant content
