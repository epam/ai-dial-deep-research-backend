# Tasks

## 1. Setting

- [x] 1.1 Add `show_debug_stages: bool = True` to `Settings` in `settings.py`, with a comment saying
  what it hides, and add `SHOW_DEBUG_STAGES` to the README environment-variables table and to
  `.env.example`; verify `make lint` passes

## 2. Emitting debug stages

- [x] 2.1 Add `emit_debug_stage(choice=..., title=..., body=...)` to `utils/dial_stages.py`, which
  emits the stage only when `settings.show_debug_stages` is on; verify with a unit test for both
  values of the setting
- [x] 2.2 Use it for the snapshot stages in `app/completion.py`; verify the existing snapshot-stage
  tests pass and add one that resumes from a snapshot with the setting off and finds no snapshot
  stage
- [x] 2.3 Use it for the tool, research-review, research exhausted-budget, report-review, report
  exhausted-budget and failed-revision stages in `app/research/runner.py`; verify with a test that
  runs research with the setting off and finds only activity stages
- [x] 2.4 Use it for the tool result stage in `app/preparation/runner.py` and
  `app/playground/runner.py`; verify with a test per runner that a tool call with the setting off
  emits no stage

## 3. Checks

- [x] 3.1 Run `make format`, `make lint` and `make test`, and verify all pass
- [x] 3.2 Run `openspec validate hide-debug-stages --strict` and verify it passes

## Workflow follow-up

- Archive the change once it is merged.
