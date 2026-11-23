# Design

## Context

Every stage is created with `Choice.create_stage(title)` at the place that produces it. The debug
stages are created in eight places, and each one opens the stage, appends one body and closes it:

- `app/completion.py`: `_show_snapshot_stage` (both snapshot stages);
- `app/research/runner.py`: the tool result stage, the research-review stage, the research
  exhausted-budget stage, the report-review stage, the report exhausted-budget stage and the
  failed-revision stage;
- `app/preparation/runner.py` and `app/playground/runner.py`: the tool result stage.

The activity stage in `app/research/runner.py` (`_set_activity`) is opened and closed across
several steps, and stays as it is.

## Goals / Non-Goals

**Goals:**

- One place decides whether a debug stage is emitted.
- A debug stage added later is marked as one where it is created.

**Non-Goals:**

- Changing a turn's setting per request or per conversation.
- Changing what a debug stage carries when it is emitted.
- Changing logs or state. The facts a hidden stage carries stay in the log records the
  logging-policy spec already requires.

## Decisions

**An environment variable, not an application property.** `settings.py` gives the rule: what varies
per environment for the same client is an env field, what varies per client is an application
property. Whether debug stages are shown differs between a client's test and production
environments, so it is an env field: `show_debug_stages: bool = True`, read from
`SHOW_DEBUG_STAGES`.

**One function emits a debug stage.** `emit_debug_stage(choice=..., title=..., body=...)` in
`utils/dial_stages.py` opens the stage, appends the body and closes it, or returns without doing
anything when the setting is off. The eight places call it in place of their own `with
create_stage(...)` block. The alternative, a check at each place, repeats the condition eight times
and lets a new debug stage forget it.

**The stage body is still built when the stage is hidden.** Building it costs only string
formatting, and skipping it would need the condition back at every call site.

**Filtering in Deep Research, not in the client.** Deep Research is also used directly as its own
application, so a client that relays its stages cannot be the only place that hides them.

## Risks / Trade-offs

- [A client that relays Deep Research's stages hides them itself too] → That client has to relay all
  the stages it receives. This is a deployment note for the client, not a change here.
- [A failure recorded only in a debug stage, such as a failed blind review, is not visible to the
  user when debug stages are hidden] → The same failure is logged as a warning, as the
  report-composition spec already requires. User is not intended to see that message.

## Migration Plan

The default keeps today's behavior. An environment that should hide debug stages sets
`SHOW_DEBUG_STAGES=false` and restarts. Rollback is removing the variable.
