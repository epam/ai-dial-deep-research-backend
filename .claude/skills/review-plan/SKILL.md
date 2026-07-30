---
name: review-plan
description: Run the adversarial review loop on the plan of an active OpenSpec change, before it is implemented — spawn a critic subagent that judges whether the change makes sense, then hunts gaps, then checks coherence; verify every finding against the real code, apply the safe fixes, escalate approach-level findings to the user, and record everything in review-log.md. Use ONLY when the user explicitly asks to review or critique the plan of a SPECIFIC named change (e.g. "review the plan for add-user-auth"). Do not trigger without a concrete target. Reads and refines planning artifacts only — it never reviews or writes code, and it is not for archived changes; for reviewing implemented code against its artifacts use /opsx:verify, and for a code diff review use /code-review.
---

# review-plan

## HARD CONSTRAINT — PLANNING ARTIFACTS ONLY

This skill improves the existing planning artifacts of one **active** OpenSpec
change and writes `review-log.md` in that change's directory. **Nothing else.**

It reviews a plan, not an implementation. It does not read the change's code for
review purposes — it reads code only to *verify the plan's claims about the
codebase*. Two neighbours it is not: `/opsx:verify` checks a finished
implementation against its artifacts, and code-diff review is a separate skill.
Archived changes are out of scope; there is nothing left to steer.

You MUST NOT:
- Write or edit any file outside the change directory reported by `openspec status`
- Modify source code, build files, configs, or the README
- Create artifacts that do not exist yet — that is `/opsx:continue`'s job
- Create the `tasks` artifact, even if the schema says it is ready
- Run builds or tests, or make git writes
- Begin implementation

Target: `$ARGUMENTS` — a change name, optionally followed by a max pass count
(default **6**).

## Phase 0: Resolve and read

1. Resolve the change. If `$ARGUMENTS` names one, use it. Otherwise run
   `openspec list --json` and ask with `AskUserQuestion`. Do not guess. Announce
   `Using change: <name>`.
2. ```bash
   openspec status --change "<name>" --json
   ```
   Take `changeRoot` and `artifactPaths`. Read every file in each artifact's
   `existingOutputPaths`. **Never hardcode artifact ids or paths.** If the work
   lives in a registered store, pass `--store <id>` (see `openspec store list
   --json`) on every command.
3. Read the project's `CLAUDE.md` / `AGENTS.md` and the existing
   `openspec/specs/` capabilities the change touches.
4. Read `<changeRoot>/review-log.md` if it exists. Extract the running
   **rejected-and-deferred set** — findings already dismissed, with their reasons.
   This set is what stops the loop from re-litigating the same points forever.
5. If the `design` artifact does not exist, say so and continue on the artifacts
   that do. Level-1 review will be much weaker without it; suggest the user create
   it via `/opsx:continue` first. Do not create it yourself.

## Phase 1: Structural pass (before spending critic budget)

```bash
openspec validate "<name>" --strict --json
```

Fix what it reports — it catches the mechanical class for free, including
scenarios written with three hashtags instead of four, which are otherwise
silently ignored. Report what you fixed. The critic's attention then goes to
semantics, not formatting.

## Phase 2: Review loop

**One pass** = one critic run plus the triage, edits, and logging that follow it.
`N` caps passes, all kinds counted the same way. Repeat until an exit condition in
2f fires.

A pass ends one of two ways: it stops at level 1 and escalates to the user, or —
level 1 being clean — it reaches level 2 and reports level-2 and level-3 findings
together. Levels never cost a pass each.

### 2a. Spawn the critic

One `Agent` (`subagent_type: general-purpose`) per pass. Its prompt is the
brief in `.claude/skills/review-plan/CRITIC_PROMPT.md`, followed by:

- the **full current text** of the proposal, every spec file, and the design
- on passes after the first: what changed since the last round
- the **rejected-and-deferred set** from the review log, each with its reason

The critic returns findings and edits nothing. One critic, not several: the three
levels are a dependency chain — if the approach is wrong, coherence findings are
worthless — so they belong in one agent reasoning in order.

### 2b. Verify every finding against the real code

For each finding, open the cited `file:line`, spec section, or artifact text and
confirm it. **Discard anything you cannot reproduce.** Critics hallucinate
confidently. Count the discards — you will report them.

This verification is why the loop runs in-session rather than headless: your
judgment filters the critic, and the user can interject on any pass.

### 2c. Triage — who resolves what

| Finding | Resolved by | Action |
|---------|-------------|--------|
| any level 1 | **the user** | escalate, with a suggested action |
| any **Critical** at level 2 or 3 | **the user** | escalate, with the fix you propose |
| level 2 or 3, High and below | you | Accept / Reject / Defer, then apply |

**Any verified level-1 finding stops the pass.** Level 1 is approach, alternatives
and scope — all of it is the user's call, so there is no such thing as a level-1
finding you resolve yourself. Applying one means redesigning the user's feature on
a critic's hunch, the failure mode this whole workflow exists to prevent.

Escalate every level-1 finding with `AskUserQuestion`, and for each one **suggest
an action** and say which you recommend:

