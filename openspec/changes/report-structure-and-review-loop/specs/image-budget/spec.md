## MODIFIED Requirements

### Requirement: No LLM call ever exceeds the image budget

Every LLM request the app issues SHALL carry at most the configured image budget of image
content blocks — from any agent, node, or channel, current or future. The budget SHALL default
to 50 — the documented
[Azure OpenAI limit](https://learn.microsoft.com/en-us/azure/ai-services/openai/quotas-limits)
on images per request, counted across the messages array / conversation history. The doc row
names only GPT-4o / GPT-4.1, but the same limit is observed on the newer model families the app
actually runs (the provider rejects the 51st image with a 400 error). Other providers document
different limits — [OpenAI's own API](https://developers.openai.com/api/docs/guides/images-vision)
allows up to 1500 images and 512 MB of total payload per request — and the values may change
over time, so the budget SHALL be configurable via the `MAX_CONTEXT_IMAGES` environment
variable. (Per-image *size* limits —
[20 MB per input image on Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision)
— are enforced by the provider and are out of this capability's scope, which governs count
only.) A call path may satisfy this by direct enforcement or by construction (e.g. a history
already bounded by an enforcement point, or no image content at all), but any change that
introduces an LLM call whose history is not already bounded SHALL add enforcement for that call.

#### Scenario: Requests stay within the budget
- **WHEN** the research-agent state accumulates more image blocks than the budget allows
- **THEN** every subsequent LLM request (research-agent, report) SHALL contain at most the
  budgeted number of image blocks, and no provider "too many images" error SHALL occur

#### Scenario: Playground requests stay within the budget
- **WHEN** the playground agent's tool results accumulate more image blocks than the
  budget allows
- **THEN** every subsequent playground LLM request SHALL contain at most the budgeted
  number of image blocks

#### Scenario: Budget is configurable
- **WHEN** `MAX_CONTEXT_IMAGES` is set in the environment
- **THEN** enforcement SHALL use that value instead of the default 50

### Requirement: Overflowing tool results are substituted newest-first before the model call

The app SHALL count image blocks across the agent state before each model call of every agent
whose tools may return images (currently research-agent and the playground). While the total
exceeds the budget, it SHALL substitute image-carrying tool messages with error tool messages
(same message id, `status="error"`), walking from the newest tool message to the oldest and
stopping as soon as the total is within the budget. Enforcement SHALL be tool-agnostic: it
SHALL count image blocks in returned content and SHALL NOT depend on tool names or tool-call
arguments. The substitution SHALL be a state update on the agent's messages, so later model
calls in the same turn and the report node see the substituted messages. The slice persisted
into `custom_content.state` SHALL be taken from the graph's final state, so it carries the
substituted messages rather than the originals.

#### Scenario: Parallel batch overflows
- **WHEN** the conversation holds 49 images against a budget of 50 and one tool round
  lands two results: message `a` with 4 images followed by message `b` with 1 image
- **THEN** walking newest-first, both `b` (54 → 53) and `a` (53 → 49) SHALL be substituted
  with error tool messages before the model sees them, leaving 49 images in state

#### Scenario: Model never sees dropped images
- **WHEN** a tool round pushes the image count over the budget
- **THEN** the overflowing results SHALL be substituted before the next model call, so no
  LLM request ever contains the dropped image blocks

#### Scenario: Substitution reaches the report node
- **WHEN** tool messages are substituted and the turn later reaches the report node
- **THEN** the report request SHALL contain the substituted error messages, not the
  original images

#### Scenario: Substitution reaches the persisted state
- **WHEN** tool messages are substituted and the turn is persisted
- **THEN** the slice written to `custom_content.state` SHALL contain the substituted error
  messages, and the dropped images SHALL NOT be uploaded to DIAL files

### Requirement: Researcher prompt discloses the image budget

The research-agent system prompt SHALL mention that a conversation-wide image budget exists and
that overflowing image results are dropped with an explanatory tool error, so the agent treats
a dropped result as budget exhaustion rather than a transient tool failure. The prompt SHALL
NOT restate what to do about a given drop — the substituted tool messages carry that
instruction.

#### Scenario: Prompt mentions the budget
- **WHEN** the research-agent is built
- **THEN** its system prompt SHALL include the image-budget disclosure
