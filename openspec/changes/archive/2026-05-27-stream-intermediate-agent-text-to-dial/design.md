## Context

`AgentRunner` today drives one chat-completion turn by iterating
`agent.astream(agent_input, stream_mode="updates", config=...)`. The graph is
the one returned by `create_agent` (LangGraph), so `"updates"` events only
fire once a node has finished — `AIMessage`s and `ToolMessage`s arrive as
fully-formed objects, not as token chunks. `_handle_ai_message` then routes
each `AIMessage` with the rule:

```python
if msg.tool_calls:
    # register pending tool-call bookkeeping
elif msg.content:
    self._choice.append_content(str(msg.content))
```

So:

- text emitted on the SAME `AIMessage` as `tool_calls` (the Plan/Plan-update
  segments in the captured conversation) is dropped from the user-visible
  stream.
- even text-only `AIMessage`s (the final answer) arrive as a single blob and
  go to `choice` in one shot — not token-by-token.

Both behaviours are inherited from `stream_mode="updates"`. Persistence is
unaffected: `self._messages.append(msg)` runs unconditionally for every
`AIMessage`, so `messages_to_dict(self._messages)` → `set_state` captures the
full slice (with intermediate `.content`) — confirmed in the captured DIAL
state of conversation `ai_dial_chat_conversation_5-26.json`.

A proven token-streaming pattern calls `chain.astream(inputs)` on a plain
LangChain `Runnable` and forwards every `AIMessageChunk.content` straight to
`choice.append_content`.
We cannot literally copy that — `create_agent` returns a LangGraph compiled
graph, not a `Runnable` chain — but LangGraph's `stream_mode="messages"`
provides the same shape (token chunks + metadata) inside the graph.

## Goals / Non-Goals

**Goals:**

- Every natural-language assistant token the LLM emits — whether on an
  intermediate `AIMessage(tool_calls=[...])` or on the final text-only
  `AIMessage` — reaches `choice.append_content` as it is generated, not after
  the producing node returns.
- Text segments separated by tool stages render as separate paragraphs in the
  saved `message.content`, not as concatenated strings.
- Persistence and cross-turn history reconstruction are unchanged on the
  outside: `state.messages` still carries the full intermediate-plus-final
  slice; `messages_from_dict` rebuilds the agent's view of prior turns intact.
- Tests cover the new dispatch in isolation, so a regression that re-introduces
  the `elif msg.content` shortcut or accidentally swallows the `"messages"`
  channel fails CI before manual QA.

**Non-Goals:**

- Streaming non-text content blocks (Anthropic `thinking` blocks, structured
  reasoning blocks, image blocks). The existing project memory
  "intermediate reasoning passthrough deferred" stays in force — those blocks
  are silently dropped, to be reconsidered in a dedicated future change.
- Mutating any already-saved DIAL conversation. Old chats produced before this
  change keep their final-answer-only `message.content`; the state slice is
  still complete and replay still works.
- Changing the chat model construction (`get_chat_model` / `LLMModelConfig`).
  OpenAI-compatible DIAL Core deployments stream by default; the existing
  defaults are sufficient.
- Surfacing intermediate text inside a dedicated DIAL stage. The product
  decision (taken in the planning chat) is to interleave intermediate text
  into the main message body so the user reads `Plan → stages → Plan update
  → stages → final answer` as one running message.

## Decisions

### D1. Combined stream mode `["updates", "messages"]` over `astream_events`

LangGraph supports composing stream modes via a list. The resulting events
arrive as `(mode, payload)` tuples — `("updates", node_dict)` for the
existing path and `("messages", (AIMessageChunk, metadata))` for token
streaming. The single `astream` call still runs the graph once; we just
subscribe to two views of the same execution.

**Alternative considered: `astream_events` (v2).** That API gives richer event
metadata (one event per LLM call, tool call start/end, etc.) and is what
LangChain's official streaming guide recommends for "stream tokens from an
agent". We are not adopting it because:

- it would re-shape every event handler in `AgentRunner` (more diff, more
  churn) for no behaviour gain over `stream_mode=["updates", "messages"]`,
- the existing `"updates"`-based dispatch for tool stages and the persistence
  buffer is exactly the shape we want to keep,
- the `"messages"` channel gives us token chunks directly — no filtering by
  event name, no `data.chunk` indirection.

### D2. Token streaming via `"messages"` channel; `"updates"` channel no longer touches `choice`

The new `_handle_message_chunk(chunk, metadata)` is the SOLE caller of
`choice.append_content` for assistant text. `_handle_ai_message` keeps only
its bookkeeping responsibilities (pending tool calls + append to
`self._messages`). The `elif msg.content` branch is removed entirely.

This avoids the double-emission risk that would otherwise exist: when the
`"updates"` event for an LLM node fires, `msg.content` is the full
accumulated text we already streamed via `"messages"`. By making the
two channels disjoint in what they emit to `choice`, there is no
de-duplication logic, no chunk-vs-message matching, no risk of drift.

