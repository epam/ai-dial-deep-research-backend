## Context

See proposal.md — Why. What matters for the approach is the shape of the code today:

- `research/graph.py` compiles `START → researcher → reviewer → (researcher | report) → END`,
  three nodes, all routing decided in Python.
- `make_report_node` (`research/nodes.py`) streams one LLM call and returns
  `{"report": text, "messages": [AIMessage(content=text)]}`. It sees `state["messages"]` (the
  whole research transcript), the aligned query, and the plans.
- `ResearchRunner` (`research/runner.py`) forwards only the report node's token chunks into the
  DIAL choice (`metadata["langgraph_node"] == "report"`), and unconditionally prepends `"\n\n"`
  before the first of them. It takes the slice it persists from the graph's final `values`
  state.
- DIAL content is append-only (`Choice.append_content`); nothing streamed can be retracted.
  This is the constraint that decides the streaming question: a draft that may still be
  revised cannot be streamed.
- The preparation agent is a `create_agent` loop whose tools mutate a closure-held `PrepState`.
  After `start_research` returns, the loop routes back to the model, which writes the
  "research is starting" sentence that lands ahead of the report.
- `ApplicationProperties` generates the DIAL application-type schema; `_inline_root_refs`
  inlines root `$ref`s and raises on anything deeper.

## Goals / Non-Goals

**Goals:**

- The word ceiling is enforced by measurement and rewriting, not by asking a model to count or
  by cutting text off.
- The report rules live in one place per rule: the section structure in configuration, the
  ceiling in configuration, the enforcement in the review step's prompt.
- The launch turn's answer is the report and nothing else, guaranteed by control flow rather
  than by prompt wording.
- The loop is cheap to disable (`max_report_revisions: 0`) and never fails a turn over a
  formatting verdict — a completed multi-minute research run is not discarded.

**Non-Goals** (deferred acceptance criteria of issue #32, and neighbours):

- **User-requested format overriding the default — deferred to issue #45.** (Issue #32's third
  acceptance criterion; proposal.md quotes it.) The decision needed first is where a user
  instruction belongs. The query holds the active user
  question plus the answers to clarification questions; the plan holds how the question gets
  answered. Formatting instructions read naturally as part of the plan, since they describe the
  process of answering rather than the question — but putting user instructions in the query
  has its own argument: an unclear instruction ("format the response as a table") deserves a
  clarification round ("what should the table contain?"), and only the query path can raise
  one. The cost of the query path is that `update_query` re-runs the clarity check on an
  already-clear query, which is stochastic and can re-open settled questions.
  Whichever side wins, the current graph has a further problem: the plan is consumed by the
  researcher and the research reviewer, and a formatting instruction means nothing to either —
  that is issue #45's observed bug, where "answer in two sentences" became a research step the
  reviewer kept reporting as outstanding. Splitting query and plan into research instructions
  and report instructions fixes today's two kinds and nothing beyond them; the general answer
  is a more agentic research stage that can route an arbitrary instruction to whichever step
  owns it. That needs its own discussion, so this change leaves the report node reading only
  the configured default structure.
- **Per-node instruction scoping — recorded here for the discussion that owns it, not built.**
  A cheap partial answer to the routing problem above: give every node a line telling it which
  user requirements are *not* its business. `research-agent` and `research-review` would ignore
  report formatting requirements — which alone would fix issue #45's observed bug, where
  "answer in two sentences" became a research step that research-review kept returning as
  outstanding work. The report nodes would ignore instructions about where to look for data,
  since they do no research.
  Two constraints on that idea, which is why it needs its own discussion rather than a quick
  prompt line here. First, the report nodes must **not** ignore report-related instructions
  wholesale — the scoping is "do not go and research", not "disregard what the user asked the
  report to be". Second, the report must still say when the research deviated from the approved
  plan or when data the plan required was not found; a node told to ignore research concerns
  must keep reporting on research *outcomes*, or that silence becomes a new failure mode where
  a report reads as complete over findings that are not.
