## Why

Research runs that fetch many page images fail hard: the LLM provider rejects any request
carrying more than 50 images (`openai.BadRequestError: Too many images in request: 51,
maximum allowed: 50.`), aborting the whole turn (issue #25). The researcher accumulates
image tool results across iterations and turns, so long runs inevitably cross the limit.

## What Changes

- Add a conversation-wide image budget (default 50, env-overridable) enforced by a new
  shared agent middleware, registered on every agent whose tools may return images
  (the researcher and the playground).
- Before every model call of such an agent, the middleware counts image blocks in the agent
  state; while the total exceeds the budget, it substitutes the newest image-carrying
  tool messages with error tool messages explaining the drop, walking newest → oldest.
- Each substituted message states the drop math (its image count, the running totals);
  the message whose drop brings the total back under the budget also states how many
  image slots remain (or that the budget is fully used).
- The substitution is a state update (same message id), so later researcher calls in the
  turn and the report node inherit the clamped history.
- `ResearchRunner` takes the slice it persists from the graph's final state (the last root
  `values` stream part) instead of accumulating stream updates, so in-place substitutions
  reach `custom_content.state` too. Stream parts move to `version="v2"` for a uniform shape.
- Add one sentence to the researcher system prompt introducing the image budget.
- Tool-agnostic by design: no tool names or argument patterns are configured; only
  returned image content is counted.

## Capabilities

### New Capabilities

- `image-budget`: bound the number of image blocks any LLM request may carry, so requests
  never exceed the provider's per-request image limit; define how overflowing tool results
  are substituted and how the agent is informed.

### Modified Capabilities

<!-- none — researcher/reviewer/report behavior at the requirement level is unchanged;
     the budget is a new cross-cutting invariant -->

## Impact

- `src/dial_deep_research/app/middleware.py` — new shared middleware module.
- `src/dial_deep_research/app/research/nodes.py`, `src/dial_deep_research/app/playground/agent.py`
  — register the middleware on the researcher and playground agents.
- `src/dial_deep_research/app/research/prompts.py` — researcher prompt line about the
  budget.
- `src/dial_deep_research/app/research/runner.py` — persist the graph's final state instead
  of accumulated stream updates; adopt the `version="v2"` stream-part shape.
- `src/dial_deep_research/settings.py` + README env table — new `max_context_images`
  setting (`MAX_CONTEXT_IMAGES`, default 50).
- Tests for the clamp walk, message rendering, and the persistence of substitutions.
