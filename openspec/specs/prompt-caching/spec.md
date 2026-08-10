# prompt-caching

## Purpose

Cache-aware LLM request shaping for DIAL deployments with automatic prompt caching. The app
sends byte-stable request prefixes (deterministic MCP tool ordering, append-only prompt
assembly for repeated calls) so DIAL Core's content hashes and the provider's prompt cache
can match across a research turn, optionally sends the `X-DIAL-CACHE-POLICY` routing header,
and surfaces cached-input-token counts so cache effectiveness is observable. Behavior is
app-side only; enabling caching on a model deployment is a DIAL Core concern.

## Requirements

### Requirement: Cache routing policy header behind an env setting

The service SHALL support sending the DIAL Core cache routing policy header on LLM calls,
gated by a `Settings` field `llm_cache_policy` (env `LLM_CACHE_POLICY`) restricted to
`availability-priority` or `cache-priority`, default unset. When set, every model request
produced by `get_chat_model` SHALL carry the header `X-DIAL-CACHE-POLICY` with the
configured value; when unset, the header SHALL NOT be sent (DIAL Core then applies its own
default, `availability-priority`). Any other value SHALL cause `Settings` instantiation to
fail with a Pydantic `ValidationError` identifying the `llm_cache_policy` field.

#### Scenario: Policy set — header sent

- **WHEN** `LLM_CACHE_POLICY=cache-priority` and any model call is made
- **THEN** the outgoing request carries `X-DIAL-CACHE-POLICY: cache-priority`

#### Scenario: Policy unset — no header

- **WHEN** `LLM_CACHE_POLICY` is unset and any model call is made
- **THEN** the outgoing request carries no `X-DIAL-CACHE-POLICY` header

#### Scenario: Invalid policy rejected at startup

- **WHEN** `LLM_CACHE_POLICY=always` is passed to `Settings`
- **THEN** instantiation SHALL raise a Pydantic `ValidationError` whose error entry
  references the `llm_cache_policy` field

### Requirement: Deterministic MCP tool ordering

`load_mcp_tools` SHALL return the tools in a deterministic order regardless of the order
the MCP servers list them in: servers in their configured order, and within each server the
(filtered) tools sorted by tool name. Two calls against the same configuration and the same
server tool sets SHALL yield the same tool sequence, so the serialized `tools` array of
model requests is byte-stable across requests and turns.

#### Scenario: Shuffled server listing yields the same order

- **WHEN** an MCP server returns the same tool set in a different listing order on two
  consecutive requests
- **THEN** `load_mcp_tools` returns the tools in the same (name-sorted, per-server) order
  both times

#### Scenario: Server order is preserved

- **WHEN** two MCP servers are configured in a given order
- **THEN** all tools of the first server precede all tools of the second, each group
  name-sorted internally

### Requirement: Prefix-stable reviewer prompt assembly

Research-review's user message SHALL be assembled so that content growing across iterations is
appended after earlier content, never inserted before it: first the research question
(stable for the run), then the findings log (append-only), then the plans list
(append-only). Successive research-review calls within one research run therefore share a byte
prefix covering the question and all previously rendered findings.

#### Scenario: A later research-review call extends the earlier one's prefix

- **WHEN** research-review runs on iteration N and again on iteration N+1 of the same research
  run, with new findings and a new plan added in between
- **THEN** the iteration-N+1 user message starts with the same bytes as the iteration-N
  user message up through the end of iteration N's findings section, and the new findings
  and the plans section follow after that common prefix
### Requirement: Prefix-stable report revision assembly

A report revision's request SHALL extend the previous draft's request rather than replace any part
of it: the system prompt, the findings transcript, and the report request stay byte-identical, and
the revision inputs — the draft being revised, the review's instructions, and the measured word
count with the ceiling — are **appended after** them. Successive report calls within one research
run therefore share a byte prefix covering everything the first draft was written from, which is
the bulk of the request.

This is the same shape as research-review's prompt assembly, applied to a different call: content
that grows across calls goes after content that does not.

**report-review's user message SHALL follow the same rule**: the configured structure, the protected
sections, the ceiling, the research question and the approved plan first — all constant across the
review calls of one run — then the draft and its measured word count last.

#### Scenario: A revision extends the draft's prefix

- **WHEN** the report node writes revision N+1 after draft N in the same research run
- **THEN** revision N+1's request SHALL start with the same bytes as draft N's request up through
  the end of the report request section, with the draft, the instructions, and the counts following
  after that common prefix

#### Scenario: Revision inputs are never inserted before the transcript

- **WHEN** a revision's inputs are assembled
- **THEN** neither the review instructions nor the previous draft SHALL be placed ahead of the
  findings transcript or the system prompt, since doing so would invalidate the cached prefix for
  every subsequent call in the run
