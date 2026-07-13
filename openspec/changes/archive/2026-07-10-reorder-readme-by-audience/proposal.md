## Why

The README front-loads contributor content: it opens into Prerequisites and Local run (a
developer loop) before Configuration, and the full Environment variables table — the prime
reference for anyone configuring or deploying the app — is last. A general reader or an
operator has to scroll past dev setup to reach the content they came for.

## What Changes

- Reorder the top-level README sections by audience priority: intro (general) → a
  "configure & deploy" block → the developer loop → optional developer tooling. No section's
  body wording changes; sections are moved, not rewritten.
- Promote **Configuration**, **Environment variables**, and **DIAL core configuration** up,
  directly after the intro, as the configure-&-deploy block.
- Fold **Prerequisites** into **Local run** (every prerequisite is a dev-loop concern) and
  place that block after configure-&-deploy.
- Keep **Running the app in Docker (opt-in)**, **Driving the app from the CLI**, and **LLM
  tracing with Opik** last as optional developer sections.
- Update the table-of-contents anchor list at the top to match the new order (and drop the
  standalone Prerequisites entry now folded into Local run).
- Docs-only: no content is deleted, no section body is reworded, no code changes.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `dev-environment`: the "Minimal developer README" requirement gains an audience-ordering
  clause — the README SHALL present its sections general-audience → operator/configuration →
  contributor. The existing cold-start-contributor guarantee (following top-to-bottom reaches
  a working chat UI) is preserved.

## Impact

- `README.md` at the repo root: section order and the table-of-contents anchor list.
- No code, settings, `.env.example`, or generated-schema changes. No behavior change.
