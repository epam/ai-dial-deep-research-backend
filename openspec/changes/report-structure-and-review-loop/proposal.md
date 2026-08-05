## Why

Reports are delivered as free-form Markdown with no defined structure and no length ceiling
(issue #32). The only guidance the report node has today is a paragraph of generic advice
("scope → primary analysis → cross-cutting synthesis → conclusion → sources"), so shape varies
run to run and length is unbounded. Nothing removes meta-annotations the model likes to add
(confidence scores, complexity ratings, elapsed times), and on the turn that launches research
the answer is not the report alone: the preparation agent's closing sentence ("research is
starting") is streamed into the same assistant message ahead of it.

A word ceiling cannot be met by prompting alone — a model asked for "at most 2,750 words"
misses by a wide margin, and a `max_tokens` cap would truncate mid-sentence, which issue #32
explicitly forbids. So the ceiling is enforced by reviewing the finished report and revising
it, with the measured word count fed back as a number.

## Acceptance criteria

From issue #32, quoted so the artifacts can refer to them without the issue open. Where a
criterion is deferred, the reason is in design.md — Non-Goals.

| # | Criterion | This change |
|---|-----------|-------------|
| 1 | "Response does not contain anything except the structured research report, there are no phrases like 'Research started …'." | Covered, with one stated exception (text on the same message as the `start_research` call) |
| 2 | "Default reports follow the configured section structure (working proposal: Key Findings → Detailed Analysis → Conclusion → References)." | Covered |
| 3 | "A user-requested format (comparison table, bullet summary, historical overview) overrides the default." | **Deferred** — issue #45. This change only bounds what such a request may do. |
| 4 | "Reports respect the configured length ceiling (target ~2,750 words / ~5 pages). The limit must not affect readability — text is never truncated abruptly, and reports always end at a clean boundary." | Covered |
| 5 | "No confidence scores, complexity ratings, or processing times appear in output." | Covered |
| 6 | "When a glossary is configured, domain-specific terminology is used consistently across the report where applicable." | **Deferred** — expected as an MCP tool, not configuration |
| 7 | "(optional) The clickable table-of-contents is present in the beginning of the report, only if it proves to be useful given the size limit." | **Deferred** — optional in the issue |

## What Changes

- **Configured section structure.** New application property `default_report_structure`: an
  ordered list of `{name, description}` sections, defaulting to Key Findings → Detailed
  Analysis → Conclusion → References. It is rendered into the report prompt, so a deployment
  can change section names, order, and what belongs in each.
- **Word ceiling with a review loop.** New graph nodes turn the single report step into
  `report → report-review → (report | END)`: the report node writes the first draft and later
  revisions, `report-review` judges the draft and returns either approval or concrete revision
  instructions. The existing nodes are renamed with it — `researcher` → `research-agent` and
  `reviewer` → `research-review` — so each name says which stage it belongs to and neither
  review step can be mistaken for the other. Word counts are computed in Python (whitespace-separated tokens) and stated in
  both prompts as numbers — "current 3,910 words, ceiling 2,750" — so the model never has to
  count. Bounded by a new `max_report_revisions` property; on exhaustion the latest draft is
  delivered as-is.
- **No hard truncation.** No `max_tokens` cap is set on the report call, and a revision that
  shortens must rewrite to fit rather than cut — the report always ends at a clean boundary.
- **Report is the whole answer.** The report node stops streaming tokens into the DIAL choice
  (a draft under review must not reach the user); the approved report is appended once, after
  the loop settles. On the launch turn the preparation agent no longer writes a closing
  message: the launch step of its instructions drops "tell the user that research is starting", and a
  new preparation middleware ends the agent loop as soon as `start_research` has fired, so no
  model call can follow it. The `"\n\n"` the research runner prepends becomes conditional on
  content having actually been streamed earlier in the turn.
- **Report review is observable.** Each report-review call emits one DIAL stage carrying the draft
  number, the measured word count and the configured ceiling, and the findings as a list; plus one INFO
  record carrying those same numbers and the *count* of findings. The asymmetry is required, not
  incidental: findings are LLM response text, which the logging-policy content allowlist keeps out of
  log records at any level, while a stage is part of the response the user asked for. Report review
  only — research review gets no stage for now.
- **Banned meta-content.** The report prompt prohibits confidence scores, complexity ratings,
  and processing times, and `report-review` checks for them.
- **Protected sections outrank user instructions.** `ReportSection` carries a `protected` flag;
  a protected section may be neither dropped nor restyled by anything the user asked for, and at
  least one section must be protected (the shipped default protects References). The inline
  citation format is protected report-wide and is not configurable at all. Both prompts carry the
  configured sections, the query and plan (where a user's formatting instruction already arrives
  today, via the report prompt's query and plan text), and the explicit list of what those
  instructions may not touch. `report-review` gains the query and plan as inputs so it can tell a
  followed instruction from an overridden rule. This bounds what a format request can do; making
  the app *follow* one is still issue #45's.
- **A section's rules live only in its description.** Everything about a section — contents,
  rendering, table columns — lives in its `ReportSection.description` and is passed verbatim to
  both the writer and the review step. The source-table rules therefore move out of
  `REPORT_SYSTEM_PROMPT` and into the default References section's description; report-wide rules
  (ceiling, banned annotations, inline citation format) stay report-wide.
- **Not in this change** (issue #32 acceptance criteria deliberately deferred, see
  design.md Non-Goals): user-requested format overriding the default (issue #45 — it needs the
  query/plan responsibility split settled first), the configured glossary (expected to arrive
  as an MCP tool rather than as configuration), and the optional clickable table of contents.

- **Every LLM call's inputs and outputs written down.** Both flows get a requirement listing, per
  call, which system prompt and messages it receives, whether images are included, which tools
  are bound, and what it returns — including the deliberate omissions, such as research-review
  judging coverage without the images the researcher saw (issue #29) and report-review judging a
  draft without the findings. Mostly this records existing behavior that was never specified; the
  matching convention goes into `CLAUDE.md`.

## Capabilities

### New Capabilities

- `report-composition`: what a research report must look like and how that is enforced — the
  configured section structure, the word ceiling and how the count is measured and fed back,
  the prohibited meta-content, and the report review ↔ revise loop with its cap and its
  no-truncation rule.

### Modified Capabilities

- `research-execution`: the graph gains the report-review loop, so the node set and the edges
  in **Research runs as a deterministic graph launched after plan approval** change; and
  **Report node writes the final cited report and is the only assistant content** changes —
  the node no longer streams into the assistant content, the approved report is appended once,
  and the section structure and word ceiling move to `report-composition`.
- `clarification-and-plan-alignment`: **start_research hard-gates and stops at readiness**
  gains the silent-handoff rule — once `start_research` succeeds, the preparation agent
  produces no further text for that turn. Gate-rejected calls are unaffected: the agent still
  relays the failure to the user.
- `application-config-schema`: **Application properties model** gains
  `default_report_structure`, `max_report_words`, and `max_report_revisions`, plus the nested
  `ReportSection` model.
- `dial-agent-with-mcp`: **Streaming response path** currently requires *all* assistant text to
  stream token-by-token via the `messages` stream mode; it is rescoped to preparation text, with
  the report appended once after the loop settles. **Assistant message content contains only model
  text** makes the paragraph boundary the assistant *message* rather than an intervening tool
  round, so two segments separate whether or not a tool ran between them — which is what a retried
  call needs. **Transient LLM stream drops retried in-app** gains the report-review call in its
  list of covered surfaces, and states that a retry's abandoned fragment is separated from the full
  answer. **Failures delivered as DIAL protocol errors** loses its assumption that partial *report*
  content can already be on screen.
- `logging-policy`: the **INFO request skeleton** is an exhaustive enumeration of events, so it
  gains a report-reviewed event and a draft ordinal on the report-generated event, and its
  model-call middleware set follows the `researcher` → `research-agent` rename.
- `prompt-caching`: a new requirement makes the report revision's prompt prefix-stable, the same
  shape as the existing prefix-stable research-review assembly, which is renamed with the nodes.
- `image-budget`: three requirements name the `researcher` node, so they follow the rename. No
  behavior changes — the budget and its substitution walk are untouched.

## Impact

- `src/dial_deep_research/app_properties.py` — new `ReportSection` model and the three new
  properties, plus the `max_research_iterations` description, which reads "researcher → reviewer
  loops" and is deployment-visible through the generated schema the admin configuration form renders,
  so regenerating the artifact does not fix it — the string is the source.
- `docs/generated-app-schema.json` — regenerated by `scripts/dump_app_schema.py` (lint fails
  on drift).
- `dial_conf/core/applications-template.json` — hand-updated example properties (the new report
  properties).
- `README.md` — the core-config snippet elides `applicationProperties` entirely, so nothing there
  changes; what may need a line is the prose that explains `mcp_servers` (an equivalent paragraph
  for `default_report_structure`, or a deliberate decision that the template plus the generated
  schema are enough).
- `src/dial_deep_research/app/research/prompts.py` — rewritten `REPORT_SYSTEM_PROMPT`
  (structure rendering, ceiling, banned content), new report-review system prompt and its
  structured-output schema, new revision-instruction renderer. Also carries two names the rename
  reaches: the `RESEARCHER_SYSTEM_PROMPT` / `REVIEWER_SYSTEM_PROMPT` constants, and the
  model-visible sentence `render_next_instruction` injects ("A reviewer checked the findings so
  far…") — which a second reviewer makes ambiguous.
- `src/dial_deep_research/app/research/nodes.py` — report node handles draft and revision; new
  `make_report_review_node`; two new routers (`route_after_report_review`, and the conditional edge
  out of `report` that skips the review when the budget is zero); word-count helper; the
  app-rendered length instruction; renames `build_researcher_agent` → `build_research_agent`,
  `make_reviewer_node` → `make_research_review_node`, `route_after_review` →
  `route_after_research_review`, the `ReviewerNode` type alias, and the agent-logging label
  `researcher` → `research-agent`.
- `src/dial_deep_research/app/research/tools.py` — `FINISH_ITERATION_RESULT` is **model-visible**
  text reading "handing off to the reviewer", which is ambiguous once two reviewers exist; the
  module docstring names the researcher too.
- `src/dial_deep_research/app/research/graph.py` — the renamed node ids, the new `report-review`
  node, its edges, and one more per-turn parameter forwarded to the report-review node factory (the
  stage-emitting callback the runner supplies).
- `src/dial_deep_research/app/research/state.py` — new state fields for the critique, the revision
  counter, and a flag recording that a revision's own model call failed (which the router reads to
  leave the loop with the previous draft).
- `src/dial_deep_research/app/research/runner.py` — the report is appended once from the
  graph's final state instead of streamed per token; the leading separator becomes
  conditional; and it builds the stage-emitting callback it hands to the report-review node (it holds
  the `Choice`; nodes do not, and `nodes.py` imports no DIAL types today).
- `src/dial_deep_research/utils/dial_stages.py` — the stage title formatter is tool-shaped
  (`[TOOL] "<name>" - <action>`); the report-review stage needs its own title form and body renderer.
- `src/dial_deep_research/app/completion.py` — tells `ResearchRunner` whether preparation
  already streamed content this turn.
- `src/dial_deep_research/app/preparation/runner.py` — exposes whether it appended any content, the
  fact `completion.py` passes on; it is the only holder of it.
- `src/dial_deep_research/app/research/__init__.py` — module docstring names the old node set
  (`researcher → reviewer → report`).
- `src/dial_deep_research/app/preparation/prompts.py` — the launch step drops the closing message;
  `RESEARCH_READY` wording.
- `src/dial_deep_research/app/preparation/agent.py` plus the new middleware that ends the
  preparation loop after `start_research`. It belongs under `preparation/`, not in the shared
  `app/middleware.py`, whose docstring reserves that module for "middleware any tool-calling agent
  may need" and sends agent-specific middleware to live with its agent — this one reads the
  preparation closure's `PrepState` and is useful to no other agent.
- `CLAUDE.md` — the convention requiring each LLM call's inputs and outputs to be stated in the
  spec that owns it.
- `docs/architecture.md` — carries the three-node graph and its edge string, the node diagram (no
  report loop), "streamed report + state" in the preparation sequence diagram, researcher/reviewer
  role prose throughout, a *quoted* research-execution sentence that this change rewords
  ("A researcher iteration SHALL therefore end only when the researcher calls `finish_iteration`"),
  and the step-budget claim that the outer graph is bounded by the iteration cap. (Currently staged
  but uncommitted, so it may be landing in parallel — named so it is not missed.)
- `tests/test_research_routing.py`, `tests/test_research_dispatch.py`,
  `tests/test_app_properties.py` — extended; new tests for the word count, the deterministic
  over-ceiling gate, the revision cap, the zero-budget skip, the failed-review path, the structure
  rendering, section-name uniqueness, and the silent handoff.
- `tests/test_agent_logging.py` — asserts `agent=researcher`, which the rename changes.
- `tests/test_stream_drop_retry.py` — builds the report node directly (`make_report_node`) over a
  state with no report or revision fields, so it moves to the new signature; its "partial text is
  not persisted" assertion now also covers "partial text is never visible".
