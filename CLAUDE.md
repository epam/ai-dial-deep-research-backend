# CLAUDE.md — dial-deep-research

DIAL Deep Research: a per-request LangChain tool-calling agent over a generic-RAG MCP server.
Python 3.13, `poetry`-managed, `src/` layout.
The `Makefile` has the targets `make format`, `make lint` and `make test`. `make help` lists all
targets.

## Never commit sensitive info

@no_sensitive_info.md carries the whole rule and stands on its own: what must never appear, which
generic placeholders are allowed, and what to check before handing work over. It is also what the
`scripts/check_sensitive_info.sh` checker judges a staged diff against, so keep it self-contained.

## Safety review before every commit

Before every commit, run the `pre-commit-safety-check` subagent on the staged changes, and commit
only when its verdict allows it. Pass it, in the prompt, every client name, server or tool name,
dataset id and private path seen in the session, because the subagent cannot see the session. If
the verdict reports a problem, fix it and run the subagent again before committing.

## Rules for coding agents (Claude Code, etc)

- When you refer to a rule of a Deep Research quality policy, always give the policy name, the
  rule number (if the rule has one) and the rule name, for example: Source selection, rule 2
  "Every current value, with its own source". Never refer to a rule only by its number.
- Use simple, clear and precise wordings, also in comments, docstrings, commits and pull requests.
  Never use abstract and vague ones. Name the real thing instead of a category, prefer one plain
  sentence to a chain of qualifiers, and cut words that carry no fact.
- Abstraction is not a cure for wording that is too tied to today's implementation. Blurring it
  ("an agent loop", "the relevant component") only trades a dated sentence for a hollow one.
  Instead state plainly the part that stays true, and keep the precise mechanics in the place
  whose readers need them — a spec, or a comment next to the code — rather than watering them
  down everywhere. A docstring or a config description should tell its reader what to do with
  the thing; internals belong where they are implemented.
- If not sure, ask questions. Do not make design decisions based on your assumptions.
  Except for cases when user explicitly asks you to work autonomously or make decisions yourself.
  Do not ask when a principle of the Deep Research constitution settles the case.
- Do not cite design docs or other code without naming the source.
  The user is not an LLM and does not remember every document.
- Do not present plausible reasoning as an observed fact. Anything about how a dependency,
  runtime or protocol actually behaves is a guess until checked, however sound the reasoning
  that produced it — especially quantitative claims: what counts as one unit, what scope a
  limit applies to, how many X fit into one Y. Before such a claim goes into code, a comment,
  a spec or docs, run the cheapest decisive check: read the installed source under `.venv/`,
  or write a ~10-line probe that measures the behavior directly. Two real examples: a
  framework limit assumed to span a whole run while it is in fact applied to each nested call
  separately; a batch of N parallel operations assumed to cost N units while it costs one.
- **Work on OpenSpec changes only through the OpenSpec skills** (`.claude/skills/openspec-*`):
  creating, updating, applying, verifying, syncing and archiving a change each have one, and a
  skill that tells you to run another skill means invoking it, not reimplementing what it does.
  Hand-rolling a step skips rules that live only in the skill — the merge semantics in
  `openspec-sync-specs` are the easiest to miss, since `openspec archive` also updates the main
  specs and the two describe a partial `## MODIFIED` block differently.
- Keep a single source of truth, and mind staleness (docstrings, comments, READMEs and similar).
  Keep each fact — a concept, rule, mode, or concrete detail like a URL format, path, or name —
  in the one place that owns it, usually the code that implements it. Do not restate it in
  distant prose, which silently drifts when the place that owns it changes. Duplicate only with
  a clear reason, such as a user-facing schema description that must stand alone.
- Cross-reference sparingly, and only when motivated: a `see X` earns its place only when it
  saves the reader real work, and it too goes stale (X gets renamed or moved). Prefer describing
  a fact where it lives over pointing at it from afar. When unsure whether a reference or a copy
  will age worse, prefer neither and say less.
- Reread your draft and ask which sentences you verified and which you inferred. Check the
  inferences, or say plainly that they are unverified — do not state them flatly. A claim about
  to be copied into several places (a spec, a field description, a README) is worth the check
  twice over, since a wrong one then has to be corrected in every copy.

## The Deep Research constitution

The standing principles for design decisions about Deep Research. When a principle settles a case,
decide without asking, and name the principle. The instruction of the person you work with comes
first, then the OpenSpec specs and the output-quality policies, then this section. Report a
conflict between them to the person you work with.

1. **Correctness first.** A correct report outranks work already done: redo work rather than risk
   misleading the reader.
2. **Nothing made up.** Do not make up what the sources do not state.
3. **Do not overfit.** Deep Research serves questions we cannot foresee. A rule states general
   behaviour, and a change made for one case is weighed by its effect on other cases.
4. **Broad rules first.** Phrase a rule as broadly as it can be without losing precision. Narrow it
   only for a stated reason, such as a run that shows the problem.
