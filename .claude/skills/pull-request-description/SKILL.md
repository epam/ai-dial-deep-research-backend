---
name: pull-request-description
description: Write or edit the description of a pull request. Invoke before drafting a PR body and before editing an existing one — e.g. "write/update the PR description", "create a PR" or any gh pr create/edit call that carries a body.
---

# Pull request description

The reader is a reviewer about to open the diff. The description says **what changed and why**. The diff says how.

## Shape

Keep the repository template's headings. Under the description heading:

1. One or two sentences on the problem: what was wrong or missing.
2. A bulleted list of the changes, **most important first** — the change a reviewer must understand to review the rest comes first, chores last.
3. One line on verification.
4. Keep whatever trailer the template or the project requires (license confirmation, attribution).

## Rules

- **One bullet per change.** Open with the bolded thing that changed and what it does now, then why, in the same bullet, when the why is not obvious.
- **Keep bullets to one or two sentences.** A paragraph is not scannable.
- **Leave out the how.** No call sites, control flow, field wiring, or the order the code checks things in. That is what the diff is for.
- **Name the concrete thing** — the property, the file, the image tag, the number. Never a category word standing in for it.
- **Full sentences, simple phrasing.** No compressed notation, no fragments that depend on layout.
- **Cut** restatements of the title, rationale essays, and alternatives not taken.
- **Verification is one line:** what you ran and the result. Never claim a check you did not run, and say so when a recorded result predates later commits.
- **No sensitive or client-related information** in the PR title or description. Similar to general repository rules, no client names, endpoints, references to internal documents or other private details.

## Editing an existing description

Read the current body and the commits it does not cover yet (`git log <base>..HEAD`), then rewrite it to describe the branch as it now stands. A description that contradicts the code is worse than a short one.
