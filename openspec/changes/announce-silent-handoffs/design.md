## Context

See proposal.md — Why, for the motivation.

Three facts about the code as it stands shape the approach.

**The decision is the router's, and it is taken mid-run.** `route_after_research_agent` compares the
just-finished iteration against the cap and returns `report` instead of `research-review`. No node
sits on that path, which is why the router already logs the event itself rather than leaving it to a
node.

**The report loop's equivalent starts out after the graph.** `ResearchRunner` reconstructs the
unreviewed delivery once the graph has finished, from the final state and the channel configuration.
The placement is inherited rather than chosen: when the report review was introduced, the runner was
the only place holding that configuration.

**Stages appear in creation order.** A DIAL stage is a chunk in the response, so the order the runner
creates them is the order the user reads them.

## Goals / Non-Goals

**Goals:**

- Every hand-off that changes what the user gets is visible in the stage channel, at the point in the
  run where it happened. Transparency is the stage channel's job; the logs keep the content allowlist
  and gain nothing here.
- The two loops report a skipped or failed step the same way, differing only where their subjects
  genuinely differ.

**Non-Goals:**

- Changing what the cap or the failed-revision rule does. The router's decision, the iteration
  counting, the hand-off to the report node and the delivery of the previous draft are untouched;
  only their visibility changes.
- Recovering from a failed research-review call. That is a separate gap, tracked in issue #60.
- Showing any draft the loop did not settle on. The failed-revision stage names numbers and a failure
  kind, never draft text.

## Decisions

### The router reports the skip through a callback

`route_after_research_agent` takes an emitter alongside the cap it already receives, and calls it on
the branch that skips the review — beside the INFO record it already writes there.

*Alternatives rejected.* **Emitting from the runner after the graph, as the report loop does** — the
stage would be created after every report stage, so a notice about a decision taken before the report
was written would sit at the end of the run, out of order. **Inferring the skip in the runner from
the stream** — the runner would have to re-derive the router's condition from the state it observes,
which duplicates the routing rule in a second place; the same reasoning rejected inferring node entry
from the stream when the activity stage was designed. **A dedicated graph node on the skip path** —
a node whose whole body is one stage emission, for a decision the router has already made.

The cost is that a router gains a side effect beyond logging. It is the same kind of side effect it
already has, and it keeps the announcement with the decision rather than with an observer's guess
about it.

### Each skipped step is reported by whoever decides it

Both routers report their own hand-off, and the report node reports the failure it catches. The
unreviewed delivery therefore leaves `ResearchRunner`, which reconstructed it after the graph had
finished from the final state and the channel configuration, and moves into `route_after_report`.

The report router needs the section structure and the ceiling to measure the draft, which the graph
builder already holds, so the move costs two parameters. Its INFO record travels with it: a stage
and the record that mirrors it drifting apart is how the two come to disagree.

*Alternative rejected.* **Leaving it in the runner** — it works, and for the report the two
positions render in the same place because nothing emits after that decision. But then one loop
announces its skipped step from the decision and the other from a reconstruction, and a reader has
to learn which is which before trusting either.

### A cap of one is silence, not an announcement

The rule mirrors the report loop, where a version budget of one emits nothing: with a single
permitted iteration there was never a review to exhaust, so a notice would report a configuration as
if it were an outcome.

### The report node reports its own failed revision

The report node catches the failure, so it is the only place that knows the exception kind — the
graph state carries a boolean and nothing else. It hands the runner the failed draft number, the
delivered draft number and the exception kind through a callback, the same split the report-review
stage uses.

*Alternatives rejected.* **Emitting from the runner after the graph**, reading the state flag as the
unreviewed delivery does — the state flag says a revision failed but not what failed, so the stage
could not name the failure kind, and naming it is the point. **Carrying the exception kind in the
graph state** so the runner could read it — a field on the state for no other reader, where a
callback already exists for this exact purpose.

Its prefix is the report step's own, not `[REPORT REVIEW RESULT]`, because a prefix names the step
the stage speaks for. The two exhausted-budget stages keep their review prefixes on the same rule:
each is a review step reporting that it did not run, while this one is the report step reporting on
itself.

### The stage carries no elapsed time and no findings

There was no call to time and no verdict to show. The title states that the budget is exhausted and
that the run proceeds to the report; the body gives the iteration and the cap. This mirrors the
report loop's unreviewed delivery, which likewise carries no duration.

## Risks / Trade-offs

- **A router with a side effect is easier to get wrong under future edits.** A second caller, or a
  router invoked twice for one decision, would emit two stages. → The graph calls each router once
  per super-step, and the emission sits on a branch that ends the research loop, so it can fire at
  most once per run; a test pins that.
- **The wording claims the report follows.** If a later change routed elsewhere on an exhausted
  budget, the stage would be wrong. → The stage is emitted on the same branch that returns `report`,
  so the two cannot disagree without an edit that touches both lines.
