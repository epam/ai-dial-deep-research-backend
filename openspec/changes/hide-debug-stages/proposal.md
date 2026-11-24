# Proposal

## Why

A research turn shows every stage the app emits: tool calls with their arguments and raw results,
research and report reviews, failed revisions and snapshot decisions. These stages help the people
who run Deep Research, but in a client's production environment they bury the few stages that tell
the user what is happening. Deep Research is also opened directly as its own application, so a
caller that relays its stages cannot be the only place that hides them. Hiding them by default
means a deployment that leaves the variable unset cannot show them to users.

## What Changes

- A new environment variable `SHOW_DEBUG_STAGES` (default `false`) decides, per deployment, whether
  the app emits debug stages. Debug stages are hidden unless a deployment sets it to `true`.
- The debug stages are: the tool result stages (`[TOOL] …`), the research-review stages
  (`[RESEARCH REVIEW RESULT] …`, the exhausted-budget one included), the report-review stages
  (`[REPORT REVIEW RESULT] …`, the delivered-without-review one included), the failed-revision stage
  (`[REPORT REVISION FAILED] …`) and the snapshot stages (`[DEBUG] …`).
- The activity stage, which says what the research is doing now, is not a debug stage and is always
  emitted. Assistant content, attachments, state and logs do not change.
- The snapshot stages lose the rule that they are always emitted.

## Capabilities

### New Capabilities

- `debug-stages`: which stages are debug stages, and the deployment setting that decides whether
  they are emitted.

### Modified Capabilities

- `research-resume`: the snapshot stages ("[DEBUG] reusing snapshot", "[DEBUG] existing snapshot
  discarded") are emitted only when the deployment shows debug stages.
- `dial-agent-with-mcp`: the `[TOOL]` result stages are emitted only when the deployment shows
  debug stages.
- `research-execution`: the research-review stage and the exhausted-budget stage are emitted only
  when the deployment shows debug stages.
- `report-composition`: the report-review stage, the unreviewed-delivery stage and the
  failed-revision stage are emitted only when the deployment shows debug stages. Their INFO
  records are written either way.

## Impact

- Code: `settings.py` (new field), `utils/dial_stages.py` (one function that emits a debug stage or
  skips it), and the places that emit debug stages: `app/completion.py`,
  `app/research/runner.py`, `app/preparation/runner.py`, `app/playground/runner.py`.
- Docs: README environment-variables table, `.env.example`, `docs/architecture.md`.
- Deployment: environments that should show debug stages, such as development and review
  environments, set `SHOW_DEBUG_STAGES=true`. A client that relays Deep Research's stages has to
  relay all of them, since the filtering happens in Deep Research.
