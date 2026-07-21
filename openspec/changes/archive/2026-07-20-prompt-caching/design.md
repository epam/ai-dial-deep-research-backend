# Design — prompt-caching

## Context

### How DIAL Core prompt caching actually works

Findings from the DIAL docs (`docs.dialx.ai/tutorials/developers/prompt-caching`) and the
ai-dial-core source (`UpstreamCacheService`, `ChatCompletionRequest.buildCacheKeys`,
`BuildUpstreamCacheFn`, `UpstreamRoute`). Where docs and code disagree, this design follows
the code.

- Core's "prompt caching" is **sticky upstream routing**, not response caching. Core hashes
  parts of the request, stores `hash → upstream endpoint` in Redis, and routes later
  requests carrying a matching hash to the same upstream — so the *provider's* prompt cache
  gets hits. The actual token-level caching, its TTL, and its billing discount live at the
  provider; for OpenAI-family models the provider caches automatically for prompts of
  ~1024+ tokens, no request markers needed.
- Hashing is **per array element**, not a cumulative prefix (despite the docs' "prefix"
  wording): each entry of `tools` and `messages` is SHA-1-hashed in isolation, with JSON
  keys sorted. `custom_fields` is excluded from the hash entirely; of `custom_content` only
  `attachments` contributes. Every other field of the element is hashed verbatim — any
  byte change to an element's `role`/`content`/`tool_calls` changes that element's hash.
  Top-level fields (`stream`, `temperature`, `tool_choice`, `response_format`, …) are never
  hashed.
- With the deployment flag `auto_caching_supported` (the mode the target environments run,
  always on), **every element counts as a cache breakpoint** and the client needs no body
  changes: on read, Core picks the deepest element whose hash exists in Redis and routes to
  its upstream; on miss it falls back to the normal balancer; on success it stores one
  entry for the element the upstream echoes back. Default entry TTL is 10 minutes unless
  the upstream returns an expiry header.
- The routing policy header is **`X-DIAL-CACHE-POLICY`** (the tutorial says
  `X-CACHE-POLICY`; the code defines `X-DIAL-CACHE-POLICY`): `availability-priority`
  (default — on retry, fail over to another upstream) or `cache-priority` (retries stay on
  the cached upstream). Invalid values are rejected with HTTP 400.
- Only **Model deployments** on the **chat-completions API** participate — exactly the
  app's call path (`AzureChatOpenAI` → Core `/openai/deployments/{id}/chat/completions`).
- The Redis key is scoped to (storage prefix, model name) — **not** per api-key or user, so
  routing affinity is shared across all conversations hitting the same model.

Consequence for this app: with auto-caching already on, Core's side is done. What remains —
and what this change delivers — is the app's side of the bargain: **byte-stable request
prefixes** (otherwise neither Core's hashes nor the provider's prefix cache can match),
the **retry-policy choice**, and **evidence in the logs** that caching actually happens.

### What the app sends today

All LLM calls go through `get_chat_model` (`utils/llm.py`) — a per-call `AzureChatOpenAI`
against DIAL Core. Six call families: the preparation agent loop, the clarity check, the
approval check, the researcher tool loop, the reviewer, and the report. The researcher loop
dominates: up to ~200 model calls per turn, each re-sending the system prompt, all MCP tool
schemas, and an append-only message list.

Cache-relevant properties of the current requests:

- The researcher/preparation message lists are **append-only** within and across calls, and
  history reconstruction (`custom_content.state` round-trip) is byte-stable — good.
- System prompts embed `today_date` — byte-stable within a day; breaks caches at day
  boundaries (accepted).
- MCP tool order is whatever each server returns from `list_tools` — not guaranteed stable
  across requests, and a reorder silently changes both Core element hashes and the
  provider's token prefix.
- The reviewer's user message renders the growing plans list *before* the much larger
  findings log, so each iteration inserts bytes early in the message and invalidates the
  provider-side prefix from that point on.
- No policy header and no logging of cached-token counts —
  `usage_metadata.input_token_details["cache_read"]` is already delivered by
  `langchain-openai` (and `stream_usage` auto-enables for this client configuration, so
  streamed calls report usage too), but nothing reads it.

## Goals / Non-Goals

**Goals:**

- Make request prefixes byte-stable so the provider-side cache (and Core element hashes)
  hit: deterministic tool ordering, append-only reviewer prompt growth.
- Let a deployment operator choose the cache routing retry policy per environment without
  code changes (`X-DIAL-CACHE-POLICY`).
- Surface cached-token counts in the INFO skeleton so cache effectiveness is observable in
  logs (the feedback loop for tuning).

**Non-Goals:**

- Manual cache-breakpoint injection (`custom_fields.cache_breakpoint` on messages). The
  target environments run only OpenAI models behind the OpenAI adapter with auto-caching
  always enabled, so there is no manual-mode deployment and no Anthropic-style upstream
  that would need explicit markers. Deferred until either appears. (For the record, the
  viable mechanism is a `AzureChatOpenAI` subclass overriding `_get_request_payload` —
  LangChain's message converter drops arbitrary per-message fields, so payload
  post-processing is the one clean injection point.)
