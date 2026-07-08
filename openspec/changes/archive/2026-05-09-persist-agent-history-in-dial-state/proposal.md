## Why

DIAL natively persists `user`/`assistant` text but drops `tool` role messages and intermediate `AIMessage`s carrying only `tool_calls`. The current `deep-research` MVP intentionally accepts this loss — the "Cross-turn isolation of tool messages" scenario states that the second turn's agent sees only prior assistant text. For follow-up turns that reference earlier tool work ("show me a chart of what we just retrieved", "filter by year") the agent re-runs the whole research from scratch, which is slow, wasteful, and can produce inconsistent answers because the model is reasoning from a summary of its own prior output rather than the actual tool results. `create_agent` is a multi-step ReAct loop (see `_handle_ai_message`/`_handle_tool_message` dispatch in `agent.py`) — it can emit `AI(call) → Tool → AI(call) → Tool → AI(final)` with arbitrary depth — so faithful replay requires preserving the full ordered intermediate trace, not just the calls or the final text.

## What Changes

- During each chat completion, the agent SHALL accumulate every `AIMessage` and `ToolMessage` it observes via `astream(..., stream_mode="updates")` into a single ordered buffer.
- After the run completes, the agent SHALL serialize the buffer via `langchain_core.messages.messages_to_dict` and write it to `choice.set_state({"messages": [...]})`, which DIAL persists as `assistant.custom_content.state.messages` on the assistant turn it just produced.
- On the next request, history reconstruction SHALL walk `request.messages` and:
  - for `Role.USER` messages, emit a `HumanMessage` from the native `content` field;
  - for `Role.ASSISTANT` messages, ignore the native `content` / `tool_calls` fields and emit `messages_from_dict(msg.custom_content.state["messages"])` to recover the full intermediate + final slice;
  - fall back to `AIMessage(content=msg.content)` only if `custom_content.state["messages"]` is absent (legacy turns produced before this change).
- The DIAL native `assistant.content` field SHALL continue to receive the streamed final-answer text for UI display, but it is NOT consulted on reconstruction — `custom_content.state["messages"]` is the source of truth.
- DIAL native `tool_calls` / `tool_call_id` fields on assistant messages SHALL NOT be populated; the `custom_content.state` blob carries them faithfully and avoids any reliance on DIAL preserving structured fields on standard message slots.
- Encoding/decoding SHALL use the native LangChain helpers `messages_to_dict` / `messages_from_dict` (no hand-rolled if/elif type dispatch, no Pydantic carve-outs for tool-call shape).
- **Out of scope (deferred):** reasoning text emitted alongside `tool_calls` in the same `AIMessage` (Anthropic-style "let me check X first" + tool-use, extended thinking blocks) — currently dropped from user-visible streaming by the existing `if msg.tool_calls: ... elif msg.content: ...` branch, and not specially handled in persistence either. A future change will define how such reasoning round-trips through both the UI and the persisted history.
- **Out of scope (deferred):** non-text content blocks in the final assistant answer (images, citations, attachments). The use case is plain-text answers; if structured content blocks ever appear in the final `AIMessage.content`, they will be stringified for DIAL UI display via `str(...)` and re-parsed faithfully on the LangChain side from `custom_content.state["messages"]`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `deep-research`:
  - **Replace** the "Cross-turn isolation of tool messages" scenario under the "Assistant message content contains only model text" requirement: the new scenario states that intermediate tool messages ARE preserved across turns via `custom_content.state["messages"]`, while assistant `message.content` continues to carry only the final natural-language text.
  - **Add** a new requirement covering the persistence contract: the encoding key, the use of `messages_to_dict` / `messages_from_dict`, the partition between DIAL native fields (UI display) and `custom_content.state["messages"]` (replay source of truth), and the legacy-message fallback.

## Impact

- **Code**:
  - `src/dial_deep_research/app/agent.py`: add `self._messages: list[AIMessage | ToolMessage]` buffer on `AgentRunner`; append in both `_handle_ai_message` and `_handle_tool_message`; after `astream` completes, dump via `messages_to_dict` and call `self._choice.set_state({"messages": ...})`. Replace `_extract_history_from_dial_request` with a richer walker that emits `HumanMessage` for user turns and `messages_from_dict(...)` for assistant turns (with the legacy-message fallback). Drop the now-unused `_extract_text` helper.
- **Dependencies**: none — `messages_to_dict` / `messages_from_dict` ship with `langchain_core.messages`.
- **Configuration**: none.
- **DIAL surface**: the persisted assistant message gains a non-empty `custom_content.state` blob keyed under `messages`. Existing turns produced before this change have no such blob — the legacy fallback handles them. No UI-visible change (final answer streams unchanged; tool stages unchanged).
- **Tests**: round-trip test (dump → load) over a synthesized `[HumanMessage, AIMessage(tool_calls=[...]), ToolMessage(...), AIMessage(content="...")]` sequence; assertion that DIAL `message.content` and `custom_content.state["messages"]` are independently faithful.
