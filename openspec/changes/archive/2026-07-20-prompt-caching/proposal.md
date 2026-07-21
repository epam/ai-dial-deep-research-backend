# Prompt Caching Management

## Why

A research turn re-sends an ever-growing transcript to the LLM many times: the researcher
loop makes up to ~200 model calls per turn, each repeating the full system prompt, all MCP
tool schemas, and every prior message; the reviewer re-reads the accumulated findings each
iteration; the report call re-reads everything. Today every one of those calls pays full
input-token price and latency.

The target environments run OpenAI models behind the OpenAI adapter, with DIAL Core's
automatic caching (`auto_caching_supported`) always enabled on the model deployments. That
means Core already routes requests with matching content back to the same upstream, and the
provider caches prompt prefixes automatically — *if* the app sends byte-stable requests.
The app currently undermines this in two places (unordered MCP tool listings, a reviewer
prompt that inserts growing content before its largest section), leaves the cache-routing
retry policy at its default, and gives no visibility into whether caching happens at all.

## What Changes

- **Cache routing policy header (opt-in).** A new env setting that, when set, sends
  `X-DIAL-CACHE-POLICY` (`cache-priority` or `availability-priority`) on all model calls,
  controlling whether DIAL Core retries a failed call on the cache-warm upstream or fails
  over to another one.
- **Deterministic MCP tool ordering.** `load_mcp_tools` sorts each server's tools by name so
  the serialized `tools` array is byte-identical across requests and turns — a reordered
  tool list silently breaks both Core's content hashes and the provider's prefix cache.
- **Prefix-stable reviewer prompt.** The reviewer's user message currently inserts the
  growing plans list *before* the much larger findings log, shifting all following bytes
  every iteration; reorder so append-only content grows at the end.
- **Cache observability.** The model-call INFO skeleton event reports cached input tokens
  (LangChain's `input_token_details.cache_read`) alongside existing token usage; the
  iteration-reviewed and report-generated events gain token usage including the cached
  count. This is the feedback loop proving caching works (counts only — allowlist-safe).
- **Docs.** README environment-variables table gains the new setting; the local-stack
  config template documents the model-deployment flag (`auto_caching_supported`) the app
  relies on.

Not in scope: manual cache-breakpoint injection (`custom_fields.cache_breakpoint`) — no
manual-mode deployments or Anthropic-family models exist in the target environments today,
so there is nothing to mark breakpoints for; revisit if either appears (see design,
Non-Goals). Also not in scope: DIAL Core-side configuration of shared environments (owned
by the platform team), and restructuring the report node to share the researcher's system
prompt (rejected in design — prompt-quality risk outweighs the one-call saving).

## Capabilities

### New Capabilities

- `prompt-caching`: cache-aware LLM request shaping for auto-caching DIAL deployments —
  the `X-DIAL-CACHE-POLICY` header and its env setting, deterministic tool ordering, and
  prefix-stable prompt assembly for repeated calls.

### Modified Capabilities

- `logging-policy`: the INFO request-skeleton requirement changes — the model-call event's
  token usage is extended with the cached-input-token count, and the iteration-reviewed and
  report-generated events gain token usage fields.

## Impact

- `src/dial_deep_research/utils/llm.py` — cache-policy header wiring in `get_chat_model`
  (the single model-construction point, so all six call families inherit it).
- `src/dial_deep_research/settings.py` — one new env setting (optional).
- `src/dial_deep_research/app/mcp_tools.py` — tool ordering.
- `src/dial_deep_research/app/research/nodes.py` — reviewer prompt reordering; token usage
  in reviewer/report INFO events.
- `src/dial_deep_research/utils/agent_logging.py` — cached tokens in the model-call event.
- `README.md`, `dial_conf/` templates — new env var, Core-side flag documentation.
- No API or persisted-state changes; the setting can be flipped without invalidating
  existing conversations.