- Configuring DIAL Core itself (deployment feature flags, upstream adapters, Redis) —
  platform-side; this change only documents what the app relies on.
- Response caching, deduplication, or any semantic caching.
- Restructuring the report call to share the researcher's system prompt (see Decisions —
  rejected).
- Per-call-family cache policies — start with one global env toggle; split later if log
  data shows the need.

## Decisions

### D1. Cache policy header via an env setting and `default_headers`

A new `Settings` field `llm_cache_policy: Literal["availability-priority",
"cache-priority"] | None = None` (env `LLM_CACHE_POLICY`). When set, `get_chat_model`
passes `default_headers={"X-DIAL-CACHE-POLICY": <value>}` to the client, so every model
request carries it; when unset, no header is sent and Core applies its own default
(`availability-priority`). An env setting, not an application property: retry-policy
preference is an environment/operations concern, not a channel concern — the same home
rule `settings.py` already documents. Pydantic validates the value at startup, mirroring
Core's own 400 on unknown values.

`default_headers` suffices because the setting is process-wide constant; no per-request
header plumbing is needed.

### D2. Sort each server's MCP tools by name

`load_mcp_tools` keeps the configured server order (a meaningful, operator-chosen sequence)
and sorts tools by name within each server. This makes the serialized `tools` array
deterministic regardless of listing order. One-time cost: the first deploy of this change
reorders the array once and invalidates existing provider caches for a few minutes — noted,
accepted.

### D3. Reorder the reviewer's user message: stable → append-only-large → append-only-small

`query` (stable) first, then the findings log (large, append-only), then the plans list
(small, append-only), instead of today's query → plans → findings. Successive reviewer
calls then share a byte prefix up to the end of the previous findings, which OpenAI's
automatic prefix caching exploits. No behavior change for the model beyond section order.

### D4. Log cached tokens where usage is already logged

- Model-call INFO event (`ModelCallLoggingMiddleware`): extend the existing `tokens=in/out`
  field with the cached-read count from `usage_metadata.input_token_details["cache_read"]`
  (0 when absent).
- Reviewer and report INFO events: add the same token-usage field. The report node streams,
  so it reads `usage_metadata` from the chunk that carries it (usage arrives on the final
  chunk; `stream_usage` is already effectively on for this client configuration).

Counts only — inside the logging-policy content allowlist. This is deliberately the whole
observability story: before/after comparison happens in logs, no new metrics surface.

### Rejected: sharing the researcher's system prompt with the report node

The report call re-reads the entire transcript but starts with a different system message,
so it gets zero provider-side reuse of the researcher's cache. Making the report a
continuation of the researcher conversation (same system prompt, report request as the last
user message) would cache-hit almost the entire input — but the researcher prompt hard-forbids
prose output ("every step MUST be a tool call"), and undoing that with a trailing
instruction is exactly the kind of prompt conflict the separate-node design exists to
avoid. One call per turn does not justify it. Revisit only if log data shows the report
call dominating cost.

## Risks / Trade-offs

- **[All conversations of a channel pin to one upstream]** — in auto mode every element is
  a routing anchor, and elements shared across conversations (the per-channel system
  message) make all of a channel's calls match the same Redis entries while they live
  (~10 min default) → this is Core's intended behavior; the default
  `availability-priority` policy still fails over on errors, and load spreads again as
  entries expire.
- **[`cache-priority` trades availability for hit rate]** — retries stay on a possibly
  unhealthy upstream → keep the policy unset by default; the app's own transient-stream
  retries (`utils/llm.py`) still apply either way.
- **[Core docs/code drift]** — the header name (`X-DIAL-CACHE-POLICY` vs the tutorial's
  `X-CACHE-POLICY`) and the per-element (not cumulative) hashing come from today's Core
  source; a Core upgrade could change either → the spec pins app-side behavior only;
  re-verify Core behavior when the platform upgrades. On a Core too old to know the
  header, an unknown request header is ignored — the setting is inert, not harmful.
- **[Daily cache invalidation]** — `today_date` in system prompts breaks all caches at
  midnight → accepted; the win is intra-turn and intra-day, and removing the date would
  degrade prompt quality.
- **[Tool reorder on first deploy]** (D2) → one-time, self-heals within provider TTL.

## Migration Plan

1. Ship with the setting unset — behavior change is limited to tool ordering and the
   reviewer prompt layout (both invisible to users); README documents the new var.
2. Watch the cached-token counts in the model-call events to confirm provider-side hits
   during research turns (the baseline check that auto-caching + stable prefixes works).
3. Optionally set `LLM_CACHE_POLICY=cache-priority` per environment and compare cached-token
   counts and latency; revert by unsetting the var.
4. Rollback at any step: unset the env var; no state or data migration exists.

## Open Questions

- Does the OpenAI adapter pass the OpenAI `prompt_cache_key` request field through? If so,
  setting it per conversation could improve OpenAI-side cache routing beyond endpoint
  affinity under high load — a possible follow-up once cached-token logging shows the
  baseline hit rate.