**Alternative considered: keep `"updates"` as the text source, drop
`"messages"`.** Cheapest possible diff, but it does not solve the
"as-soon-as-possible" requirement — text would still arrive only after a node
returns. Rejected.

**Alternative considered: stream from `"messages"` AND also call
`append_content` from `"updates"` for safety, then dedupe on chunk metadata.**
Adds complexity for no benefit since `"messages"` is documented to fire for
every LLM invocation inside the graph. Rejected.

### D3. Separator inserted via `_separator_pending` flag

Token chunks within one `AIMessage` are continuous. Between AIMessages there
is at least one tool stage round-trip. Without a separator, the persisted
`message.content` reads `"Plan: …Plan update: …## Scope: …"` with no
paragraph break. We track a single `bool` on `AgentRunner`:

- set `_separator_pending = True` when a tool stage closes (`_handle_tool_message`),
- on the next non-empty text chunk, if the flag is True, prepend `"\n\n"` to
  the emitted text and reset the flag.

This is symmetric with how a human writes: stages are "side work", text
following stages is a new paragraph. Empty chunks (some providers emit
zero-text chunks with usage-only metadata) do not consume the flag.

**Alternative considered: track chunk-message-id transitions and insert a
separator on id change.** More precise but harder to reason about — message
ids can be `None` early in some provider implementations, and we would need
to handle "first chunk ever" (no separator wanted) specially. The flag is
local and deterministic.

**Alternative considered: emit the separator from `_handle_ai_message` when
we observe a new AIMessage in `"updates"`.** That fires AFTER the chunks of
that message already streamed, so the separator would appear in the wrong
place. Rejected.

### D4. Content-block flattening shared between streaming and history paths

`history._extract_text` already knows how to flatten a `BaseMessage.content`
that may be a `str` or a `list[ContentBlock]`. Streaming chunks have the same
shape: `chunk.content` is usually a `str`, but some providers (Anthropic via
LiteLLM, OpenAI Responses API with structured output) emit lists of
`{type: ..., text: ...}` blocks. We promote `_extract_text` to a shared util
(new module `dial_deep_research.utils.content.py` exporting
`extract_text_from_content(content) -> str`) and call it from both
`history.reconstruct_history` and the new `_handle_message_chunk`.

Behaviour for non-text blocks: ignored. A `thinking` block, an `image` block,
or any unknown-typed block produces no text contribution. This preserves the
existing project memory "intermediate reasoning passthrough deferred".

### D5. Persistence buffer and history reconstruction stay untouched

`self._messages.append(msg)` continues to run unconditionally in
`_handle_ai_message` and `_handle_tool_message`, both fed off the
`"updates"` channel. `messages_to_dict(self._messages)` → `set_state` is
called at the end of `run` exactly as today. `history.reconstruct_history`
is unchanged.

The reason this just works: the intermediate `AIMessage`'s `.content` field
is captured by `messages_to_dict` regardless of what we did with it on the
UI side. So next-turn replay sees `AIMessage(content="Plan: …", tool_calls=[…])`
exactly as before — the LLM gets full fidelity of its own prior reasoning.

## Risks / Trade-offs

[Risk] **`stream_mode="messages"` not firing for every LLM call.** Mitigation:
unit test feeds a synthesized `("messages", ...)` stream into `AgentRunner`
and asserts the recorded `append_content` calls; manual end-to-end with a
real DIAL Core deployment is part of cleanup tasks.

[Risk] **Provider-specific chunk content shapes.** Anthropic chunks via LiteLLM
sometimes emit `content` as `list[{type: "text", text: "..."}]`, sometimes as
a bare `str`. Mitigation: `extract_text_from_content` handles both; unknown
block types contribute the empty string rather than `str(block)`.

[Risk] **Old saved conversations look unchanged in the UI.** A conversation
created before this change still has only the final answer in
`message.content`, even though the state slice has the intermediate text. We
accept this — backfilling would require either DIAL-side migration tooling
or per-message rehydration on read, both out of scope for this change.

[Risk] **Stream-order interleaving surprises.** The captured conversation
shows model→tool→model→tool→model. In some edge cases (parallel tool calls
across providers, mid-message streaming interruptions) the order of
`"messages"` and `"updates"` events could in principle interleave
differently than expected. Mitigation: the `_separator_pending` flag is
self-healing — if a separator is set and the next chunk is empty, it stays
pending until real text arrives.

[Risk] **`append_content` granularity load.** Token-level appending produces
many small SSE chunks for DIAL Core to forward to the chat client. This
shape is already proven in production, so no new risk.

## Migration Plan

This is a streaming/UI change with no schema or persistence-format change.

1. Land the code change. New turns in any conversation immediately stream
   intermediate text.
2. Old saved conversations continue to render only their final answer (their
   `message.content` was finalized before the change). No action needed.
3. Rollback: revert the `agent.py` change; the persisted state format is
   unchanged so no data cleanup is required.
