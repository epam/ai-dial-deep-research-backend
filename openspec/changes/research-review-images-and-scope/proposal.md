## Why

Research-review can loop forever on work that is already done or can never be done. It renders
every image-carrying tool result as a bare `[+image]` marker, so a fact that only exists in a
chart or table image looks uncovered to it — it keeps asking research-agent to re-fetch a page
whose image research-agent already has. It also judges the raw query and plan as given, so a
user's report-format request ("answer in two sentences", "use a table") becomes a plan item it
expects evidence for, and forced tool choice means research-agent can never write that answer —
research-review then asks for "the final answer" as a next step forever, because no report exists
yet to satisfy it (see issues #29 and #45).

## What Changes

- research-review's human message includes the actual image content blocks from the tool results
  it renders, instead of a `[+image]` marker — the same images research-agent already has, still
  bounded by the existing image budget (no new limit is introduced).
- research-review's system prompt states that a pure format request (tone, length, "keep it
  brief") is out of its scope: it never lists a next step whose purpose is to satisfy one. A
  format request that names real data (e.g. "compare X and Y in a table") still drives an
  ordinary next step for the missing data — only the presentation itself is out of scope.
- research-review's system prompt states that no report exists at review time — research-agent
  never writes prose — so it must never ask for "the final answer", a summary, or a specific
  presentation as a next step, and must never judge whether one would honor a format request.
- report-review's checklist gains a sixth check: when the query or plan asks for a report
  property that doesn't conflict with its other checks, it verifies the draft honors it, so a
  user's format request is actually enforced somewhere, not just kept out of research-review's
  scope.

## Capabilities

### Modified Capabilities

- `research-execution`: the research-review LLM call's inputs (images are now included, not
  omitted) and its judged scope (evidence coverage only, never report format or report content)
  are call-contract and reviewer-scope requirements this spec owns.
- `report-composition`: report-review's checklist requirement gains the sixth, user-specified-
  format check.

## Impact

- `src/dial_deep_research/app/research/nodes.py`: `_render_findings` renders image blocks
  alongside their tool result's text instead of a marker.
- `src/dial_deep_research/app/research/prompts.py`: `RESEARCH_REVIEW_SYSTEM_PROMPT` gains the
  scope and no-report-yet rules; `RESEARCH_REVIEW_HUMAN_MESSAGE` splits so real image blocks can
  sit between its rendered-text pieces; `REPORT_REVIEW_SYSTEM_PROMPT` gains the sixth check.
- `tests/test_status_filtering.py`, `tests/test_research_review_stage.py`,
  `tests/test_report_loop.py`: updated for the new findings shape and the new check.
- `openspec/specs/research-execution/spec.md`: the research-review call-contract requirement and
  its "judges coverage without the images" scenario.
- `openspec/specs/report-composition/spec.md`: the report-review checklist requirement.