- **Configured glossary** (issue #32's sixth acceptance criterion). Expected to arrive as an MCP
  tool on the statgpt MCP server rather than as application configuration, and its presence is not
  guaranteed. Separate feature.
- **Clickable table of contents** (issue #32's seventh criterion, marked optional there). Of
  little value at a five-page ceiling.
- **Citation correctness and completeness (issue #35) and output guardrails (issue #36).** Both
  want a pass over the finished report and both are natural additions to this loop's criteria
  later. This change adds the loop and the issue #32 criteria only, so the two issues stay
  independently reviewable.
- No minimum report length, and no per-section word budget. The ceiling is a ceiling.

## Decisions

### Every node is renamed to say which stage it belongs to

The four nodes are `research-agent`, `research-review`, `report`, `report-review`. Today's
`researcher` and `reviewer` are renamed: `reviewer` becomes ambiguous the moment a second
reviewer exists, and `researcher` reads like the whole research graph rather than the
tool-calling agent inside it. Hyphens are legal — langgraph rejects only `|` and `:` in node
names (`langgraph/_internal/_constants.py:87,89`, enforced at `graph/state.py:797`) — so the
node ids are hyphenated while the Python factories that build them keep underscores
(`build_research_agent`, `make_research_review_node`, `make_report_review_node`,
`route_after_research_review`, `route_after_report_review`).

The node id is user-visible in the places that matter for debugging: Opik trace spans, the
`langgraph_node` stream metadata, and the agent-logging label — which moves from `researcher`
to `research-agent` with it.

**The rename has to reach every spec that names a node id**, or a spec ships naming a node that no
longer exists. Within `research-execution` that means the requirements written in role language
("the researcher node SHALL be…", "the reviewer node SHALL be…") are renamed too — leaving them
would put both naming schemes in one file, which is the ambiguity the rename exists to remove.
Requirement **headings** keep the old wording wherever they carry it ("Requirement: Researcher
investigates…", "Requirement: Reviewer independently judges…", "Requirement: Researcher prompt
discloses the image budget", "Requirement: Prefix-stable reviewer prompt assembly") for a mechanical
reason: OpenSpec matches a `MODIFIED` block to its original by heading text, so renaming a heading
would orphan the delta and leave the original requirement in place at archive time. Only bodies and
scenario names are renamed. Renaming the headings is a follow-up for whoever is willing to use
`RENAMED Requirements`, which OpenSpec supports for name changes only.

The sweep covers every spec that names a node id: `research-execution` (all of it),
`dial-agent-with-mcp`, `image-budget`, and `prompt-caching`. Nine requirements are carried as
`MODIFIED` purely for the rename, with no behavior change — verbatim copies with node names
substituted.

Alternative rejected: **keep `researcher`/`reviewer` and add only `report-review`.** Fewer
lines changed, but it leaves the codebase with `reviewer` and `report-review` side by side,
where only one of them says what it reviews.

### One report node writes both the draft and the revisions; a separate node reviews

The graph becomes `… → report → (report-review | END) → (report | END)`. The `report` node branches
on **whether a previous draft exists** — `state["report"]` is set. That is *not* the same test as
`revisions_used > 0`: the counter is still 0 while the first revision is being written (it increments
in that call), so branching on it would send the first revision down the first-draft path, which is
the failure this branch exists to avoid. Branch on the draft, not the counter. With no previous
draft the node writes the first one; with one, it rewrites it. `report-review` is a structured LLM
call whose only output is the findings list; there is no separate approval field, so an empty
list is the approval. That closes off "approved, but here's a minor note" as a shape the schema
can express — a finding always forces a revision, whatever the model would have called it.

The branch is deliberately **not** "are there revision instructions", because a revision can be
forced with none: when the review model approves a draft that the measured count says is over the
ceiling, Python overrides the verdict (see the ceiling decision below) and there are no model
findings to rewrite against. In that case the app renders the instruction itself — the previous
draft, its measured count, the ceiling, and "shorten to fit by rewriting, not cutting". When both
apply, the model's findings and the app's length instruction are merged into one instruction. So a
revision always arrives with something concrete to act on; a `report` call that saw only an
unchanged prompt would reproduce the same over-long draft and spend a revision doing it.

Counter semantics, pinned because two nearly-identical numbers exist: `revisions_used` counts
**revisions written**, so it is 0 after the first draft and increments only when the node runs with
a previous draft present. Routing continues while `revisions_used < max_report_revisions`, giving
`max_report_revisions + 1` report calls at most. The logged draft ordinal is `revisions_used + 1`,
so the first draft logs ordinal 1.

**The last draft is reviewed too, even though its verdict cannot be acted on.** With a budget of 2
that is 3 drafts and 3 reviews, not 3 and 2. Skipping the final review would save one call per turn,
and it is deliberately not skipped: the verdict on the draft that actually ships is the only way to
learn whether delivered reports satisfy the checks, which is what the budget default and the review
prompt get tuned from. A review call is also the cheap one in this loop — it carries the draft, not
the transcript.

Two budgets, never shared: `max_research_iterations` bounds research-agent ↔ research-review, and
`max_report_revisions` bounds report ↔ report-review. They are separate properties because the loops
cost different amounts and are tuned independently.

Alternatives rejected:

- **A dedicated `report_revise` node.** Two nodes would duplicate the same prompt assembly,
  the same transcript, and the same stream-drop retry, differing only in one appended message.
- **A tool-calling report agent that reviews itself.** Self-review of one's own output is
  weaker than an independent judge, and the repo already pays for independence in the research
  reviewer for exactly this reason. It would also put the loop back under model control, which
  the research-execution spec deliberately keeps in Python.
- **A LangGraph subgraph for the report loop.** The recursion limit is applied per graph run
  (`max_research_graph_steps`), so a subgraph would get its own budget — extra indirection for
  no gain, since the outer graph's length is already bounded by the revision budget.
- **A separate `approved: bool` field alongside `findings`.** Lets the model approve a draft
  while still leaving a note. Rejected: a model that hedges this way is common, not an edge case,
  and the field only widens the disagreement the app already has to arbitrate (the ceiling
  override shows the app overrides the model's opinion regardless). One field, findings-empty-is-
  approval, means there is nothing to disagree with.

### Report-review reads the report, the config and the query; the reviser also reads the findings

`report-review` receives the draft text, the configured structure, the protected sections, the
measured word count and the ceiling, and the research question and plan — and **not** the
research transcript. Every issue #32 criterion (sections present and ordered, length, prohibited
annotations, citation format, protected sections intact) is decidable from those, so sending the
transcript would multiply the cost of the cheapest node in the loop for nothing. This is also
what keeps the spec's "review cannot reopen research" rule honest: a judge that cannot see the
findings cannot form an opinion about coverage.

The query and plan are in there for one reason: they are where a user's formatting instruction
lives today, so without them the step cannot distinguish a draft that followed a legitimate
request from one that overrode a protected rule. They are two short strings — the transcript they
came from is what stays out.

Its user message is ordered **stable content first, draft and measured count last**, for the same
reason research-review's is: those two are the only parts that differ between the review calls of one
run, so putting them last leaves everything before them as a shared byte prefix. The
**prompt-caching** requirement this change adds covers both the report revision and report-review.

The `report` node keeps the full transcript on a revision, because a revision may need to
re-ground a passage it rewrites, and because reusing the first draft's exact prompt prefix lets
the provider's prompt cache serve it. The revision request is **appended after** the original
`REPORT_REQUEST` message rather than replacing it, so the byte prefix is unchanged. The
**prompt-caching** capability had no requirement covering this — its only prefix requirement is
scoped to the reviewer's user message — so this change adds one for report revisions, in the same
shape.

Alternative rejected: **revise from the draft alone.** Cheaper, but a reviser with no findings
can only shuffle words — it cannot fix a passage whose citation is wrong or restore detail it
condensed too far.

### A token cap is not an option — measured, not assumed

Measured, one short generation prompt issued at output-token caps of 10/50/100/200/500 plus an
uncapped baseline, on the model this app uses by default:

- **Every capped call returned `finish_reason="length"` and its text ended mid-sentence.** The model
  does not wind the answer up as it approaches the cap; the response is cut where the budget runs
  out.
- `max_tokens` (deprecated) and `max_completion_tokens` behave identically — both resolve to the same
  upstream parameter, with the same truncation.
- A cap below 16 is rejected outright with an HTTP 400 naming a minimum, so a very small cap is an
  error rather than a very short answer.
- The uncapped baseline stopped on its own (`finish_reason="stop"`) at roughly **0.78 words per
  output token** of prose — the figure to use if a token cap is ever wanted for some other purpose.
- The model tested reports no reasoning tokens, so this says **nothing** about how a cap interacts
  with a reasoning model: whether reasoning could consume the budget before any visible text appears
  is untested and remains open.

A cap therefore produces exactly the abrupt truncation issue #32 forbids, which is why the ceiling
is enforced by review-and-revise and no token cap is set. One incidental lesson for the
implementation: a "does it end on sentence-final punctuation" check is not a truncation detector —
one capped run ended on a period and was still cut mid-scene. `finish_reason` is the reliable
signal.

### Word count is `len(text.split())`, computed in Python and stated as a number

Whitespace-separated tokens over the report Markdown: one definition, used in the review
prompt, in the revision instruction, and in the log event, so the three never disagree. It counts
Markdown syntax as part of the text — every table pipe, heading hash, and bullet dash scores as a
word — so it overstates prose length, by an amount nobody has measured and which grows with how
many tables a report carries. Accepted anyway: the alternative (stripping Markdown before counting)
adds a dependency and a second definition of "the report's length", and the ceiling is an
approximate budget, not an accounting figure. Worth measuring once on a real report before the
default of 2,750 is tuned, since a table-heavy report reaches the count sooner than its prose
would.

No `count_words` tool is exposed to any model: the count is an input, not something to ask for.

Alternative rejected: **token count instead of words.** The issue states the ceiling in words
and pages; tokens would need translating for whoever configures the property.

### No streaming of the report; the delivered text is appended once

The report node keeps `astream` internally — it preserves the existing transient stream-drop
retry semantics (`STREAM_DROP_MAX_ATTEMPTS`) and avoids one long idle request — but its chunks
no longer reach the DIAL choice. `ResearchRunner` drops the `"messages"` stream mode and its
`_handle_message_chunk` handler, takes the settled report from the graph's final `values`
state, and appends it in one call. Tool stages continue to appear throughout research, and the
SDK keep-alive (`HEARTBEAT_INTERVAL`, default 5s) covers the report loop's quiet stretch.

The `"\n\n"` separator becomes conditional: `completion.py` tells `ResearchRunner` whether the
preparation stage appended any content this turn. With the silent hand-off below it normally
did not, so the report starts at the first character.

Alternatives rejected:

- **Stream drafts into a DIAL stage.** Useful while tuning prompts, but it shows end users
  rejected drafts, and the review verdict then needs a stage of its own to make sense of them.
  Cheap to add later behind a setting if tuning turns out to need it.
- **Stream the first draft and treat revisions as appended corrections.** Append-only content
  makes this incoherent — the user would read the rejected text followed by its replacement.

### The report-review node reports its own review, through a callback the runner supplies

The node owns both records for its review — the DIAL stage and the log line — and reaches the stage
through a **stage-emitting callback** passed into `make_report_review_node`, not through the DIAL
`Choice` itself. The runner builds that callback (it holds the `Choice`) and the graph is constructed
per turn inside `ResearchRunner.run`, so passing it in costs nothing new.

Why the node and not the runner: the node already owns this event's log record (see
**logging-policy**), and it already has the duration, the counts, the findings and the verdict in hand.
Splitting one observability concern — same numbers, same moment — across the node (log) and the runner
(stage) means deriving those numbers twice, in two files, free to disagree later.

Why a callback and not the `Choice`: `research/nodes.py` imports nothing from DIAL today, and every
`create_stage` call in the repo sits in a runner (`research/runner.py`, `playground/runner.py`,
`preparation/runner.py`). A narrow callback keeps that boundary — the node decides *what* to report,
the runner decides *how* it is rendered as a DIAL stage — and it keeps the node testable with a plain
fake instead of a `Choice` stub.

**How the `Choice` is passed: it isn't.** It stays in the runner, captured by the runner's own bound
method; only the callback crosses into the graph, threaded through the existing per-turn construction
path:

1. `ResearchRunner.run` already holds `self._choice` and already builds the graph per turn
   (`runner.py:76`), so it passes its own bound method — say `self._emit_report_review_stage` — into
   `build_research_graph(...)`, alongside the per-turn values that function already takes (`tools`,
   `today_date`, `client_name`, `max_iterations`).
2. `build_research_graph` forwards it to `make_report_review_node(...)`, which closes over it exactly as
   the other node factories close over `today_date`.
3. After its review call the node invokes the callback with one structured value — a small pydantic
   model carrying the draft number, the measured word count, the ceiling, the findings, the outcome and
   the duration — rather than a dict, per the repo's convention.
4. The runner's method formats the title and body and writes the stage:
   `with self._choice.create_stage(title) as stage: stage.append_content(body)`. Both are sync
   (`aidial_sdk/chat_completion/choice.py:183`, `stage.py:62`), so the callback is a plain sync
   callable — no `await` in the node for it.

The model and the callback type live beside the node; the runner imports them, which is the direction
imports already run (`runner.py` imports from `.graph`, `.state`, `.tools`). Nothing DIAL-shaped appears
in `nodes.py`, and a test supplies a collector function in place of the runner's method.

Alternatives rejected:

- **Put the `Choice` in the graph state.** It works today — `builder.compile()` has no checkpointer, so
  nothing serializes state — but a `Choice` is a per-run *dependency*, not per-run *data*. It would ride
  along in every `values` stream payload the runner consumes, it would have to be threaded through
  `build_initial_state`, and it breaks the day a checkpointer is added.
- **`context_schema` + `Runtime[Context]`**, the framework's own mechanism for run-scoped dependencies
  (`langgraph/graph/state.py:181-184`). Correct and typed, and the right answer if more nodes ever need
  run-scoped dependencies; more machinery than one callback for one node, and it still puts DIAL types
  in the graph's type signature.
- **The runner renders the stage from the node's state update** (the first draft of this design). Keeps
  DIAL strictly in the runner, but re-derives the draft number, the counts and the elapsed time that the
  node just computed for its log line.

### Drafts stay out of `state["messages"]`; the runner builds the persisted assistant message

The report node writes `report` (and the revision counter) into the state and appends nothing
to `messages`. `ResearchRunner` takes the final `report` from the graph's final state and adds
the assistant message to the slice it persists. Otherwise every rejected draft would be
persisted into `custom_content.state["messages"]` and re-sent to the model on each revision.

### The preparation loop is ended by middleware, not by the prompt

A `before_model` hook that returns `{"jump_to": "end"}` when the closure-held `PrepState` has
`research_started` set. It fires only after `start_research` has actually passed its gate, so a
gate-rejected call is untouched and the agent still relays the failure to the user. Verified
against the installed langchain: `JumpTo = Literal["tools", "model", "end"]` and the
`@before_model(can_jump_to=["end"])` form are present in
`.venv/.../langchain/agents/middleware/types.py:66,905`.

The prompt changes too — the launch step drops "then tell the user that research is starting", and the
`RESEARCH_READY` tool result says the hand-off is automatic — but the guarantee is the
middleware's.

Alternatives rejected:

- **`@tool(return_direct=True)` on `start_research`**, the pattern `finish_iteration` uses.
  Verified unusable here: the exit is decided by the tool's static `return_direct` attribute,
  with the ToolMessage's error status never consulted
  (`.venv/.../langchain/agents/factory.py:1935`), so a gate-rejected `start_research` would
  also end the loop — leaving the turn with no answer at all.
- **Prompt only.** Was the first choice, dropped once the middleware turned out to be a few
  lines: a stochastic model asked to stay silent will sometimes speak, and "the response contains
  nothing but the report" is the first thing issue #32 asks for.
- **Buffering or suppressing the text in `PrepAgentRunner`.** Fixes the symptom downstream of a
  model call that was made and paid for anyway, and buffering costs the live streaming of
  clarifying questions.

### Structure is configured as a list of `{name, description}` sections

`default_report_structure: list[ReportSection]`, each section carrying the heading to render
and a description of what belongs in it. The `default_` prefix names it for what it is: the
structure used when the user asked for nothing else — the override is issue #45's.

Alternatives rejected:

- **A free-text structure block** (like `data_sources_descriptions`). More expressive, but
  nothing then guarantees a section list the review step can check mechanically, and the
  reviewer would be judging prose against prose.
- **A bare `list[str]` of section names.** Cannot say what belongs in a section, which is the
  part that actually shapes the report; a deployment renaming "Key Findings" to "Executive
  Summary" needs to say what changes about its content.

### `ReportSection.protected` declares protection, with a validator as the floor

`ReportSection` gains `protected: bool = False`. The shipped default marks References protected;
a deployment may protect sections of its own (a regulatory disclaimer, a methodology note), and a
model validator requires **at least one** protected section, so no configuration can produce a
report whose every section a user instruction may remove.

This replaces an earlier draft where the app appended a references section unconditionally,
whatever the configuration said. That version cannot coexist with the single-home rule below: an
app-appended section needs a name and content rules of its own, which is exactly the per-section
instruction living outside `ReportSection` that the rule forbids.

**What this softens, deliberately, and accepted:** an admin editing `default_report_structure` can
now ship a structure with no references section at all, as long as something else is protected.
The protection is against the *end user*, who is anonymous and arbitrary; the deployment admin
already controls every prompt input there is (`client_name`, `data_sources_descriptions`, now the
section descriptions), and application properties are maintained with care. The `≥1 protected`
validator is what remains of the old guarantee, and that is the intended level of protection —
not an oversight to be tightened later.

Alternative rejected: **a semantic flag** (`carries_source_tables: bool`) so the app could require
a sourcing section specifically. It restores the hard floor, but it makes the app reason about
what a section *means*, and a deployment could satisfy it with a section that decodes nothing.

### A section's description is the only place its rules live

Everything about a section — purpose, contents, rendering, any table columns — lives in its
`description` and is passed verbatim to both the report writer and `report-review`. The
consequence worth stating: the source-table rules move **out** of `REPORT_SYSTEM_PROMPT` and into
the default References section's description.

The line between a section rule and a report-wide rule: the word ceiling, the prohibited
meta-annotations, and the **inline citation format** stay report-wide, because they govern every
section's body rather than one section's content. Only the decoding of citations is a section's
business, and the references description owns the entry format for every source type — documents
and datasets alike.

The inline format has a second, harder reason to stay put: DIAL chat will render citations from
it, which makes it a machine-readable interface rather than a style choice. A configurable
interface is a broken renderer waiting for a config edit, so it is non-configurable by
requirement, in both **research-execution** and **report-composition**.

Without this rule, changing a section means editing a prompt, a config default, and two spec
paragraphs, and they drift; with it there is one place to change and one place to look.

### Protected sections are named in both prompts, next to the instructions they outrank

Both the report prompt and the `report-review` prompt carry the same three things in the same
place: the configured sections with their descriptions, the research question and plan (where a
user's formatting instruction lives), and an explicit list of the sections and rules that no
instruction in those two may drop or restyle. Stating the protection *beside* the text it
outranks is the point — a rule in the system prompt and an instruction in the user content are
otherwise two claims with no stated precedence, and the model picks.

The protected set is a concept with one member today (references, and its citation formats).
Enforcement is at two points, as above: the writer is told, and the reviewer checks. Neither
alone is sufficient — the writer is stochastic, and a reviewer with no rule to check against
would be judging taste.

Note for the implementer, since this is easy to get backwards: **the report writer receives every
report rule up front** — the configured sections with their descriptions, the word ceiling, the
protected sections, the prohibited annotations, the citation format. The review loop is a
backstop, not the mechanism: a writer told none of this would fail its first review almost every
time, spending a revision on rules it could have followed at the first attempt.

What the writer does *not* get is a rule elevating a **user-supplied** format request to
something it must satisfy. That is issue #45's, and adding it here would quietly implement the
acceptance criterion this change defers. The query and plan are in the writer's prompt regardless
(they are today), so a request in them may still influence a draft — unreliably, exactly as now.
The change here is only that protected sections and rules are stated as outranking them.

Alternatives rejected:

- **Strip formatting instructions out of the query and plan before the writer sees them.**
  Requires classifying arbitrary user text into research and formatting intent — the very
  problem issue #45 exists to solve — and would silently drop legitimate instructions.
- **Post-process the report to re-attach a dropped references section.** Deterministic, but a
  report written without references has usually shed the citations too, so there is nothing to
  attach; the section has to be written, not stapled on.

### `max_report_revisions` defaults to 2, and `0` skips the review entirely

Two revisions bound the loop at three report calls plus two review calls in the worst case,
against a run that has already spent far more on research. `0` is an explicit off switch that
skips the review call as well, so a deployment that finds the loop not worth its cost pays
nothing for it.

## No changes required

- `app_properties.py`'s schema generation (`_inline_root_refs` / `_inline_refs`) already
  handles a list-of-nested-model root property — that is exactly `mcp_servers` today — and
  `ReportSection` has no nested models of its own, so the guard against deeper `$ref`s is not
  reached. Only `docs/generated-app-schema.json` needs regenerating.
- `research/middleware.py` (`ForceToolChoiceMiddleware`) and the research-agent prompt are
  untouched: the report loop is downstream of research, and the rename does not reach the
  prompt text.
- `history.py` / `PrepState` need no new field. The middleware reads `research_started`, which
  already exists and is already persisted.

## Risks / Trade-offs

- **The loop costs tokens on every research turn.** → The review call carries only the draft
  (a few thousand words), not the transcript; revisions hit the prompt cache for their prefix;
  the budget is configurable and `0` turns the whole thing off.
- **Report-review becomes a second author.** A judge with an opinion about wording will keep
  finding something to change, spending the whole budget on every run. → Its prompt is scoped
  to the checkable criteria and instructed to approve anything that satisfies them; the
  logged verdicts show whether it is behaving, and the budget caps the damage either way.
- **A revision can make the report worse** — condensing to fit the ceiling loses detail, and a
  rewrite can drop a citation. → The spec keeps the citation-format check in the review step,
  so a revision that breaks citations is caught by the next pass; with an exhausted budget the
  latest draft ships, which is the same failure mode the change is trying to bound.
- **Report latency grows** by a review call plus any revisions, with no visible streaming
  during it. → Stages from research already carry the turn; the report loop's silence is
  bounded by the budget and covered by the SDK heartbeat.
- **The word ceiling stays approximate.** Nothing forces a revision to land under the ceiling;
  the loop only pushes toward it and stops. → Accepted: the acceptance criterion asks the
  report to respect the ceiling without abrupt truncation, and truncation is the only way to
  make a hard number hard.
- **"The response contains nothing but the report" is not fully closed by the middleware: text on
  the same message as the `start_research` call still reaches the user.** `preparation/runner.py:133-148` appends every model-node chunk's
  text to the choice with no tool-call check, and `dial-agent-with-mcp` contracts exactly that
  ("including text produced on intermediate `AIMessage` instances that also carry `tool_calls`").
  The tool has not run when those tokens stream, so `research_started` is still false and no
  `before_model` hook exists to consult; DIAL content is append-only, so nothing downstream can
  retract them. → The middleware closes the larger hole (the post-hand-off message the prompt used
  to ask for), and dropping "tell the user that research is starting" from the launch step
  discourages the remainder. Fully closing it needs
  `PrepAgentRunner` to buffer its text and decide at end of run — rejected earlier for costing the
  live streaming of clarifying questions, and worth revisiting only if stray preambles show up in
  practice.
- **A swallowed revision failure must also stop the loop.** Delivering the previous draft is only
  safe if control then leaves the loop: report-review would otherwise re-judge the same unchanged
  draft, route back to `report`, and fail again — and since a failed revision writes nothing,
  `revisions_used` never increments, so nothing but the graph's step budget would bound the cycle.
  → The edge out of `report` therefore exits to END when a revision's own call failed and a previous
  draft exists. It is app-owned state, not a model verdict, so it lives in the graph state beside the
  counter.
- **`_inline_root_refs` raises on nested `$ref`s.** If `ReportSection` ever gains a nested
  model, schema generation fails loudly at generation time — a lint failure, not a runtime one.
- **A future renderer may start parsing the references section too**, which would make its entry
  format an interface as well — and it is configurable. → Cheap to correct when it happens: move
  the entry format out of the section description into a report-wide requirement, the same place
  the inline format already lives. Worth knowing before a renderer is written against a format a
  deployment can edit.

## Open Questions

- **What exactly do reference entries look like, for publications and for datasets?** The format
  is to be supplied later. It lands entirely in the default References section's `description`, so
  the answer changes one string in one place and touches neither the specs nor the loop. Until it
  arrives, the shipped default carries the current Sources/Datasets tables (columns `doc id`,
  `title`, `publication date`; `dataset id`, `title`) as a placeholder.
- **Is the revision budget's default of 2 right?** Answerable from the logged verdicts and word
  counts of real runs (how often the first draft is approved, how often the budget is
  exhausted). It is one property default, so changing it touches no design.
