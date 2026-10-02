## Context

The archived change `no-calculations` added the rule to every step. Its plan item and research parts
asked both for a stated figure and for the figures it would be computed from, and its query-check
sentence said that research "looks only for figures the sources state", which the query check read
as a reason to ask the user for something else to report.

## Goals / Non-Goals

**Goals:**

- No clarification round for a request that asks for a computed figure.
- A plan the user approves never promises what the report will refuse.

**Non-Goals:**

- A code check that rejects a plan with a calculation step. A live run showed that the prompt alone
  holds against repeated pushback, so a further LLM judgement is not added.
- Changing the report writer or report review, whose rule already gives the inputs and says the
  sources do not give the figure.

## Decisions

**The query check is told what research does with such a request, not only what it must not ask.**
A bare prohibition ("never ask how to compute") left the model free to ask for an alternative; saying
that research looks for the stated figure and otherwise its inputs makes the request a settled
subject.

**The inputs are conditional on the stated figure being absent.** Retrieving the inputs when a source
states the figure spends research steps on evidence the report will not need. Research review keeps
the reasonable-attempt condition, so a figure is never declared absent after a single search.

**Pushback is handled in the preparation prompt.** The agent explains the limit once, keeps the plan
item, and offers the inputs. The rule's highest priority already binds the later steps.

## Risks / Trade-offs

- [The report lacks the inputs when a stated figure turns out to be weak or narrow] → the writer still
  gives every value the question asks for, and the source-selection rules still ask for near matches.
