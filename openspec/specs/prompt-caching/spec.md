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

The reviewer's user message SHALL be assembled so that content growing across iterations is
appended after earlier content, never inserted before it: first the research question
(stable for the run), then the findings log (append-only), then the plans list
(append-only). Successive reviewer calls within one research run therefore share a byte
prefix covering the question and all previously rendered findings.

#### Scenario: Later reviewer call extends the earlier one's prefix

- **WHEN** the reviewer runs on iteration N and again on iteration N+1 of the same research
  run, with new findings and a new plan added in between
- **THEN** the iteration-N+1 user message starts with the same bytes as the iteration-N
  user message up through the end of iteration N's findings section, and the new findings
  and the plans section follow after that common prefix
