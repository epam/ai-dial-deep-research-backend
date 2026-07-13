## Context

The app runs a fresh LangChain `create_agent` ReAct agent per chat-completion request (`AgentRunner` in `app/agent.py`). The agent streams `updates` + `messages`; `AgentRunner` buffers every `AIMessage`/`ToolMessage` into `self._messages`, persists them to `choice.set_state` via `messages_to_dict`, and `history.reconstruct_history` replays that slice on the next turn. The agent stops the moment the model returns a tool-less `AIMessage`, so research depth is whatever the model decides on its first pass.

langchain 1.2.15 / langgraph 1.1.10 are installed. `AgentMiddleware` exposes an `after_model` hook; decorating it `@hook_config(can_jump_to=["model"])` and returning `{"jump_to": "model"}` re-enters the model node, which is the only control-flow primitive this change needs. An existing `PromptLoggingMiddleware` already demonstrates the middleware pattern in this repo.

Observed behavior we rely on: during research the model's `AIMessage`s always carry `tool_calls` (text+tool_calls or tool_calls only). A **tool-less `AIMessage` therefore marks a phase boundary**, never mid-research narration.

## Goals / Non-Goals

**Goals:**
- Force the model to self-review coverage and keep researching when gaps remain (repeatable `research → gap_check → research → …`).
- Cleanly separate research from a single, final report-generation step.
- Keep it thin: reuse the existing ReAct agent via middleware; add no new LangGraph nodes and no custom graph state.
- Preserve cross-turn replay: injected nudges round-trip through DIAL state so history reads `ai → human → ai`.
- Always terminate with a report, even at the safety cap.

**Non-Goals:**
- The full planner/researcher graph with separate states (a later experiment).
- Hiding or redirecting reflection turns from the visible chat (inline streaming kept as-is for now).
- Enforcing a token budget (a no-op stub is included for later).
- A dedicated report-generation node or structured-output report.

## Decisions

**1. Middleware + `jump_to` instead of a multi-node graph.** A single `after_model` hook inspects the message tail and either lets the agent end or injects a nudge and jumps back to the model. This keeps the existing ReAct agent and its tool loop untouched, where a planner/researcher graph would require new nodes, edges, and state. Trade-off: the "plan" stays as the model's own text in the conversation rather than structured state.

**2. Tool-less `AIMessage` = phase signal, enabled by deferring the report in the system prompt.** Rather than detect "is this answer good enough" semantically, we exploit the structural signal. The system prompt is changed so the model does **not** write the report until asked; its first tool-less message becomes a short "research complete" *signal*. Without this, the first tool-less message would be a full report and the gap-check would fire after it (double report). Alternative considered: gate the existing final answer (no prompt change) — rejected because it produces two full reports.

**3. Two distinct tagged nudges drive a message-derived state machine.** `gap_check` and `report_request` are injected as `HumanMessage`s with those `name` values. The discriminator is purely structural: if the previous `AIMessage` had tool_calls (research just happened) → `gap_check`; if the previous `AIMessage` was also tool-less (the model declined to research after a nudge) → `report_request`. Presence of a `report_request` in the turn is the exit signal (the next tool-less message *is* the report). Distinct tags (vs one tag + a counter) make both the discriminator and the exit trivial and stateless.

**4. Per-UI-turn scoping derived from messages, not custom state.** Each request is a fresh `graph.invoke` whose input is the full reconstructed history — which includes prior turns' tagged nudges. So all checks are scoped to the slice after the **last real (untagged) user message**: `HumanMessage` whose `name ∉ {gap_check, report_request}`. This avoids a custom `state_schema` counter and is robust across multi-turn conversations (a prior turn's trailing tool-less answer can't trigger a spurious exit).

**5. The cap counts reflections and forces a report.** The cap counts `gap_check` nudges already injected this turn (not all AI turns — matching the `MAX_REFLECTIONS` name). At the cap we inject `report_request` rather than bare-exit, because the deferred-report prompt means a bare exit would leave the user with only a "research complete" signal and no report. The cap is a configurable app setting (`AgentSettings.max_reflections`, env var `MAX_REFLECTIONS`, default 10, `ge=1`), passed into `ReflectionMiddleware(max_reflections=...)` as a constructor arg so tests can inject a small value. It lives in a new `AgentSettings` class rather than `DialAppSettings` because it is an agent-behavior knob and is the natural home for the future token-budget setting; no field alias is added (field name maps to the env var directly). A future per-turn token budget slots in via the `_token_budget_exhausted(state) -> False` stub.

**6. Capture injected nudges into the persistence buffer + guard `None` node updates.** A returning-`None` `after_model` emits a `None` value on the `updates` stream, which would crash `run()`'s existing `node_update.get(...)`; we guard with `isinstance(node_update, dict)`. Injected `HumanMessage`s surface on the `updates` stream (node key `ReflectionMiddleware.after_model`) and must be appended to `self._messages` so they persist and reconstruct as `ai → human → ai`. They stream no tokens, so nothing reaches visible content; we set `_separator_pending` so the next AI text segment is paragraph-separated.

**7. Persist the nudges (deliberate, with a known exit).** We keep the injected nudges in the persisted slice so reconstruction yields a clean `ai → human → ai` alternation. The cost is that every subsequent turn replays a past turn's internal scaffolding into context (pure overhead, growing with conversation length). This is accepted on purpose: the expected future direction is to either (a) replace this thin middleware with a different architecture and discard it, or (b) move to an all-`AIMessage` loop with no fake-human nudges. Either way, persisting the nudges now is the simplest correct choice and is cheap to undo.

## Risks / Trade-offs

- **Model writes the report before being asked (ignores the deferral)** → double/premature report. *Mitigation:* this is fundamentally an LLM-compliance dependency — the structural phase machine cannot force semantics, so the **system prompt is the primary control** and must be tuned (and smoke-tested) against the deployed model. The cap + report-present exit still bound termination; inline double-text is the already-accepted streaming trade-off.
- **Model emits a standalone tool-less message mid-research (violates the core assumption)** → a premature `gap_check`. *Mitigation:* relies on observed gpt-5-class behavior; worst case wastes one reflection and the cap bounds it. The completion instruction is phrased softly to reinforce the contract — e.g. "if you think you are done, do not emit tool calls; wait for the user to ask for the report" — so a tool-less message reads as a deliberate completion signal rather than mid-research narration.
- **Model keeps calling tools after every `gap_check` and never confirms** → no natural convergence. *Mitigation:* `gap_check` instructs "if complete, do not call tools, just confirm"; `MAX_REFLECTIONS` forces the report.
- **Reflection tool-rounds inflate latency / hit langgraph's `recursion_limit`** within a single research phase. *Mitigation:* the reflection cap is independent of langgraph's per-invoke recursion limit; tune the latter if deep research needs more tool steps.
- **Inline streaming shows the "research complete" signal(s) + report concatenated.** *Accepted, deferred* — a later change may route reflection turns into DIAL stages.

## Migration Plan

No data migration. Legacy persisted turns contain no tagged nudges, so reconstruction is unaffected (untagged `HumanMessage`s remain real user turns). Rollback is removing `ReflectionMiddleware()` from the `create_agent` middleware list and reverting the prompt; the `None`-update guard and `_handle_human_message` are harmless if left in place.

## Open Questions

- Is one `gap_check` challenge per research phase the right cadence, or should the prompt encourage the model to batch multiple gap dimensions per nudge? (Deferred; the loop already supports many rounds.)
