## Context

See proposal.md — Why, for the motivation.

Three properties of the code as it stands shape everything below.

**Every stage today is written after the fact.** `ResearchRunner._handle_ai_message` records a
`PendingToolCall` when the assistant message arrives, and `_handle_tool_message` creates the stage
only once the `ToolMessage` comes back. Each stage therefore opens and closes inside a single `with`
block. `utils/dial_stages.py` holds formatters and deliberately no context managers, for the reason
recorded in `openspec/changes/archive/2026-04-29-add-deep-research/design.md:101`: there was never an
open→close window for one to wrap. This change introduces the first stage that outlives the code
creating it.

**The research tools are not the app's.** `load_mcp_tools` fetches them from the configured MCP
servers, filters, sorts them by name for a byte-stable tool array, and normalizes their schemas. The
app owns only `finish_iteration`, appended in `ResearchRunner.run`.

**Every research-agent step must be a tool call.** `ForceToolChoiceMiddleware` re-issues each model
call with `tool_choice="any"`, so the agent can never emit free text. A status therefore has to be a
tool call; it cannot be a message the model writes.

### Behavior confirmed before designing on it

- An open DIAL stage shows a spinner in the client until it is closed. Confirmed in the client.
  The single-open-stage shape depends on this; were it false, closing each stage immediately would
  be the better design.
- A stage closed with the failed status renders an icon of its own, neither a spinner nor a
  completed mark. Confirmed in the client on a turn that failed mid-research: the spinner stopped
  and the failure icon took its place. The `except` branch that closes the activity stage is
  therefore visible to the user as a failure, not merely as motion stopping.
- A slow stream consumer pauses graph execution. Measured with a two-node LangGraph probe and a
  50 ms sleep in the consumer: the observed order was `node a enter → consumed a → node b enter →
  consumed b`. Node entry therefore cannot overtake the runner's processing of earlier updates, so a
  node-emitted stage and a runner-emitted stage cannot arrive out of order.
- The report-review node reads no transcript (`app/research/nodes.py:355-372`), so it needs no
  filtering. Only two call sites consume `state["messages"]`: `_render_findings` at `nodes.py:163`
  and the report node at `nodes.py:274`.
- A DIAL stage name can be appended to but never rewritten — the SDK merges name deltas by string
  concatenation (`aidial_sdk/utils/merge_chunks.py`, `merge_str`). Changing what a stage says
  therefore requires a new stage.
- The SDK offers only two terminal stage statuses, `completed` and `failed`. There is no neutral
  one.

## Goals / Non-Goals

**Goals:**

- One stage open at every moment of the research run, naming what is happening.
- The model decides when a step is new; the app decides how that renders.
- No stage state can survive the turn, on either the success or the failure path.
- Nothing the model says for the user's benefit reaches a model that judges research or writes the
  report.

**Non-Goals:**

- Accurate plan progress. A stage closes when the next starts, not when its work ends. See
  Risks.
- Any timing guarantee on how often a status refreshes. It would need a timer, a separate mechanism
  from a model-driven announcement. The SDK heartbeat already keeps the SSE connection alive, so
  this is a user-experience question, not a connection one.
- A research planning component. Statuses are not plan items and are not derived from them.
- Preparation. It already streams its text token by token (`app/preparation/runner.py:164`) and is
  not silent.

## Decisions

### The model announces through a tool, rather than the app inferring steps

*Alternatives rejected.* **Piggybacking a `status` argument onto the research tools** — the app does
not own those schemas. It would have to wrap every MCP tool to inject the argument and strip it
before dispatch, a permanent transformation layer over someone else's contract, and it would still
produce one status per tool call rather than one per step, which is the wrong granularity: the same
step often spans several calls. **Deriving statuses from iteration boundaries or plan items** — the
proposal's non-goals rule both out; a step is not an iteration and not a plan item, and research may
work on several plan items at once.

### Announcements ride along with a real tool call

The prompt asks the model to call `update_status` in the same assistant message as the first real
tool call of the step it announces. The runner already iterates every call in a message, so both
execute in one super-step and the status costs no extra model round trip.

*Alternative rejected.* **Letting the model call `update_status` on its own turn** — every status
would then cost a full model round trip, in latency and tokens. It remains possible, and is
answered rather than blocked; see "Misuse is corrected, not prevented".

### The runner emits the stage; the tool never touches DIAL

The tool returns a string and does nothing else. The runner sees the call on the graph stream and
manages the stage, which keeps DIAL out of the graph and puts the emission at the choke point that
already turns tool calls into stages — the place that can see the whole `msg.tool_calls` batch and
so apply the `finish_iteration` rule and the join rule.

*Alternative rejected.* **The tool emitting its own stage through an injected callback**, the shape
`emit_report_review_stage` uses. It would work: a tool can read the assistant message carrying its
own call via `InjectedState`, so batch visibility is not the discriminator it first appears to be.
It is rejected for coupling the graph to DIAL and splitting stage emission across two owners.

### One stage, replaced, never accumulated or re-titled

Exactly one activity stage is open at a time. The runner opens the first before the graph runs, and
every announcement — from the tool or from a node entry — closes the current one and opens the next.
A single slot means there is never a silent window: during research-agent's first model call the
user still sees the stage research-review opened, which is briefly stale and self-corrects.

*Alternatives rejected.* **Several stages open at once**, one per concurrent line of work — it
multiplies spinners for a feature whose promise is awareness, and the same information fits in one
title. **Re-titling one long-lived stage** — impossible: `append_name` concatenates, so a name can
only grow. **A `before_agent` middleware emitting a placeholder** so research-agent's first call is
never silent — unnecessary once the single slot guarantees a stage is always open; the runner's
opening stage covers the one genuinely uncovered moment, the start of the run, in one line instead
of a middleware class.

