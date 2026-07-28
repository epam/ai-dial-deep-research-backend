## Context

Issue #25: the models we currently use reject any request carrying more than 50 images.
That matches Azure OpenAI's documented limit — "GPT-4o and GPT-4.1 maximum images per
request (number of images in the messages array or conversation history): 50" — alongside
a 20 MB per-input-image size limit. The doc row names only GPT-4o / GPT-4.1 and lags the
model lineup: we run newer model families and observe the same 50 there. OpenAI's own API
is far more permissive (up to 1500 image inputs and 512 MB total payload per request), so
the 50 is platform-specific, and both docs note limits may change over time. Doc URLs are
cited in the image-budget spec. Two call sites can exceed it: every researcher model call
(the `create_agent` history accumulates image tool results across the turn's iterations) and
the report node (it sends the full `state["messages"]` transcript). The reviewer is safe — it
renders findings as text.

Images accumulate within one turn only, never across turns. The research graph starts from
`build_initial_state(prep_state)`, not from the reconstructed history; once `research_started`
is set, the next turn is rejected outright (`ResearchAlreadyHandedOffError` in
`app/completion.py`), so a research transcript is never fed back into an agent. The
preparation agent does receive the reconstructed history, but it has no MCP tools and never
runs on a post-research turn. The playground is stateless — it rebuilds history from visible
text alone (`app/playground/runner.py`) — so its images accumulate only across the tool rounds
of a single turn.

The design was settled in discussion (issue #25 conversation) and validated by an
experiment: returning a `ToolMessage` with the same `id` from an agent-middleware
`before_model` hook replaces the original message in state (the `add_messages` reducer
replaces by id) — confirmed end-to-end with `create_agent` on langchain 1.3.12.

## Goals / Non-Goals

**Goals:**
- No LLM request ever carries more than the budgeted number of image blocks.
- Enforcement is tool-agnostic: works for any current or future image-returning MCP tool,
  with zero per-tool configuration.
- The agent is told precisely what was dropped and how many image slots remain, so it can
  adapt (re-fetch less, or switch to text).
- The budget is a spec-level invariant that future architecture changes must respect.

**Non-Goals:**
- No intent-based gating of tool calls before execution (would require configuring tool
  names/argument patterns per deployment; content-based checking observes what actually
  came back).
- No message splitting: whole tool messages are substituted, never individual image
  blocks within a message.
- No optimal drop-set selection; the walk is a simple newest-to-oldest pass.

## Decisions

### Enforce in the agent-middleware `before_model` hook, mutating state

`before_model` is a hook on langchain's `AgentMiddleware`, so it exists only on
`create_agent` agents; the middleware is registered on every agent whose tools may return
images — the researcher and the playground (the preparation agent has no MCP tools, so it
carries no images by construction). Plain LLM calls — the reviewer and report nodes — have
no middleware (chain/LLM callbacks such as `on_chat_model_start` are a different
mechanism). They stay within budget indirectly: the reviewer renders findings as text,
with no images at all; the report node sends `state["messages"]` — the exact history the
researcher's hook keeps at ≤ budget images — so it carries ≤ budget images too. That is an
assumption about the current architecture, not a guarantee: if a future architecture gives
some LLM call a history the researcher hook never clamped (e.g. the main research agent no
longer sees all tool outputs, but the report generator consumes them raw), that call needs
its own enforcement to satisfy the image-budget spec invariant.

The hook fires before every researcher model call, after an entire parallel tool
batch has landed in state (`ToolNode` gathers results and appends them in `tool_calls`
order as one update), so there is no per-call race. Substituting via a state update (same
message id) makes the fix stick for the rest of the turn: later researcher calls and the
report node (which does not pass through researcher middleware) both inherit the clamped
history, and so does the slice persisted into `custom_content.state` — see the next
decision.

Alternatives rejected:
- `awrap_tool_call` (before or after execution): each wrapper sees only its own call;
  parallel siblings cannot see each other's results, so the budget can overshoot.
- `awrap_model_call`: same visibility, but edits only the outgoing request copy — the
  rewrite would need recomputing on every call, and the report node would need its own.

### Persist the graph's final state, not the collected stream updates

`ResearchRunner` used to build the slice it persists by appending every message it saw on
the stream, deduped by id (`_already_seen`) because the same message arrives from both the
subgraph and the parent aggregate. A substitution reuses the original's id on purpose, so
that dedupe skipped it and the persisted slice kept the image-carrying original — the
images were uploaded to DIAL files and stored in `custom_content.state`, even though no LLM
request ever carried them.

The runner now streams `values` alongside `updates` and assigns the slice from the last
root-namespace `values` part: the graph's final state, where `add_messages` has already
applied every in-place edit. The two modes get distinct jobs — `updates` and `messages`
drive the live DIAL output (they arrive from inside the subgraph, well before the parent
re-emits them, which is what keeps stages live), `values` supplies what gets persisted.
`_already_seen` stays, for the live output only.

Collecting root-namespace `updates` instead was rejected: a compiled subgraph used as a node
returns its *entire* state, not a delta, so the researcher's update re-emits every earlier
message on each iteration. That needs id-based dedupe again — the mechanism that caused the
bug.

The stream uses `version="v2"`, which gives every part the same `{type, ns, data}` shape
regardless of mode count or subgraphs, so the runner no longer normalises 2- and 3-tuples by
hand.

### Count content, not intent

The middleware counts `{type: "image"}` blocks in message content. It never inspects tool
names or arguments, so it needs no configuration and covers any image-returning tool.
The cost: an overflowing image is fetched and then dropped (one wasted MCP call around
the moment the budget fills). Acceptable for a guard.

### Bottom-up walk with per-step math

Walk this round's tool messages newest → oldest with a cumulative count starting at the
landed total; substitute each image-carrying message while the count exceeds the budget,
subtracting its images as it drops. A `for` loop over the round's tool messages (with a
"within budget" break) guarantees termination even in impossible-by-design states.
Messages older than the current round are never touched in normal operation: each pass
leaves state within budget, so the next overflow is always resolvable from the new batch
alone — the model never sees an image that later vanishes, and the untouched prefix keeps
the provider prompt cache warm.

Per-step math gives each substituted message truthful numbers ("brought the conversation
from X to Y"); at most one message per pass — the one whose drop lands within budget —
carries the remaining-allowance instruction (`limit − (cum − N)` is known inline in that
iteration). Greedy keep-what-fits was considered and rejected as needless subtlety.

### Error-message templates

- Regular dropped message:
  `Tool result dropped: it contained {N} image(s), which brought the conversation from
  {X} to {Y} images, exceeding the budget of {limit}.`
- Terminal drop, slots remain:
  same + ` {K} image slot(s) remain — fetch at most {K} more image(s).`
- Terminal drop, budget exactly used:
  same + ` The image budget is fully used — do not fetch more images.`

Substituted messages keep the original `id`, `tool_call_id`, and `name`, and set
`status="error"`. The `id` is what makes it a substitution: `add_messages` assigns a fresh id
to any message that lacks one, so an id-less original would keep its images and gain an error
message beside them. Such a message is therefore skipped with a WARNING rather than
substituted, and the post-walk shortfall warning reports what stayed. Messages that reach the
hook through the reducer always carry an id, so this is a guard, not a path we expect.

### Budget lives in `settings.py`

The limit comes from the LLM provider platform (the 50 default matches the OpenAI models
currently in use), not per-client deployment config, so it is an env field
(`max_context_images: int = 50` → `MAX_CONTEXT_IMAGES`), not an application property. Tests
override it with a small value instead of building 51-image fixtures.

## Risks / Trade-offs

- [Agent keeps trying image fetches after exhaustion] → the terminal message says "do not
  fetch more images" and the researcher system prompt discloses the budget; if looping is
  still observed, an intent-based pre-execution gate can be added later as an
  optimization.
- [A single tool message mixing text and images loses its text when substituted] →
  acceptable; the error text tells the agent the result was dropped, and it can re-fetch
  as text.
- [Bottom-up can over-drop: a small result that would individually fit is dropped because
  it sits above a large one] → accepted for simplicity; the remaining-allowance message
  tells the agent how many images it may re-fetch.
- [The user cannot tell that a page image was dropped] → the DIAL stage shows what the tool
  returned and the substitution is invisible there; only the model is told. Accepted for now
  (the budget is a model-context concern), and reversible — surfacing it means rendering the
  substituted message instead of skipping it as an already-seen id.
- [The persisted slice now depends on `values` parts arriving] → if a future change drops
  `values` from the stream modes or the root-namespace check, the runner silently persists
  an empty slice rather than a stale one. Covered by tests on `_handle_part`.
- [Provider limit changes] → single setting to adjust.