- **revise** — keep the change, fix the design; `/opsx:update` is the tool
- **abandon or park** — the finding says this change should not be made now
- **keep the approach** — the finding is wrong, or the trade-off is accepted;
  record the reason in the relevant design decision so it is not raised again

The decision is the user's. The recommendation is yours — never present the options
without one.

**Hold that pass's level-2 and level-3 findings.** A level-1 resolution can already
resolve them or make them irrelevant, and applying them first can conflict with the
revision. Log them as held, apply nothing, and let the next pass re-derive whatever
still stands against the revised artifacts.

Escalate **Critical** level-2 and level-3 findings the same way, but propose the
concrete fix: these rewrite a behavior contract, so the user sees them before they
land. Everything else at level 2 and 3 you resolve yourself — Accept (fix it),
Reject (one-line reason), or Defer (out of scope; note it) — and report all of it
in Phase 3. If a level-2 fix would materially change scope, it *is* a level-1
finding; escalate it.

### 2d. Apply fixes, keeping the artifacts coherent

Edit the artifacts to apply every accepted fix. A fix rarely lands in one file —
after each edit, check the others **in both directions**:

- a new scenario may need a design decision to justify it, or a capability entry
  in the proposal
- a changed design decision may invalidate scenarios written against the old one
- a widened Impact list may imply new spec coverage

Only edit files in `existingOutputPaths`. Do not create new spec files for
capabilities the proposal does not list — add the capability to the proposal
first, or defer.

### 2e. Record the pass

Append one block to `<changeRoot>/review-log.md` (create it on pass 1 with an
`# Review log — <name>` heading). **Append-only — never rewrite a prior pass.**

```markdown
## Pass {i}

**Verified findings:**

1. **[L{level}/{Severity}] {artifact} § {section} — `file:line`** — {claim}
   - Evidence: {what was opened and what it said}
   - Resolution: **Accepted** — {what changed, in which artifacts}
     / **Rejected** — {why} / **Deferred** — {why} / **Escalated** — {user's decision}

**Discarded (unverified):** {count} — {one line each, or "none"}

**Held (level 2/3, superseded by a level-1 escalation this pass):** {one line each,
or "none"}

**Exit:** {converged | new findings, continuing | level-1 escalated | cap reached}
```

### 2f. Re-validate and check convergence

Re-run `openspec validate "<name>" --strict --json` — your own edits can break
spec structure.

Stop when **any** of these holds, and say which fired:

- no new Critical or High finding survived verification this pass — **one** clean
  pass is enough; do not ask for a second to confirm
- pass `N` reached
- the user chose to abandon or park the change

A level-1 escalation is **not** an exit. Once the user decides and the artifacts are
revised, run a fresh pass against the revised artifacts. Only the conditions above
end the loop.

If the critic raises fresh level-1 findings on consecutive passes, tell the user the
plan likely needs rethinking rather than more review. That is a signal to raise, not
a stop condition — keep going unless they say otherwise.

## Phase 3: Present

Tell the user:
- Which change was reviewed, how many passes ran, and **which exit condition
  fired**
- Counts: verified findings by level, Accepted / Rejected / Deferred / Escalated,
  and how many the critic raised that did not survive verification
- The most important changes the loop made to the artifacts
- **Level-1 findings awaiting their decision**, stated plainly — these are the
  reason to read the log
- Anything Deferred that an implementer would otherwise assume is in scope
- **What the loop did not cover**: cap reached with findings still arriving,
  findings that could not be verified either way, artifacts missing. A loop that
  reports clean when it merely ran out of passes is worse than no loop.
- Next step: the user reads the refined artifacts plus `review-log.md` and
  approves. Then `/opsx:continue` writes `tasks`, and `/opsx:apply` implements.
- That `review-log.md` is **scratch for this gate, not a deliverable** — it gets
  deleted on approval. Anything in it that an implementer will still need must
  already be folded into the artifacts themselves: a Deferred item belongs in the
  design's Non-Goals, a rejected alternative belongs in the relevant decision's
  rationale. Check this before you present, because the log is about to disappear.

## Phase 4: Remove the log on approval

When the user approves the plan, delete `<changeRoot>/review-log.md`.

Do it in this session if they approve while the skill is still running. If they
approve later, say plainly that the file should be deleted at that point — the
change directory that goes on to implementation and archive should carry only
OpenSpec's own artifacts.

Never delete it while the loop is still running or before approval: it is both the
loop's memory and the evidence the user is reading to decide.

## Rules

- Planning artifacts and `review-log.md` only. Never source code, never builds,
  never git writes.
- The critic is a subagent; **you** own verification and every edit. No unverified
  claim reaches an artifact.
- Level-1 findings go to the user, always.
- `review-log.md` is append-only *during* the loop, and it is the memory that makes
  the loop converge: a rejected finding must reach the next critic with its reason
  attached, or it comes back every round. It is deleted once the user approves —
  it never reaches implementation or the archive, so fold anything durable into
  the artifacts before then.
- Never create artifacts or spec files that do not exist — point at
  `/opsx:continue`.
- Report what was dropped, not just what was fixed.
