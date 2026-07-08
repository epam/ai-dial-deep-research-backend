## Context

DIAL persists chat history on behalf of applications, but its `Message` schema only round-trips the `user`, `assistant`, and `system` roles' `content` fields with high fidelity. `tool` role messages are not stored, and intermediate `assistant` turns within a single user-prompted tool loop are collapsed into a single final assistant message. The current `deep-research` MVP accepts this loss: the agent is rebuilt per request and the prior turns' tool calls / tool results are unavailable on the next turn.

`langchain.agents.create_agent` runs a ReAct-style loop (`agent → tools → agent → tools → … → agent_with_no_tool_calls`). For multi-step research turns the loop emits a sequence like `AI(call_X) → Tool(X_result) → AI(call_Y) → Tool(Y_result) → AI(final_text)`, where call_Y depends on X's result. Faithful replay on the next turn requires preserving the *full ordered slice*, not just the final text and not just a flat set of tool_calls (flattening loses the sequential vs parallel distinction and breaks Anthropic/OpenAI history requirements).

A proven pattern: each assistant turn carries a `custom_content.state` blob holding the intermediate slice as Pydantic-dumped LangChain messages, decoded back on the next turn with hand-rolled `if msg_type == 'ai': … elif 'tool': …` dispatch. We borrow the partitioning idea but use the native `messages_to_dict` / `messages_from_dict` helpers to get the type dispatch for free.

Constraints:
- DIAL is the persistence layer. No database-backed LangGraph checkpointer is in scope.
- `assistant.message.content` is what the DIAL chat UI renders, so it must remain the streamed final text — we cannot move the user-visible answer elsewhere.
- The agent in `agent.py` already streams text directly via `choice.append_content(...)`; the persistence buffer must coexist with that without forcing a re-architecture.

## Goals / Non-Goals

**Goals:**
- Preserve the full ordered intermediate `AIMessage(tool_calls=…)` / `ToolMessage(...)` slice across turns, plus the final `AIMessage`, with structurally faithful encoding.
- Reuse native LangChain serialization helpers; no custom Pydantic shape, no per-message-type if/elif decode ladder.
- Keep DIAL's chat UI rendering unchanged: the streamed final answer continues to live in `assistant.message.content`, tool stages continue to live in `custom_content.stages`.
- Preserve forward and backward compatibility: assistant messages produced before this change (no `custom_content.state["messages"]`) still reconstruct as a usable history (downgraded fidelity, same as today).

**Non-Goals:**
- Persisting non-text content blocks (images, citations, attachments) emitted by the model. Use case is plain-text research answers; if structured blocks ever appear they will be stringified for the DIAL UI and re-parsed faithfully on the LangChain side from the `custom_content.state` blob.
- Persisting reasoning text emitted *alongside* `tool_calls` in the same `AIMessage`. The current `agent.py` dispatch (`if msg.tool_calls: ... elif msg.content: ...`) drops such content from the user-visible stream and from the persistence buffer's content field. A separate spec will govern reasoning passthrough.
- Token-budget management for persisted history. Long multi-turn conversations will accumulate ever-growing tool message blobs; summarization / pruning is a future change.
- Migrating to a real LangGraph checkpointer (Postgres / Sqlite / Redis). Out of scope while DIAL is the persistence layer.
- Mutation/replay APIs (time-travel, branch, edit). DIAL's UI doesn't support them and we have no use case.

## Decisions

### D1. Where to stash the persisted message list — `custom_content.state` (chosen) vs DIAL native fields

DIAL native message fields (`content`, `tool_calls`, `tool_call_id`, `name`) are subject to whatever DIAL chooses to normalize, strip, or coerce on its way to/from storage. `custom_content.state` is opaque JSON: DIAL guarantees round-trip without inspecting the contents.

Stashing the entire intermediate-plus-final slice in `custom_content.state["messages"]` removes any reliance on DIAL preserving structured fields, which is the hardest part of the contract to defend against without DIAL-internal knowledge. The chat UI continues to render `message.content` (the final answer) as before.

Alternative considered: populate DIAL's native `assistant.tool_calls` for the final AI message and stash only `ToolMessage` results in custom_content. Rejected — it splits a logically single payload across two storage mechanisms with different fidelity guarantees, complicates reconstruction (need to merge native + state), and gains nothing compared to a single opaque blob.

### D2. What to store in the blob — full slice (chosen) vs intermediate-only with final-AI in DIAL body

The backend stores intermediate-only and reads the final `AIMessage` content from DIAL's native `message.content`. That works because the backend's content is plain text. We considered the same pattern, but chose to also include the final `AIMessage` in the blob.

