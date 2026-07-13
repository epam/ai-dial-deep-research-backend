# Tasks

## 1. Persistence buffer (response side)

- [x] 1.1 In `src/dial_deep_research/app/agent.py`, add an instance attribute `self._messages: list[AIMessage | ToolMessage] = []` to `AgentRunner.__init__`, alongside the existing `_pending_tool_calls` buffer.
- [x] 1.2 In `_handle_ai_message`, append the incoming `AIMessage` to `self._messages` unconditionally (both the `tool_calls`-bearing intermediate AIs and the final content-bearing AI). Do this in addition to — not instead of — the existing `if msg.tool_calls: ... elif msg.content: ...` UI dispatch. The user-visible streaming path is unchanged.
- [x] 1.3 In `_handle_tool_message`, append the incoming `ToolMessage` to `self._messages` unconditionally — including for the case where `_pending_tool_calls.pop(msg.tool_call_id, None)` returns `None` (a stage cannot be drawn, but the message must still round-trip on the LangChain side).
- [x] 1.4 After `agent.astream(...)` completes in `run`, serialize `self._messages` via `langchain_core.messages.messages_to_dict` and call `self._choice.set_state({"messages": <serialized>})`. Add the import.
- [ ] 1.5 Manually verify (single chat completion against a real or stub MCP server) that the persisted state blob round-trips: run a turn, capture the response, confirm `assistant.custom_content.state.messages` contains the expected sequence with `type` discriminators (`ai`, `tool`, `ai`, …).

## 2. History reconstruction (request side)

- [x] 2.1 Replace `_extract_history_from_dial_request` with a method that returns `list[BaseMessage]` (HumanMessage / AIMessage / ToolMessage), not the current `list[dict]`. Adjust the call site in `run` so `agent_input["messages"]` receives the new list.
- [x] 2.2 In the new method, iterate `request.messages`. For `Role.USER`: emit `HumanMessage(content=msg.content)` (use the existing `_extract_text` only if the content is a list of content-block parts; otherwise pass the string through directly). For `Role.SYSTEM`: skip — `create_agent` already receives the system prompt via its `system_prompt=` kwarg.
- [x] 2.3 For `Role.ASSISTANT`: read `msg.custom_content.state` if non-None, look up `state["messages"]`, and if present-and-non-empty call `messages_from_dict(...)` and extend the reconstructed history with the result.
- [x] 2.4 Legacy fallback for assistant turns with no usable state (custom_content/state/messages absent or empty): emit a single `AIMessage(content=msg.content)`. Ensure the fallback path does not raise on `custom_content is None` or on `state` being a non-dict value.
- [x] 2.5 Drop the now-unused `_extract_text` method if no caller remains. Drop or update its docstring otherwise.
- [ ] 2.6 Manually verify a two-turn conversation: run turn 1 with a tool-using prompt, then send turn 2 referencing the prior turn's tool output ("filter the result you just retrieved by year"). Confirm via logs (or a trace) that the second turn's reconstructed history contains the prior tool slice, and that the model answers without re-running search.

## 3. Unit tests

- [x] 3.1 Add a round-trip test in `tests/`: build a synthetic sequence `[AIMessage(tool_calls=[...]), ToolMessage(...), AIMessage(content="final")]`, dump via `messages_to_dict`, decode via `messages_from_dict`, assert structural equality (types, content, `tool_calls[i].id`/`name`/`args`, `tool_call_id`).
- [x] 3.2 Add a unit test for the new history-reconstruction method on `AgentRunner` (or a free function if extracted): given a stub `Request` with one user message and one assistant message whose `custom_content.state["messages"]` carries an encoded slice, the method returns `[HumanMessage, AIMessage(tool_calls=...), ToolMessage(...), AIMessage(content="final"), HumanMessage]` (the trailing HumanMessage from a follow-up turn). Use real DIAL SDK message types — do not mock `Request`/`Message` shape.
- [x] 3.3 Add a unit test for the legacy-fallback branch: given an assistant message with no `custom_content` and no `state`, the method emits `AIMessage(content=msg.content)` without raising.
- [x] 3.4 Add a unit test for the mixed-history branch: a `Request` whose history alternates legacy and new assistant turns reconstructs to a list mixing fallback `AIMessage`s with full-slice decodings, in original turn order, no exceptions.
- [x] 3.5 Per project guidance, do **not** add a test that only asserts the buffer field initializes empty.

## 4. Spec maintenance

- [x] 4.1 Run `openspec validate persist-agent-history-in-dial-state --strict`; fix any validation errors.
- [x] 4.2 Re-read the spec delta against the implemented `agent.py` and adjust wording drifts caught during code review (especially around the "Reconstruction of LangChain history from DIAL request" requirement — keep it accurate to what the code actually does).

## 5. Cleanup and verification

- [ ] 5.1 Run `make format` and `make lint`; expect green.
- [ ] 5.2 Run `make test_unit`; expect green.
- [ ] 5.3 Manual end-to-end: against a real generic-RAG MCP server, `make up && make run`, open the chat UI, run a tool-using turn, then a follow-up that references the prior tool output. Confirm the second turn's answer cites or builds on the prior tool result without re-running the same searches.
- [ ] 5.4 Manual fidelity check: in the DIAL admin / debug tooling (or via direct DIAL Core API), inspect the persisted assistant message of turn 1; confirm `custom_content.state.messages` is populated and well-formed; confirm `message.content` carries only the final answer text.
