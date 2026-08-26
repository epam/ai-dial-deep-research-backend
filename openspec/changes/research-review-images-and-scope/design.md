## Context

`_render_findings` (`app/research/nodes.py`) turns the research-agent transcript into a single
string: every `ToolMessage` becomes a `RESULT:` line, and an image-carrying one gets a trailing
`[+image]` marker instead of the image itself. `RESEARCH_REVIEW_HUMAN_MESSAGE` then formats that
string, the query, and the plans into one `HumanMessage`. Research-agent's own transcript already
carries real image content blocks, and `ImageBudgetMiddleware` already caps the running total
across `state["messages"]` at `settings.max_context_images` (50) before every research-agent model
call, substituting the newest image-carrying tool results with an error message when it would
overflow. Research-review reads that same, already-clamped `state["messages"]` — it just throws
the image blocks away on the way into its own prompt. See `proposal.md` for why that causes the
observed infinite loops and the scope confusion with report-format requests.

## Goals / Non-Goals

**Goals:**
- Give research-review the same image content blocks research-agent already has, placed where
  each tool result's text sits, so it can treat an image as evidence.
- Keep the append-only byte-prefix property `RESEARCH_REVIEW_HUMAN_MESSAGE` is built for (see
  **prompt-caching**): a later iteration's call must still share a byte prefix with an earlier
  one's.
- Add the report-format-out-of-scope and no-report-exists-yet rules to
  `RESEARCH_REVIEW_SYSTEM_PROMPT` only — sharpened so a format request that names real data
  (e.g. "compare X and Y in a table") still drives an ordinary coverage-gap next step; only the
  presentation itself, never the data it implies, is out of research-review's scope.
- Add a sixth check to `REPORT_REVIEW_SYSTEM_PROMPT` so a compatible user format request is
  actually enforced somewhere in the loop, using the query and plan report-review already
  receives — no new input.

**Non-Goals:**
- Splitting a report-format instruction out of the plan at preparation time, so it never reaches
  research-review as a plan item in the first place. That is the larger rework issue #45
  gestures at as "part of #32"; this change is the prompt-only fix the reviewer specifically
  asked for, and is a smaller, faster-landing step. If it proves unreliable in practice, the
  structural split is the natural follow-up.
- Changing the image budget or its limit. Research-review inherits whatever research-agent's own
  call already enforces.
- Changing what the `report` or `report-review` calls receive — both already get the query and
  plan a format request would live in; only report-review's instructions about that input change.

## Decisions

**1. `_render_findings` returns a list of content blocks, not a `str`.**

A `HumanMessage.content` list of `{"type": "text", ...}` and `{"type": "image", ...}` blocks is
the shape LangChain already uses for research-agent's own multimodal messages, and the shape
`is_image_block` (`utils/content.py`) already recognizes. Reusing it means no new content-block
type, and the reviewer's message becomes structurally the same kind of thing research-agent and
the report call already send.

Alternative considered: keep `_render_findings` as a string and send images through a second,
parallel list of message parts. Rejected — it breaks the single "findings" framing the prompt
gives the model, and keeping two divergent lists in lockstep as the transcript grows complicates
the append-only prefix property this code is deliberately built around.

**2. `RESEARCH_REVIEW_HUMAN_MESSAGE` splits into a head/tail pair of templates.**

The findings content blocks need to sit inside the `<findings>...</findings>` tag, between fixed
text before and after. A single format string can't hold a list of blocks in the middle, so the
constant splits into `RESEARCH_REVIEW_HUMAN_MESSAGE_HEAD` (through `<findings>\n`) and
`RESEARCH_REVIEW_HUMAN_MESSAGE_TAIL` (from `</findings>` through the closing `</plans>`). The
node assembles `[head_text_block, *findings_blocks, tail_text_block]` as the `HumanMessage`
content. The wrapping text and tags are unchanged, so the model still sees the same document
shape it saw before. Confirmed via grep that only `nodes.py` imports the old constant, so the
split has no other call site to update.

**3. No new image budget for research-review.**

