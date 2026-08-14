## Why

Research runs for minutes and tells the user nothing about what it is doing. Every DIAL stage the
app emits today is created *after* the thing it describes has already finished: the runner records
a pending tool call when the assistant message arrives and only creates the stage once the
`ToolMessage` comes back, so the stage opens and closes in the same instant. While an MCP tool is
running, and during each of the four LLM calls in the research graph, nothing new reaches the
client except the SDK's keep-alive. Two of those nodes — research-review and report — emit no stage
at any point.

The user should be able to see what research is working on right now. That means a stage that is
open while the work happens, not a record written once it is over.

## What Changes

- **A new `update_status` tool bound to research-agent.** The agent calls it when it starts a
  meaningfully new step, in the same assistant message as that step's first real tool call. The
  model decides when a step is new; the app does not infer it from iterations or plan items. The
  tool is app-owned and does no work — it returns an acknowledgement, like the existing
  `finish_iteration` sentinel.
- **One activity stage, open at all times, replaced rather than accumulated.** The runner opens the
  first one before the graph starts. Each announcement closes the current stage and opens a new one,
  so exactly one stage is open at every point in the run and it always names what is happening. The
  stage carries a title only: no body, no `[TOOL]`-style prefix, and no elapsed time.
- **The other graph nodes announce themselves on entry.** research-review, report and report-review
  each set the activity stage as their first action, through an emitter callback threaded into the
  graph — the same shape as the existing `emit_report_review_stage`. This removes the silence during
  those three LLM calls.
- **A closing stage does not mean the work finished.** A stage closes because a *new* step started.
  This is why no elapsed time is stamped on it, and why several announcements in one assistant
  message are merged into a single stage instead of leaving earlier ones to flash open and shut — a
  stage that instantly completes reads as a step that completed, which would be false.
- **Status calls are hidden from the models that read the transcript.** research-review and the
  report node stop receiving `update_status` calls and their tool responses, so status text never
  competes with genuine findings in a research-coverage judgement or in the report's context. The
  calls remain in the transcript persisted to `custom_content.state`.
- **Misuse is corrected, not prevented.** Calling `update_status` alone, or more than once in one
  message, is answered by a corrective note in the tool's response and a WARNING in the logs.
  Nothing blocks it; the consequences and the reason are recorded in design.md.

No new application property and no new environment variable.

## Capabilities

### New Capabilities

None. The change alters behavior already owned by existing specs.

### Modified Capabilities

- `dial-agent-with-mcp`: the requirement "Tool execution surfaced as timed DIAL stages" currently
  covers *every* tool the agent invokes. `update_status` becomes an exception — it produces no
  result stage — and a second stage kind is introduced, the activity stage, whose lifecycle differs
  from every stage the app emits today: it is opened before its outcome is known and closed when
  the next one replaces it.
- `research-execution`: the per-node LLM input and output contract changes in three places.
  research-agent gains a bound tool. research-review and the report node each stop receiving part
  of the transcript. Node entry becomes an observable event that three nodes must emit.
- `logging-policy`: status text is a tool-call argument value and so may never appear in a log
  record at any level. Two WARNING events are added for the two misuse cases, carrying counts only.

## Impact

Source:

- `src/dial_deep_research/app/research/tools.py` — the new `update_status` tool and its response
  constants, beside `build_finish_iteration_tool`.
- `src/dial_deep_research/app/research/runner.py` — the single open-stage slot, the replace helper,
  the `_handle_ai_message` rules, the misuse WARNINGs, and the `try/finally` that closes the stage
  on the failure path.
- `src/dial_deep_research/app/research/graph.py` — the activity emitter threaded alongside
  `emit_report_review_stage`.
- `src/dial_deep_research/app/research/nodes.py` — the entry announcements in research-review,
  report and report-review; the transcript filter and its two call sites, `_render_findings` and
  the report node's message list.
- `src/dial_deep_research/app/research/prompts.py` — the `update_status` section in
  `RESEARCH_AGENT_SYSTEM_PROMPT`, and the matching edit to its "You must always call a tool"
  section.

Tests: `tests/test_dial_stages.py` and a new module for the runner's stage lifecycle, following the
existing `_StageSpy` / `_ChoiceSpy` harness in `tests/test_preparation_streaming.py`.

Docs: `docs/architecture.md` — the research graph diagram and the loop invariants, including the
bullet that currently ends "Research review emits no stage."

No changes required, though they look adjacent:

- `src/dial_deep_research/app_properties.py` and `dial_conf/core/applications-template.json` — no
  new or changed application property.
- `README.md` — no new or changed environment variable.
- `src/dial_deep_research/utils/dial_stages.py` — the activity stage has no title decoration and no
  body, so there is nothing for a formatter to do.
- The report-review node's inputs — it reads no transcript, so it needs no filtering.
- `src/dial_deep_research/app/preparation/` — preparation already streams its text token by token
  and is not silent.
