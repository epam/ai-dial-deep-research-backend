# Never put sensitive info in this repo

This repository is public. Everything in it is world-readable, including files that are only in a
local working tree today — an untracked file is one `git add -A` away from being committed. Never
let a secret, an endpoint, a client-identifying string, a real application property or a
deployment fact reach any file in it.

**Live probe output is client data by default — verify with it, then write the generic equivalent.**
That one rule prevents most of what follows.

## What must never appear

- **Secrets**: API keys, tokens, passwords, connection strings.
- **Endpoints**: hostnames and URLs of deployments, portals, registries and internal services.
- **Client identity**: a client's name, its abbreviations and agency codes, its deployment ids, its
  channel names, its publication series and real publication titles, its dataset names and dataset
  identifiers.
- **Real application properties**: these live in DIAL Core. The DIAL core `config.json` stays
  untracked, and `dial_conf/core/applications-template.json` carries only generic examples.
- **Deployment facts**: which MCP servers a live channel has configured, how many datasets or
  documents it exposes, which client runs on which environment. A fact about a real deployment is
  sensitive even when it names nobody, because it says who we work with and how.
- **Evaluation content**: real client queries, expected answers and test cases drawn from client
  work.

## What is allowed

Generic placeholders, and genuinely public facts:

- `ACME` as a stand-in client or organization, where an example needs one.
- **Public IMF datasets wherever a dataset is named** — their identifiers and their real names are
  published, so use them rather than inventing a placeholder dataset: `IMF:WEO` and
  `IMF:WEO(1.0.0)`, `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)`, and names such as
  `World Economic Outlook` or `Primary Commodity Prices`. `IMF:WEO` is this repository's canonical
  dataset-identifier example in prompts, comments and tests.
- `Market Outlook 2025` as a document or publication title.

Being over-strict costs real information, so check whether a name identifies a client relationship
before scrubbing it. A publicly known organization and its publicly published data are fine.

## Where the rules apply

Everywhere in the repository, not only in code: comments, docstrings, documentation, tests,
**OpenSpec proposals, specs, designs, tasks and review logs**, commit messages, and pull-request
descriptions. Planning artifacts are the easiest place to forget, because they are written while
looking at real output.

Manual testing writes outside the repository entirely. Conversation artifacts, request and response
logs, scratch scripts and notes go to `$TMPDIR` or a job's own temporary directory, never to a path
under the checkout.

## The trap to watch for

This repository also requires that claims be **verified rather than inferred** — probe the real
system, do not reason about it. That rule and this one collide at one exact moment.

Having probed a live MCP server or deployment, the values that come back feel like the strongest
possible evidence, and pasting them into a spec or a design reads as rigour. It is a leak.

**Treat live probe output as client data by default: verify with it, then write the generic
equivalent.** Keep the shape, the length and the punctuation that made the example worth having, and
change the identifying part. A placeholder URN of the same length makes every point the real one
does — `IMF:DIRECTION_OF_TRADE_STATISTICS(1.0.0)` is forty characters, so an argument about a label
overflowing a pill still holds.

## Before you finish

Check what you are about to hand over, in this order:

1. `git status --short` — does the working tree hold a file you did not mean to create?
2. `git diff` — does anything in your unstaged changes name a client, an endpoint or a deployment?
3. `git diff --cached` — **the index is a separate question.** Content staged before a later cleanup
   keeps the pre-cleanup text, so scrubbing the working tree does not scrub what is staged.

A grep for the client names and agency codes you have seen in this session is the cheapest version
of all three.
