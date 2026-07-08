## MODIFIED Requirements

### Requirement: Streaming response path
The app SHALL produce its assistant response through the SDK's streaming API so that the streaming code path is exercised end-to-end. The app SHALL stream assistant text to `choice` token-by-token as the LLM produces it, rather than buffering each LLM call's full output and emitting it as a single chunk after the producing graph node returns; concretely, the per-request agent's `astream` invocation SHALL subscribe to LangGraph's `messages` stream mode (composed with the existing `updates` mode) and forward every `AIMessageChunk`'s text content to `choice.append_content` immediately, so users see content arrive while the model is still generating.

#### Scenario: Streamed delivery
- **WHEN** DIAL core requests a streaming chat completion
- **THEN** the app SHALL emit the assistant content via one or more streaming chunks terminated by an end-of-stream signal, conforming to the SDK's streaming contract

#### Scenario: Assistant text streams token-by-token, not message-by-message
- **WHEN** the agent's underlying LLM produces a multi-token assistant message (whether the final answer or an intermediate text-plus-tool-calls message)
- **THEN** the app SHALL emit `choice.append_content` calls for individual token chunks during generation, such that DIAL core observes incremental content updates before the producing LangGraph node has returned, and SHALL NOT defer the text to a single end-of-step emission

### Requirement: Assistant message content contains only model text
The DIAL response message content SHALL carry all of the agent's natural-language assistant text emitted during the turn, in chronological order — including text produced on intermediate `AIMessage` instances that also carry `tool_calls`, not just the final text-only `AIMessage`. Tool calls, tool results, and any structured non-text content blocks (e.g. Anthropic-style `thinking` blocks, image blocks) SHALL NOT appear in the assistant message content; they are conveyed via stages (for tool execution UI display) and via `assistant.custom_content.state["messages"]` (for cross-turn replay). When two streamed text segments from distinct `AIMessage`s are separated in time by one or more tool stages, the app SHALL insert a `"\n\n"` separator between them in `message.content` so the segments render as separate paragraphs rather than running together.

#### Scenario: Tool-using turn streams intermediate text alongside the final answer
- **WHEN** the agent produces an intermediate `AIMessage` carrying both natural-language text (e.g. `"Plan: ..."`) and `tool_calls`, then tool result(s), then a final `AIMessage` with the answer
- **THEN** the DIAL response `message.content` SHALL contain the intermediate text followed by the final text, in that order, with a `"\n\n"` separator between them; tool stages SHALL still render between the two segments via the stage channel; the response content SHALL NOT contain serialized tool calls, tool result payloads, or `messages_to_dict` blobs

#### Scenario: Text-only turn (no tool calls)
- **WHEN** the agent answers without invoking any tool, producing a single text-only final `AIMessage`
- **THEN** the DIAL response `message.content` SHALL equal that message's text, with no leading or trailing separator, streamed token-by-token

#### Scenario: Structured content blocks flattened to text
- **WHEN** an `AIMessageChunk` carries `content` as a list of content blocks (e.g. `[{type: "text", text: "..."}, {type: "thinking", thinking: "..."}, {type: "image", ...}]`) instead of a bare string
- **THEN** the app SHALL append the concatenation of every `text`-typed block's `text` payload to `choice` and SHALL silently skip every non-text block (no append, no error, no stage)

#### Scenario: Cross-turn replay of tool messages
- **WHEN** a follow-up chat completion request arrives after an earlier tool-using turn
- **THEN** the second turn's agent SHALL receive the prior turn's intermediate `AIMessage(tool_calls=…, content=…)` and `ToolMessage(...)` slice plus the prior turn's final `AIMessage` as conversation history, reconstructed from the prior assistant message's `custom_content.state["messages"]` field, in the original order, instead of being limited to prior assistant text
