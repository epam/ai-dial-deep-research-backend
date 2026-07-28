## 1. Setting

- [x] 1.1 Add `max_context_images: int = 50` (with `ge=1`) to `Settings` in
  `src/dial_deep_research/settings.py`, documented as the provider per-request image limit
- [x] 1.2 Add the `MAX_CONTEXT_IMAGES` row to the README environment-variables table
  (optional, default 50)

## 2. Middleware

- [x] 2.1 Implement `ImageBudgetMiddleware` in
  `src/dial_deep_research/app/middleware.py` (shared module): an agent-middleware
  `before_model` hook that counts image blocks in state, walks this round's tool messages
  newest → oldest substituting image-carrying ones (same id, `tool_call_id`, `name`,
  `status="error"`) while the cumulative count exceeds the budget, and returns the
  substitutions as a `{"messages": [...]}` state update (no update when within budget)
- [x] 2.2 Render the error-message templates from design.md: per-step math on every
  dropped message; remaining-allowance (or budget-fully-used) instruction only on the
  terminal drop
- [x] 2.3 Log the clamp at INFO following the logging policy (counts and totals only, no
  content)
- [x] 2.3a Skip (with a WARNING) any image tool message that has no id — `add_messages` would
  append the substitute beside the original instead of replacing it, keeping the images
- [x] 2.4 Register the middleware on the researcher agent in
  `src/dial_deep_research/app/research/nodes.py`
- [x] 2.5 Register the middleware on the playground agent in
  `src/dial_deep_research/app/playground/agent.py` (its MCP tools can return images)

## 2b. Persisted slice

- [x] 2b.1 In `src/dial_deep_research/app/research/runner.py`, stream `values` alongside
  `updates`/`messages` with `version="v2"` and assign the slice to persist from the last
  root-namespace `values` part, replacing the append-and-dedupe collection
- [x] 2b.2 Drop the now-dead `_unpack` helper, the `self._messages.append` calls, and the
  persistence-only `HumanMessage` branch; keep `_already_seen` for the live output

## 3. Prompt

- [x] 3.1 Add one sentence to `RESEARCHER_SYSTEM_PROMPT` in
  `src/dial_deep_research/app/research/prompts.py` disclosing the image budget and that
  overflowing image results are dropped with an explanatory tool error

## 4. Tests

- [x] 4.1 Unit-test the clamp walk: no-op within budget; single overflow; the `[a, b]`
  parallel-batch example (base 49, +4 then +1, budget 50) producing the exact step math
  49→53 and 53→54; terminal-drop allowance on the right message; budget-exactly-used
  variant; multi-image messages; defensive full-batch drop
- [x] 4.2 Test substitution mechanics: same message id replaces (not appends) in state via
  `create_agent` + `before_model` with a scripted fake model, preserved `tool_call_id`,
  `status="error"`
- [x] 4.3 Test tool-agnosticism: messages from arbitrary tool names are counted and
  substituted purely by image content
- [x] 4.3a Test the id-less skip: no update, a WARNING for the skip and for the resulting
  shortfall, and the walk still reaching an older substitutable message
- [x] 4.3b Test the persisted slice in `tests/test_research_dispatch.py`: the last root
  `values` part wins, subgraph `values` are ignored, and a substituted message reaches the
  slice even though `updates` only ever showed the original
- [x] 4.3c Test that a substituted result adds no DIAL stage and leaves the rendered one
  showing the original tool output
- [x] 4.4 Test budget override: small `max_context_images` value drives enforcement

## 5. Verify

- [x] 5.1 Run `make format` and `make lint`
- [x] 5.2 Run the test suite
