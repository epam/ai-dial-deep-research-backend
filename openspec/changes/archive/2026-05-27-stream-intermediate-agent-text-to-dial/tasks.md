# Tasks

## 1. Shared content-block flattening utility

- [x] 1.1 Create `src/dial_deep_research/utils/content.py` exporting `extract_text_from_content(content: Any) -> str`. The helper SHALL accept `None` (returns `""`), `str` (returned as-is), or `list[Any]` (iterates, extracts only `text`-typed entries — both attribute-style and dict-style blocks must carry `type == "text"` — and concatenates; all other block types contribute nothing). Anything else falls back to `str(content)`.
- [x] 1.2 Replace the local `_extract_text` in `src/dial_deep_research/app/history.py` by importing and calling the new util directly at the two `reconstruct_history` call sites, keeping its behaviour identical. (The `_extract_text` shim was removed entirely rather than kept as a wrapper.)

## 2. Streaming dispatch in `AgentRunner`

- [x] 2.1 In `src/dial_deep_research/app/agent.py`, add `self._separator_pending: bool = False` to `AgentRunner.__init__`, alongside `_pending_tool_calls` and `_messages`.
- [x] 2.2 Change the `agent.astream(...)` call in `AgentRunner.run` to `stream_mode=["updates", "messages"]`. The loop body now iterates `(mode, payload)` tuples; dispatch on `mode`: `"updates"` → existing handling via `_handle_ai_message` / `_handle_tool_message`; `"messages"` → new `_handle_message_chunk(chunk, metadata)`.
- [x] 2.3 Remove the `elif msg.content: self._choice.append_content(str(msg.content))` branch from `_handle_ai_message`. The remaining responsibilities are: append the message to `self._messages` (unchanged) and, if `msg.tool_calls`, register pending tool-call bookkeeping (unchanged).
- [x] 2.4 Add `_handle_message_chunk(self, chunk: BaseMessage, metadata: dict) -> None`. The method SHALL: (a) skip anything that is not an `AIMessageChunk` — LangGraph's `messages` stream also emits node-output messages such as `ToolMessage`s, which must NOT reach the user-visible body; (b) call the shared `extract_text_from_content` util on `chunk.content`; (c) if the resulting text is empty, return without consuming the separator flag; (d) otherwise, if `self._separator_pending` is True, prepend `"\n\n"` and reset the flag, then call `self._choice.append_content(text)`.
- [x] 2.5 In `_handle_tool_message`, set `self._separator_pending = True` right after buffering the message, so a tool-message arrival induces the paragraph break in the streamed text body.
- [x] 2.6 Update the import line at the top of `agent.py` to include `AIMessageChunk` from `langchain_core.messages`.
- [x] 2.7 Raise `ValueError` in `_handle_tool_message` when `tool_call_id` matches no pending tool call (invariant violation), instead of silently early-returning. The top-level error funnel converts it into the friendly assistant message + server log.

## 3. Unit tests

- [x] 3.1 Create `tests/test_streaming_dispatch.py` with a hand-rolled `Choice` spy that records `append_content` and stage operations as a chronological list. Add `tests/test_content.py` for the flattening util.
- [x] 3.2 Test: token-by-token streaming, no duplication from the `"updates"` path.
- [x] 3.3 Test: intermediate text + tool stage + final text yields a `"\n\n"` separator on the first post-stage chunk.
- [x] 3.4 Test: empty chunk does not consume the separator flag.
- [x] 3.5 Test: structured content blocks flatten to text only (thinking/image skipped).
- [x] 3.6 Per project guidance, no test that only asserts `_separator_pending` initializes `False`.
- [x] 3.7 Test: a non-`AIMessageChunk` (e.g. `ToolMessage`) reaching `_handle_message_chunk` produces no user-visible text.
- [x] 3.8 Test: `_handle_tool_message` with an unmatched `tool_call_id` raises `ValueError`.

## 4. Spec validation

- [x] 4.1 Run `openspec validate stream-intermediate-agent-text-to-dial --strict`; clean.

## 5. Cleanup and verification

- [x] 5.1 Run `make format` and `make lint`; green.
- [x] 5.2 Run `make test`; green (51 passed).
- [x] 5.3 Manual end-to-end in the DIAL chat UI: confirmed by user — intermediate text streams into the body and tool outputs appear only in stages.
- [x] 5.4 Manual fidelity check in saved DIAL state: confirmed by user — `assistant.custom_content.state.messages` carries the full intermediate-plus-final slice with original per-message content (no separators), while the UI's `message.content` renders the streamed text with `"\n\n"` separators.
- [x] 5.5 Update the project memory: text passthrough implemented; non-text reasoning blocks (Anthropic `thinking`, structured reasoning) remain deferred.
