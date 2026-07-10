## Context

The README currently orders sections: intro → Prerequisites → Local run → Configuration →
DIAL core configuration → Running the app in Docker (opt-in) → Driving the app from the CLI →
LLM tracing with Opik → Environment variables. Contributor content (Prerequisites, Local run)
leads; operator content (Configuration, Environment variables) is split and the env-var table
is last. This change reorders the sections only.

## Goals / Non-Goals

**Goals:**
- Present sections by audience priority: general → configure-&-deploy → contributor.
- Keep each section's body verbatim — this is a move, not a rewrite.
- Keep the top-of-file table-of-contents anchor list in sync with the new order.

**Non-Goals:**
- No rewording of section bodies, no new prose, no deletions.
- No code, `settings.py`, `.env.example`, or generated-schema changes.
- Not touching statgpt or quickapps (separate repos, out of scope).

## Decisions

**Target section order** (top to bottom):

1. Intro + badges (unchanged)
2. Configuration
3. Environment variables
4. DIAL core configuration
5. Local run (with Prerequisites folded in as its opening subsection)
6. Running the app in Docker (opt-in)
7. Driving the app from the CLI
8. LLM tracing with Opik (optional)

Rationale: the configure-&-deploy block (2–4) is what a general reader or operator wants
right after the intro; the dev loop (5) and optional developer tooling (6–8) follow.

**Fold Prerequisites into Local run** (decided with reviewer). Every prerequisite (Docker,
Python, uv, an MCP server, a remote DIAL, DIAL Core version) is a dev-loop precondition, so it
reads as the first thing inside Local run rather than a section that precedes configuration.
Alternative considered — keep Prerequisites as its own top-level section moved below the
config block: smaller diff, but leaves two adjacent "before you run" sections; rejected for
clarity.

**Ordering within the config block: Configuration → Environment variables → DIAL core
configuration.** Configuration is the conceptual overview (env vars vs. application
properties), so it leads; the Environment variables table is the detailed reference it points
to; DIAL core configuration (registration + channels) is the deploy-time step that builds on
both. This also lifts the env-var table from dead-last to just under its overview.

**TOC anchor list** is reordered to match, and the standalone Prerequisites entry is removed
(it becomes a subsection of Local run, not a top-level anchor). All existing intra-README
links (e.g. "see Environment variables", "see DIAL core configuration") keep working because
the heading text — and thus the anchor — is unchanged; only position moves.

## Risks / Trade-offs

- [Cross-references read out of order after the move] → The Local run body references
  Configuration and DIAL core configuration, which now sit *above* it — links still resolve
  and the forward/backward direction reads naturally. Verify each in-page link after the move.
- [Cold-start-contributor guarantee] → The `dev-environment` spec requires that following the
  README top-to-bottom still reaches a working chat UI. Config legitimately precedes running,
  so top-to-bottom still works; re-read the flow end-to-end before archiving.
- [macOS port-5000 / APP_PORT note] currently lives in Local run and is referenced from DIAL
  core configuration. Since DIAL core configuration now precedes Local run, keep the note
  reachable — leave the explanatory copy in DIAL core configuration intact (it already
  restates the APP_PORT guidance) so the earlier section is self-contained.