It reads the exact `state["messages"]` research-agent's own call already trimmed, so the image
count it can ever see is already bounded by `settings.max_context_images`. This was established
by issue #25's fix (`ImageBudgetMiddleware`); this change only stops discarding that
already-bounded data before it reaches research-review, rather than introducing a second budget
to enforce.

**4. Both new rules live in `RESEARCH_REVIEW_SYSTEM_PROMPT`, not in a data-model change.**

The report-format-out-of-scope rule and the no-report-exists-yet rule are prompt instructions
about how research-review should judge what it already receives (the query and the plan), not
about a new input. This matches the proposal's chosen scope: a reviewer-prompt fix, not a
preparation-stage restructuring of the plan.

**5. Report-review's format check is a sixth item on its existing checklist, not a new call or
schema field.**

`REPORT_REVIEW_REQUEST` already carries the query and the approved plan's first entry — exactly
where a user's format request would be. `ReportReview.report_violations` is already a free-form
list of strings, so a violation naming an unmet format request fits the existing shape; no new
field or a separate pass over the draft is needed. This closes the second half of issue #45 (the
report-composition spec's own text already flagged "routing a requested format to the report is
deliberately not part of this change" as a deferred concern), while the actual routing — the
report node seeing the request at all — was already true beforehand: the writer's prompt already
tells it to follow a compatible instruction where it can (see **report-composition**'s protected-
sections requirement). What was missing was anything checking that it did.

Alternative considered: leave this to a follow-up change, since it is a distinct concern from the
images-and-scope fix this change is named for. Rejected — it needs no new plumbing, the live test
run that validated the images-and-scope fix is exactly the scenario that surfaced the gap, and it
completes the second half of the same issue (#45) this change already addresses in research-review.

**6. Research-review's format rule distinguishes data from presentation, rather than excluding
format instructions wholesale.**

The first version of this rule told research-review to ignore "any instruction about the
report's format" outright. That is too coarse: "compare X and Y in a table" is a formatting
instruction, but it also names two things that must actually be found — dropping it entirely
would let research-review approve an iteration that never gathered one of them. The rule now
keeps research-review blind only to the *presentation* (would the eventual report look right),
never to a *data* requirement the instruction happens to carry, which stays an ordinary next
step like any other coverage gap.

Alternative considered: leave the coarse version and rely on the plan itself already naming the
needed data as its own step, independent of the format instruction. Rejected — a plan step and a
format instruction are two different parts of the same message the model reads; nothing stops a
plan step from being terse ("compare X and Y") while the format instruction is what actually
specifies the comparison's shape (a table with named columns), so the data requirement can live
only in the instruction research-review was about to disregard.

## Risks / Trade-offs

- **Embedding images raises the token cost of every research-review call.** An image already
  costs research-agent tokens each time it's fetched; now research-review pays that cost too,
  once per reviewed iteration. → Mitigated by the existing 50-image cap, and by the fact that the
  loops this replaces were themselves burning tokens — issue #45 measured "roughly half the
  turn's input tokens" going to iterations that could never succeed.
- **A prompt-only scope rule is a judgment call, not a structural guarantee.** A query that mixes
  a research ask with a format ask (e.g. "compare X and Y in a table") asks the model to separate
  them itself. → No structural mitigation in this change; if this proves unreliable, the
  follow-up is the preparation-stage split proposed in #32, which would remove format
  instructions from the plan before research-review ever sees them.
- **`RESEARCH_REVIEW_HUMAN_MESSAGE` becomes two constants.** A future reader who greps the old
  name won't find it. → Kept the two new names close to the original (`..._HEAD` / `..._TAIL`)
  and confirmed there is exactly one call site to update.
- **Report-review's format check is a judgment call, like research-review's scope rule.** The
  model decides both whether a request conflicts with the protected rules and whether the draft
  honored it — there is no Python-side arbiter, unlike the length ceiling. → No structural
  mitigation; the check is worded to name conflict resolution explicitly (checks 1-5 always win),
  and the existing review ↔ revise loop already bounds how many times a missed request can trigger
  a revision (the version budget), so a persistent miss ends in delivery rather than a loop.
