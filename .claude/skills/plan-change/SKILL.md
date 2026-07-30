---
name: plan-change
description: Draft the planning artifacts of an OpenSpec change — clarify scope with the user, then drive the OpenSpec skills to write proposal, specs, and design. Stops before tasks and never writes code. Use when the user wants to plan a new feature, fix, or modification and iterate on the approach before implementation. Auto-trigger on intent like "let's plan X", "I want to design X", "propose a change for X".
---

# plan-change

## HARD CONSTRAINT — PLANNING ARTIFACTS ONLY

This skill produces the planning artifacts of one OpenSpec change: **proposal,
specs, design**. Nothing else.

You MUST NOT:
- Write or edit any file outside the change directory reported by `openspec status`
- Modify source code, build files, CI workflows, configs, or the README
- Create the `tasks` artifact (that is `/opsx:continue`, after the review gate)
- Run builds, tests, or linters
- Create commits, branches, or PRs
- Begin implementation — approval of a plan is not approval to implement

What to plan: `$ARGUMENTS`

This skill is a **wrapper, not a replacement**. OpenSpec owns artifact shape; the
CLI and the `openspec-*` skills are the authority on how each artifact is written.
What this skill adds is the part OpenSpec lacks: a scope conversation with the user
up front, an explicit stop before `tasks`, and a design written to be argued with.

The artifacts are read later by an adversarial critic (`/review-plan`) and by an
implementing agent. Include enough context that neither has to re-research the
codebase from scratch.

## Phase 1: Research

1. Read the project's `CLAUDE.md` / `AGENTS.md` (root, and any nested one covering
   the affected area) for conventions and structure.
2. Read `openspec/config.yaml` for project context and per-artifact rules.
3. List existing capabilities: `ls openspec/specs/` — a change that modifies
   behavior covered by an existing spec needs a *delta* against that spec, not a
   new capability. Read the specs that look relevant.
4. Find and read the code the change touches. Use Glob/Grep; for broad changes
   spanning several subsystems, delegate breadth-first search to `Agent` with
   `subagent_type: Explore` (read-only) and keep the synthesis yourself.
5. Skim 1-2 recent changes under `openspec/changes/archive/` to calibrate depth
   and house style.

Build a working model of: what exists today, what must change, which approaches
are viable, and what could go wrong.

## Phase 2: Clarify

Summarize findings to the user in 5-10 bullets: what the change involves
technically, which code paths are affected, and the risks or edge cases you found.

Then ask **only about genuine forks** — decisions where different answers lead to
materially different artifacts:
- scope boundaries (what is in and out)
- which approach, when more than one is defensible
- edge cases to handle now versus defer

Use `AskUserQuestion` with concrete options, and recommend one. Keep it to two or
three questions; make every routine call yourself. Ambiguity you can resolve from
the code is not a question. If the user says "go ahead" or "no questions",
proceed with stated assumptions.

This is deliberately short. The user's time is spent here and at the review gate,
not on gaps the critic loop can close.

## Phase 3: Scaffold — delegate to OpenSpec

Derive a kebab-case change name from the request (3-5 words, no filler):
`add-user-auth`, `retry-transient-llm-drops`.

Invoke the **`openspec-new-change` skill** with that name and the clarified
description. It owns scaffolding: schema selection, `openspec new change`, and the
first artifact's instructions. Do not reimplement it.

Fallback if that skill is not installed (core profile):

```bash
openspec new change "<name>"
openspec status --change "<name>" --json
```

If the work lives in a registered standalone OpenSpec store, discover it with
`openspec store list --json` and pass `--store <id>` on every command that reads
or writes changes and specs.

## Phase 4: Write proposal → specs → design

**Never hand-roll an artifact.** For each one, invoke the
**`openspec-continue-change` skill** once, on this change. That skill loads
`openspec instructions <artifact-id> --json` and applies the schema's own
`instruction`, `template`, `context`, and `rules` — which are the authoritative
guidance for artifact content and shape — then stops after exactly one artifact.
This skill must not paraphrase, summarize, or override any of it.

Invoke it once per artifact — **proposal, then specs, then design**, which is the
order the dependency graph resolves anyway. Three invocations, then **stop**.

**Do not create `tasks`.** It depends on both specs and design, so every accepted
review finding would churn it; it comes after the review gate, via
`/opsx:continue`. (On a non-default schema, defer that schema's implementation
checklist instead — the terminal artifact in the build order, which is the one
`openspec status` lists in `applyRequires`.)

After each invocation confirm the file landed (`openspec status --change "<name>"
--json`). If `openspec-continue-change` reports missing context, answer from Phase
1-2 rather than letting it guess.

Fallback if that skill is not installed — run the CLI per artifact yourself:

```bash
openspec instructions <artifact-id> --change "<name>" --json
```

Use the returned `template` as the file structure; `context` and `rules` are
constraints on you, never content for the file. Take the output path from
`artifactPaths.<id>` in `openspec status` rather than assuming it, and for the
glob-valued `specs` artifact create concrete files under it rather than writing the
glob.

### Overlays

Two additions to what OpenSpec already instructs. Everything else — requirement
and scenario format, delta operations, capability naming — comes from the CLI
instructions, not from here.

**proposal.** Make `Impact` name affected files individually rather than
gesturing at areas. It doubles as the implementer's map.

**design.** Two policy differences from the stock instructions:

- OpenSpec says create `design.md` only if the change warrants it. Here, **write
  it unless the change is genuinely trivial** (single obvious code path, no new
  dependency, no alternatives worth weighing). If you skip it, tell the user — the
  review loop then has far less to work with, and its most valuable level is the
  one that argues about approach.
- The stock instruction asks for alternatives considered. Treat that as
  **mandatory, per decision, with the reason each alternative was rejected.** This
  is the input the critic argues against at review level 1. A design that records
  only its conclusion forces the critic to re-litigate options you already
  dismissed, and wastes the loop.

Also carry a **No changes required** section when it applies: files that look like
they need touching but do not, with the reason. It measurably stops implementing
agents from wandering.

## Phase 5: Present

Validate structure, then report:

```bash
openspec validate "<name>" --strict --json
```

Tell the user:
- The change name and `changeRoot`
- 3-5 sentences on the proposed approach
- The capabilities created or modified, and the files the proposal expects to change
- Every assumption you made and every open question left in the artifacts
- Validation result

Then state the next step: **`/review-plan <name>`** runs the adversarial loop —
one critic subagent judging whether the change makes sense at all, then hunting
gaps, then checking coherence. Do not run it yourself; the user decides when the
draft is worth reviewing. `tasks` comes after that review and the user's approval.

## Rules

- Planning artifacts only. No code, no builds, no git writes.
- Delegate artifact writing to the `openspec-*` skills; they and the CLI own
  artifact shape. This skill owns the clarify gate, the design policy above, and
  the stop before `tasks`.
- Never create `tasks`.
- Take output paths from `openspec status` rather than assuming them.
- Do not invent scope the user did not ask for. Record deferred ideas in the
  design's Non-Goals instead.
- If the request is a revision of an existing change rather than a new one, stop
  and point at `/opsx:update`.
