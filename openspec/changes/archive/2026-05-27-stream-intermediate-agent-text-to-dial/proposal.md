## Why

The DIAL chat UI shows only the agent's final assistant text. The intermediate `AIMessage`s the agent emits alongside `tool_calls` (the "Plan:" and "Plan update:" segments in observed gpt-5-class runs) are silently dropped on the way to `choice`. They are visible in the persisted `assistant.custom_content.state.messages` slice (so cross-turn replay is fine), but the user reading the chat never sees the agent narrate why it is invoking a given batch of tools. On top of that, today's `agent.astream(stream_mode="updates")` only fires after a graph node completes — so even the final answer arrives as one big blob rather than streaming token-by-token, which is jarring next to a chat experience where text streams while the model is still generating.

## What Changes

- `_handle_ai_message` SHALL no longer be the path that delivers assistant text to `choice`. Its sole responsibilities become (a) appending the message to the persistence buffer `self._messages` and (b) registering pending tool-call bookkeeping. The existing `elif msg.content: self._choice.append_content(...)` branch is removed.
- `AgentRunner.run` SHALL invoke `agent.astream(..., stream_mode=["updates", "messages"])` so every LLM token emitted inside the graph is observable via the `"messages"` channel. The existing `"updates"`-channel handling for `AIMessage` / `ToolMessage` is preserved, but the dispatcher is split: `("updates", payload)` events go to the existing `_handle_ai_message` / `_handle_tool_message` path; `("messages", (chunk, metadata))` events go to a new `_handle_message_chunk` that flattens the chunk's content to plain text and calls `self._choice.append_content(...)` immediately.
- Text from EVERY `AIMessage` (intermediate text-plus-tool-calls messages AND the final text-only message) SHALL stream to `choice` token-by-token in the order the model produces it, interleaved with the existing tool stages.
- Between two streamed text segments separated by one or more tool stages, the app SHALL insert a `"\n\n"` separator so the persisted `message.content` (the concatenation of every `append_content` call) reads as coherent prose rather than running segments together.
- Non-text content blocks in streaming chunks (Anthropic `thinking` blocks, structured reasoning blocks, image blocks, etc.) SHALL be silently skipped. The existing "intermediate reasoning passthrough deferred" decision stands — only `text`-typed blocks reach the UI today.
- History reconstruction (`history.reconstruct_history`) and the persistence buffer (`AgentRunner._messages` → `set_state`) require no functional change — the intermediate `AIMessage` is already appended to `self._messages` ahead of the UI dispatch, so cross-turn replay already round-trips its `.content` verbatim via `messages_to_dict` / `messages_from_dict`. The chat-reopen UI behaviour is auto-fixed by the streaming change: DIAL's saved `message.content` is just the concatenation of `append_content` calls, so once intermediates stream they are present on reload too.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `dial-agent-with-mcp`:
  - **Modify** the "Assistant message content contains only model text" requirement: the persisted `message.content` carries ALL natural-language assistant text the agent produces (intermediate + final), in chronological order, still excluding serialized tool calls and tool results. Adjust the existing "Tool-using turn" scenario accordingly and add two new scenarios — one for intermediate text streaming alongside tool stages, one for structured content blocks being flattened to text-only.
  - **Modify** the "Streaming response path" requirement: add a scenario stating that assistant text streams token-by-token from the LLM (not in a single end-of-step burst), so users see content arrive while the model is still generating.

## Impact

- **Code**:
  - `src/dial_deep_research/app/agent.py`: switch `agent.astream` to `stream_mode=["updates", "messages"]`; split dispatch in `run`; drop the `elif msg.content: append_content(...)` branch from `_handle_ai_message`; add `_handle_message_chunk` that flattens chunk content (string or list-of-blocks) and emits text only; track a `_separator_pending` flag set when a tool stage closes and consumed by the next non-empty text chunk to prepend `"\n\n"`.
  - `src/dial_deep_research/app/history.py`: factor the existing `_extract_text` content-block flattener into a small shared util so `agent.py` can reuse it for streaming chunks. No behaviour change to history reconstruction itself.
- **Dependencies**: none. `stream_mode=["updates", "messages"]` is a stock LangGraph capability and the chat model returned by `get_chat_model` already streams by default for OpenAI-compatible DIAL Core deployments.
- **Configuration**: none.
- **DIAL surface**: `assistant.message.content` now contains intermediate-text + final-answer (concatenated with `"\n\n"` between segments), instead of just the final answer. `custom_content.state.messages` is unchanged. Stages are unchanged. Old saved conversations created before this change continue to display only their final answer on reload — the state slice is still complete, so the agent's next turn in such a chat still sees everything via `messages_from_dict`.
- **Tests**: a new unit test feeds a synthesized stream of mixed `("messages", (chunk, meta))` + `("updates", {...})` events into `AgentRunner` and asserts the recorded `append_content` calls (text-only, token-by-token order, `\n\n` between intermediate-text and final-text segments, non-text blocks skipped). Existing persistence and history round-trip tests stay green without modification.