### One assistant message changes the stage at most once

Several `update_status` calls in one message are joined into a single title.

*Alternative rejected.* **Applying them in sequence**, which needs no code at all — each would close
the previous, so all but the last would render as *completed steps*. That is the same false
impression this design refuses to create by omitting durations, so the marginally simpler code is
not worth it. **Taking only the first and discarding the rest** discards something the model said.

### The activity stage carries no elapsed time, no body, and no prefix

*Alternatives rejected.* **Stamping the duration on close**, as `timed_stage_title` does for tool
stages and as the sibling `generic-rag` repo does — the stage closes because a *new* step started,
so a duration would assert a completion that did not happen. **A `[STATUS]` prefix matching `[TOOL]`
and `[REPORT REVIEW]`** — those label finished records in a growing list; this is the live line, and
the prefix spends scarce width on a label that carries no information. **A body explaining the
step** — more tokens per announcement and more room for the model to narrate instead of research.

Because the title is the model's text unchanged and there is no body, no formatter is added to
`utils/dial_stages.py`; a pass-through class would be structure without work.

### Node entries announce through an injected emitter

research-review, report and report-review call an emitter as their first action, threaded through
`build_research_graph` beside `emit_report_review_stage` — the node decides what to report, the
runner holds the `Choice` and decides how it renders.

*Alternative rejected.* **Reading node entry off the graph stream** — with `stream_mode="updates"`
an update arrives when a node *finishes*, so there is no entry signal to read. Inferring the next
node from the routing the runner observes would duplicate the routers in `nodes.py:423-495`.

### Statuses are hidden from research-review and the report node

Removed from the messages those two calls receive; kept in the transcript persisted to
`custom_content.state`, so the DIAL state stays a faithful record.

The filter strips a single tool call out of an assistant message rather than dropping the message,
because the common case is a mixed message: the status rides with real tool calls, and dropping it
whole would discard research. Its matching `ToolMessage` goes with it, so every remaining call stays
paired with its result. Being deterministic, the filter preserves the byte prefix successive calls
share (see **prompt-caching**).

*Alternative rejected.* **Leaving them in** — research-review would weigh
`SEARCHED: update_status(...)` among genuine retrievals when judging coverage, and every status
would sit in the report's context and in each revision's.

### Misuse is corrected, not prevented

Calling `update_status` alone, or more than once in a message, is answered by a note appended to the
tool's acknowledgement, plus a WARNING logged by the runner. Nothing blocks it. The tool detects
both by reading its own assistant message through `InjectedState`.

The runner owns the WARNINGs because it sees each message once and so logs once; the tool runs per
call and would repeat itself. Rules stated in the prompt, in the tool description and in the
corrective notes are built from shared constants, so three copies cannot drift.

*Alternative rejected.* **A `before_model` middleware substituting the `ToolMessage` by id**, the
pattern `ImageBudgetMiddleware` uses at `app/middleware.py:22-124`. It works and is the fallback if
`InjectedState` does not carry the current assistant message, but it is a class where a parameter
suffices. **Blocking the call outright** is not possible: `tool_choice="any"` means the model must
call something, and refusing to answer a tool call is not in the protocol.

### The word ceiling is instructed, not enforced

*Alternative rejected.* **Truncating server-side** — a title cut mid-phrase reads worse than a long
one wrapping, and the ceiling is a display preference, not a correctness bound. This also covers the
joined title, which may exceed the ceiling.

### The stage lifecycle is managed by hand, inside `try/finally`

No `with` block. The SDK's `Stage.__exit__` calls `close()` unconditionally on the exception path,
and closing an already-closed stage raises `RuntimeServerError` — which would replace the real
exception with a misleading one. The runner opens and closes directly and tracks its own flag, and
`ResearchRunner.run` closes the open stage as failed before the exception reaches `raise_dial_error`.

## Risks / Trade-offs

- **A status-only loop kills the turn.** `tool_choice="any"` forces a tool call every step, and
  `update_status` is always valid and costs no thought, so an uncertain model has somewhere to go
  that looks like progress. Repeated status-only messages consume super-steps, and exceeding
  `max_research_graph_steps` "raises GraphRecursionError and the turn fails with an error"
  (`app_properties.py:253`) — a dead turn, not a degraded answer. → The default of 500 makes this a
  tail risk; the prompt forbids it, the tool's response corrects it, and the WARNING makes it
  diagnosable if it appears in practice.
- **A closing stage reads as a finished step.** The SDK has no neutral terminal status, so a closed
  stage shows a checkmark. → Accepted: a checkmark is a loose UI affordance where a stamped duration
  would be a specific false claim. Recorded in the spec so it is not later mistaken for a bug.
- **A stale status can sit on screen indefinitely.** Nothing bounds the gap between announcements.
  → Out of scope by decision; revisit only if it proves to matter.
- **The dedupe guard's failure mode gets worse.** `_already_seen` keys on `msg.id or f"{id(msg)}"`;
  an id-less message arriving from both the subgraph and the parent is two distinct objects and
  slips through. Today that costs a duplicate `PendingToolCall`, which is nearly harmless. Once
  `_handle_ai_message` emits stages, the same miss closes a stage that just opened. → Not a new
  weakness, only a costlier one; a single live run against a running server shows it immediately.
- **A joined title can be long.** Deliberately not truncated; it wraps.

## Open Questions

None outstanding.

**Resolved:** a tool's `InjectedState` does include the assistant message carrying that tool's own
call, with its full `tool_calls` list. Measured with a `create_agent` graph whose model emitted one
message calling `update_status` and a second tool: the injected state's last message was that
`AIMessage`, listing both calls. Misuse detection therefore lives in the tool, and the `before_model`
substitution fallback is not needed.
