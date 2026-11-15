## Context

The prompt code is already implemented (see proposal.md, "Why"). This change only brings the specs
in line with it. The code is the reference: every requirement in the delta specs states what the
prompts at the branch head ask for.

## Goals / Non-Goals

**Goals:**

- Every requirement that names a rule uses the rule's current name.
- Every requirement that states what a prompt asks for matches the prompt.

**Non-Goals:**

- No code change. Where the code is inconsistent with itself, the specs describe each place as it
  is, and the inconsistency is listed under "Risks / Trade-offs".
- No change to requirements that the prompt rewrite did not touch, even where they are stale for
  another reason. One example is the default of `max_research_iterations`, which
  research-execution gives as 10 and application-config-schema and the code give as 5. Another is
  in "update_query sets the working query and runs an independent clarity check". Its unchanged
  text says that the user settles every dimension and that an event-anchored period is proposed
  to the user. However, the clarity-check prompt tells the model to resolve the time period
  itself. A requirement that this change modifies for another reason keeps such older text as it
  is.

## Decisions

- **Rule names are written into the requirements.** The prompts refer to each other's rules by
  name, such as the source-selection rule "When to say that evidence is missing" in a
  faithful-relay rule. So each rule's requirement states its name, and a reference to a rule
  uses that name. The alternative was to refer to rules by their number in the spec, but the code
  renumbered the source-selection rules, so a number is the less stable reference.
- **A renamed rule keeps its requirement.** Each old source-selection rule maps to one new rule
  through a RENAMED entry and a full MODIFIED block. Archiving keeps their positions, so the main
  source-selection spec is then reordered by hand into the rule order the prompt uses, rules 1 to
  10. The alternative, removing every old rule and adding every new one, would lose the link
  between an old rule and the rule that replaced it.
- **Examples stay generic.** Scenarios use public IMF datasets and made-up dates, as
  `no_sensitive_info.md` requires.

## Risks / Trade-offs

These inconsistencies are in the code. The specs record each place as the code words it, and
this change resolves none of them.

- **Two definitions of a calculation.** The faithful-relay term "Calculation" leaves out modelling,
  an elasticity, a regression estimate and the rounding exception. `CALCULATION_DEFINITION`
  in `research/prompts.py` still has all four. The writer and the reviews receive both texts.
- **When a missing stated date stops being a gap.** "Stated date and described period" keeps it a
  gap until research gets the date. "When to say that evidence is missing" closes the gap for
  every item, dates included, after a reasonable attempt.
- **Examples in the generic rules.** The module docstrings say that the generic rules name no
  client, publication or tool. However, the source-selection rules give the IMF and the World
  Economic Outlook as examples, and the faithful-relay terms name `rag_search` and
  `retrieve_text_chunks`. The faithful-relay spec allows the terms to name tools. The
  source-selection spec keeps its sentence that the generic rules name no client publication.
- **Section rules outside the section descriptions.** A section's description is meant to be the
  single home for that section's rules. However, the source-selection rules name the default
  Overview and Additional context sections. The specs record this as the one exception.
- **A lower-case rule body.** The blind part of "Datasets by name, cited once" starts with a
  lower-case word.