5. **Leave room for judgment.** A rule decides the scenarios that we can decide in advance. It does
   not try to decide every scenario, because:
   - we cannot foresee every scenario;
   - in some scenarios, the right choice depends on what the sources hold, for example which near
     match to give;
   - in some scenarios, it depends on the intent of the query, for example which frequency to use;
   - an LLM follows a few clear rules more reliably than many exact ones.

   In such scenarios, the rule states the goal and lets Deep Research choose what is most
   appropriate for the query. Example: when the query names no frequency, Deep Research chooses the
   frequency that is most appropriate for the query.
6. **Sources change.** Do not assume that a source's data, metadata, identifiers or tools stay as
   they are today.
7. **Generic core.** Deep Research stays client-agnostic. What depends on one client belongs in that
   client's application properties.
8. **Each component owns its concern.** Do not build into Deep Research what another component is
   responsible for, and do not make other components depend on Deep Research internals.
9. **Failures stay contained.** A failing check or optional step does not fail the other checks or
   the rest of the pipeline.
10. **Judge by the final report.** Judge a change by the whole final report, checked against the
    sources, not by an intermediate step such as the plan.
11. **The user knows what happens.** Deep Research tells the user as early as it can what it will
    not do for a request, for example during preparation. It also tells the user when a run fails
    and cannot recover.

The section "Writing prompts" has the rules for prompts.

Change this section only with the agreement of the person you work with. Propose a principle
when a correction shows a standing decision that is not written yet.

## Writing prompts

These rules apply to every LLM call: its prompt text (system prompts, tool descriptions, tool
responses and injected prompt text), its structured-output schemas and field descriptions, and the
spec that describes the call.

- **Keep prompts lean.** Add an instruction only when it is needed, and remove one that another
  instruction already gives. Otherwise prompts grow with every change.
- **Make every instruction explicit.** Give each case its own sentence that names the case and
  says what to do. Do not make the model resolve a reference such as "keeps none", "neither does"
  or "as the rules above say", and do not give an instruction only through an example. A model
  that has to work out what an instruction means follows it less reliably.
- **Write new and edited prompt text in Simplified Technical English (ASD-STE100) at about 70%.**
  Apply its writing rules and relax its dictionary. Text that a change does not touch stays as it
  is. The writing rules:
  - Write one instruction in each sentence.
  - Keep an instruction to at most 20 words, and a description to at most 25.
  - Use the active voice.
  - Put the condition before the instruction: "When X, do Y". Write three or more conditions or
    exceptions as a list.
  - Keep "a", "an" and "the". Do not stack nouns.
  - Repeat the noun when a pronoun could point at two things.
  - Use a single verb instead of a phrasal verb or an idiom: "omit", not "leave out".