Rationale:
1. **No coercion drift.** With the final AI in the blob, the model on the next turn sees exactly what it produced (structurally), regardless of how DIAL stored or re-serialized `message.content`. The DIAL body is then a pure UI-display projection (`str(msg.content)` is fine even if it's lossy for structured content blocks — see D5).
2. **Single source of truth.** Reconstruction is one branch per role (`USER` → `HumanMessage` from native; `ASSISTANT` → `messages_from_dict(state["messages"])`), no "stitch the final AI on the end" logic.
3. **No partitioning rule.** No need for a "buffer everything except the final AI" predicate; the agent dispatch buffers every `AIMessage` and every `ToolMessage` it sees, period.

The cost is one extra message in the persisted blob per turn. Negligible.

### D3. Encoding format — `messages_to_dict` / `messages_from_dict` (chosen) vs Pydantic `model_dump` + manual type dispatch

`langchain_core.messages.messages_to_dict` emits `[{"type": "ai" | "tool" | "human" | "system", "data": {...}}, …]` and `messages_from_dict` does the type-discriminated reconstruction. This is the public, stable, purpose-built API for serializing message lists.

Alternative considered: copy the backend's `model_dump(mode='json', exclude={'artifact'}, exclude_none=True)` + `if msg_type == 'ai': AIMessage.model_validate(...)` ladder. Rejected — it duplicates logic that LangChain already ships, requires an explicit branch per supported role, and creates a maintenance burden when `BaseMessage` subclasses gain new fields.

The backend's reason for hand-rolling — the `ToolArtifact` carve-out — does not apply here. dial-deep-research has no tool-artifact concept (yet), and `messages_to_dict` round-trips `tool_calls` (inside the `ai` entry) and `tool_call_id` (inside the `tool` entry) correctly.

### D4. DIAL native `tool_calls` field — leave unset (chosen) vs populate redundantly

Some DIAL clients populate `assistant.tool_calls` on the native message so any UI or downstream consumer that inspects it can see what tools fired. We chose not to: `custom_content.state["messages"]` already carries them, and adding them to a second location creates two sources of truth (and a duplication risk on reconstruction if the next-turn extractor accidentally reads both).

If a future requirement demands DIAL-native visibility (e.g., a non-LangChain consumer wants `tool_calls` without parsing `custom_content`), we can populate the native field then — purely additive, no reconstruction change.

### D5. Final-answer content stringification

The agent's `_handle_ai_message` writes `self._choice.append_content(str(msg.content))` for the final `AIMessage`. If the final content is a `list` of LangChain content blocks, `str(...)` produces the Python repr — broken for human display. This is acceptable for the use case (research answers are plain text) and the LangChain-side fidelity is preserved through `custom_content.state["messages"]`, so this drift only ever surfaces as a UI rendering issue, never as a model-input issue.

If/when the use case grows to include structured content (citations, attached charts), the UI projection logic gains a smarter renderer; the persistence path needs no change.

### D6. Legacy-message fallback

Assistant messages produced before this change have no `custom_content.state["messages"]`. The reconstruction routine emits `AIMessage(content=msg.content)` for them — same fidelity as today. This means existing conversations don't break and we don't need a migration step.

For mixed conversations (legacy turns followed by new turns), the LangChain history will be a mix of degraded (legacy) and faithful (new) messages — strictly better than the current state.

### D7. Where the buffer lives

`AgentRunner._messages: list[AIMessage | ToolMessage]` instance-scoped (already fits the existing per-request scoping pattern). Append in `_handle_ai_message` and `_handle_tool_message` unconditionally, after each branch's existing logic. Flush via `messages_to_dict` + `choice.set_state` once `astream` completes.

Alternative considered: pull the message list out of the LangGraph state via `agent.aget_state(config)` after the run. Rejected — `create_agent` does not expose a stable per-call state without a checkpointer, and the streaming dispatch already sees every message we need.

## Risks / Trade-offs

- **LangChain message format evolution** → persisted blobs from older releases may fail to deserialize after a major LC bump. Mitigation: pin `langchain-core`; if a future bump breaks the format, write a migration that walks DIAL's stored history and re-encodes.
- **Token budget growth** → every preserved tool result enters next-turn LLM context. Mitigation: explicitly out of scope here; future change can add per-turn summarization or selective drop based on age/depth. The MVP target is short conversations with a handful of turns, where unbounded growth is not yet a problem.
- **Stringification of structured final-AI content** → DIAL UI can render `str(list)` for a non-text final answer. Mitigation: accepted for now (use case is text); if it becomes user-visible, swap the stringifier for a content-block-aware renderer in a follow-up — no spec change to the persistence contract is needed.
- **DIAL `custom_content.state` size limits** → DIAL doesn't document an explicit cap, but server-side limits could exist. Mitigation: monitor in dev; if hit, the same summarization mitigation as the token budget concern applies.
- **Mixed-version reconstruction** → if a user has both legacy and new turns in the same conversation, the LangChain history will mix degraded `AIMessage(content=str)` with structured `AI(tool_calls)+Tool+AI(final)` slices. The model handles this fine (it's a strict superset of what it would have seen in the all-legacy case), so this is not a defect — just a transitional artifact that resolves itself as legacy turns scroll off.