- **Write a prompt as a triple-quoted multiline string.** Do not join adjacent or parenthesized
  string literals. Do not escape a newline with a trailing backslash to join wrapped lines: let a
  long line wrap as a real newline, which is harmless inside an LLM prompt. Keep each source line
  within 100 characters. A leading `"""\` that avoids a blank first line is fine. This keeps the
  prompt text readable and its diffs small.
- **Wrap injected prompt content in XML tags.** Any value the app substitutes into a prompt that
  is long, multi-line, or carries formatting of its own — a report draft, the rendered section
  structure, a findings log, the user's question, a plan, a topics map — goes inside a named tag
  (`<draft>…</draft>`, `<report_structure>…</report_structure>`). The tags mark where the value
  begins and ends, so its headings, bullets or numbering cannot be read as part of the
  instructions around it. Use lowercase snake_case tag names that say what the value is. Short
  scalars — a word count, a ceiling, a comma-separated list of names — stay inline; a tag around
  a number is noise. Do not wrap a tool message that the agent must repeat verbatim to the user,
  because the tag can leak into the reply.
- **LLM structured-output schemas put the verdict last.** Put a decision or verdict field after
  the supporting content that justifies it. The model emits fields in schema order, so a schema
  that puts the reasoning first yields better decisions. Examples: `questions` before
  `sufficient`; `revised_plan` or `problems_found` before `approved` or `verdict`. Order the
  supporting fields by logical precedence: a precondition check comes before a check that matters
  only once the precondition holds, such as `recorded_plan_matches` before `user_approved_a_plan`.
  Pydantic v2 allows a required field after defaulted ones, so the order is free.
- **Every LLM call states its inputs and outputs in the spec that owns it.** When adding an LLM
  call or changing what an existing one receives, write it down: which system prompt and what
  fills it, which messages (and whether history is full, filtered, or rendered to text), whether
  image content is included, which tools are bound, and what comes back (free text, a structured
  schema, or tool calls only). Name the deliberate omissions too — "this call does not receive
  the findings" is part of the contract. Inputs are the one thing about an LLM call that code
  review reliably misses. For example, a review call that judges how well the report covers its
  images, but does not receive the images, looks correct in the diff and is wrong in production.
  Nothing fails when a refactor quietly changes what a prompt sees.

## Sending a query to the DR server

Use `scripts/send_conversation.py` to drive a chat with the app from the CLI. The server is
**expected to be already running**; the script does not start it. The base URL and API key
come from the app settings (`.env`); the target deployment is the application instance
registered in DIAL Core, passed via `--deployment`.

The conversation artifact file *is* the `messages` array, so multi-turn state threads verbatim.
Two modes:

- `overwrite` — clear the file and start fresh with just this query
- `continue` — load prior messages from the file, append this query, send, append the reply back

Every turn's full response is also stored in `<stem>.raw.json` next to the messages file, one
entry per turn: the query, the whole response in the blocking shape (including fields outside the
message such as `statistics.usage_per_model`), and an `error` that is set when the turn failed. A
failed turn is recorded there with whatever arrived before the failure.

```bash
# fresh conversation
poetry run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite -d deep-research-acme
# follow-up turn, threading prior state
poetry run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue -d deep-research-acme
```

Override `--timeout` as needed.

## Conventions

- **No new aliases on pydantic-settings fields** — rely on the default field-name → env-var mapping (with the class's `env_prefix`). E.g. `heartbeat_interval` under `env_prefix=""` reads `HEARTBEAT_INTERVAL`.
- **Logging follows the `logging-policy` spec** (`openspec/specs/logging-policy/spec.md`):
  level semantics with a single-ERROR ownership rule, the INFO request skeleton, and the
  content allowlist — log structure (names, counts, durations, ids, outcomes), never message
  bodies, tool arguments, response bodies, header values, or URL query strings, at any level.
  Payload records exist only behind `LOG_PAYLOADS`.
- **Keep the README environment-variables table in sync with the settings.** Update it whenever an env var is added or removed (required or optional alike), and whenever a var's required/optional status changes.
- **Update `dial_conf/core/applications-template.json` in the same change whenever the required application properties change.** Adding, removing or renaming a required field of `ApplicationProperties` (`src/dial_deep_research/app_properties.py`), and making an existing field required or optional, each means editing every instance in the template so it again sets exactly the required properties — `tests/test_app_properties.py` fails until it does. Nothing else goes in: the template is an example of the config file's shape, so a property that has a default stays out of it. The one exception is a property that has a default but that the instance fails validation without, because a validator requires it or an alternative to it: a `generic_rag` server must set `description` or `document_stats`, so the template sets `description`, the one that needs no running server. Never copy a default in, because `make infra-config` seeds a contributor's `applications.json` from the template and a copied default pins that channel to the value it had at seed time. The requirement is specified in `openspec/specs/local-stack/spec.md` ("Local application instance config seeded from a committed template").
- **The application-properties reference is the model and the generated schema, nowhere else.** `ApplicationProperties` owns every property, its description and its default; `make format` regenerates `docs/generated-app-schema.json` from it and `make lint` fails on drift. Field descriptions live in the pydantic schema (`Field(description=...)`). The README core-config snippets are updated by hand.
- **Keep `docs/architecture.md` up to date with the runtime flow.** It is a map over
  `app/preparation/` and `app/research/`: the turn structure, the node graphs, and their
  diagrams. When a change alters a node, an edge, a routing condition, a state field, or a
  turn-boundary behavior (what starts a turn, what ends it, what persists across turns), update
  the affected diagram and prose in the same change — don't leave it for later. Write for a
  reader who has neither this codebase's context nor the change history: name the current
  behavior plainly, never how it changed ("previously", "now", "instead of"). The
  [OpenSpec specs](openspec/specs/) stay the one place that owns a requirement's full wording;
  this page links to the spec section and quotes only the short excerpt needed for the diagram,
  never restates a rule at length — a rule duplicated here goes stale the moment the spec changes
  and no one edits both.
- **Never name a list-element field `index` in anything persisted to `custom_content.state`.** The DIAL SDK's chunk-merge (`aidial_sdk.utils.merge_chunks` / `_indexed_list`) treats any list of dicts whose elements carry an `index` key as an OpenAI-style indexed streaming delta — it re-slots the elements by `index` and strips the key, corrupting the stored value (a 1-based list comes back as `[{}, {…}, …]` with the key gone). Use another name (e.g. `number`) for an ordinal field on a persisted list element.

## Code Style

- write clean and reusable code, though don't over-engineer. code should be appropriate for the task
- prefer modern python, with type hints
- always use pydantic models instead of dicts and unclear data structures, unless it introduces unnecessary complexity
- after editing code files, always run `make format` and `make lint`
- use kwargs whenever possible instead of positional arguments - this improves readability.
  Note that some functions and methods have positional-only arguments - it's ok.
- use comments to explain non-obvious code. don't write comments that restate the code.
- **no `assert` in application code — raise an exception.** Python drops `assert` statements when it
  runs with `-O`, so a check written as one disappears where it was meant to hold. Raise an
  exception whose message says what went wrong instead. Tests keep pytest's `assert`.
- **comments describe the code as it is, never how it changed.** no "instead of X", "the old
  rule", "previously", "no longer", "this used to". a reader who does not have the diff cannot
  use such a comment, and it goes stale the moment the next change lands — the reason a rule
  exists is durable, the thing it replaced is not. write the rule and why it holds: not
  "keying on the segment rather than on whether a tool ran", but "every chunk of one message
  carries the same id, so a change in it means a new segment". this covers docstrings and test
  names too: a test asserts current behavior, not the absence of a past bug.
- when writing docstrings, be concise
