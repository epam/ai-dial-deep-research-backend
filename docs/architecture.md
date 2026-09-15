# How Deep Research works

Diagrams of the current runtime flow: the preparation flow, which spans several turns, and the
research graph, which runs autonomously inside one turn. **Turn** here means a DIAL turn between
the user and the assistant: one chat completion request carrying the user's new message, and the
assistant reply streamed back for it. The app keeps nothing between turns, rebuilding each one from
the request it arrives in.

The [OpenSpec specs](../openspec/specs) are the authority on the behaviour. This page is a map:
each section links the specs that own its requirements and quotes only short excerpts from them, so
when a spec changes the diagram points at the new wording instead of restating stale rules.

- [Preparation flow](#preparation-flow)
- [Research graph](#research-graph)

## Preparation flow

Specs: [clarification-and-plan-alignment](../openspec/specs/clarification-and-plan-alignment/spec.md).
Code: `app/preparation/`, `app/completion.py`, `app/history.py`.

The preparation agent advances a clarify → plan → approve → launch flow by calling tools, and the
ordering is enforced by the tools, not by the agent:

> The flow's ordering SHALL be enforced by tool preconditions (hard gates), not by the agent's
> discretion: research SHALL NOT be startable until the working query's clarifications are resolved
> and the plan is user-approved.

Two of the tools make their own independent structured LLM calls — the clarity check inside
`update_query`, and the approval reviewer inside `approve_plan`. The agent cannot approve its own
plan, nor write the readiness flags: only tool code mutates `PrepState`.

Turns are stateless. Each turn reconstructs the history and `PrepState` from the request and
persists both back into the assistant message's `custom_content.state`; the same property is what
makes a rewind work with no rewind-detection logic.

```mermaid
sequenceDiagram
    actor U as User
    participant C as DIAL Core
    participant A as Preparation agent
    participant T as Preparation tools
    participant L as Check LLM calls
    participant G as Research graph

    loop one turn per exchange, until the query is clear
        U->>C: research request, or an answer to the questions
        C->>A: turn — history + PrepState
        A->>T: update_query "restated or refined query"
        Note over T: a new query discards<br/>any plan and its approval
        T->>L: clarity check
        L-->>T: clarifying questions, or none
        T-->>A: questions to relay, or "query is clear"
        opt query not yet clear
            A-->>C: questions + state (query, outstanding questions)
            C-->>U: questions, then the turn ends
        end
    end

    loop one turn per exchange, until the plan is approved
        A->>T: update_plan [steps]
        Note over T: gate: requires a clear query
        T-->>A: recorded query + plan
        A-->>C: query + plan verbatim + state (plan recorded)
        C-->>U: plan to review
        U->>C: approval, or requested changes
        C->>A: turn — history + PrepState
        alt user signals approval
            A->>T: approve_plan
            Note over T: gate: requires a recorded plan
            T->>L: independent approval reviewer
            L-->>T: approved, or not approved / recorded plan is stale
            T-->>A: verdict
        else user asks for changes
            Note over A: revise the steps and<br/>call update_plan again
        end
    end

    A->>T: start_research
    Note over T: gate: requires an approved plan
    T-->>A: research is ready
    Note over A: middleware ends the agent loop:<br/>no further model call, no closing message
    A->>G: hand off — same turn
    G-->>C: report appended once + state (research_started)
    C-->>U: report

    U->>C: follow-up in the same conversation
    C->>A: turn — PrepState says research_started
    A-->>C: DIAL error: research already handed off
```

The final turn is where preparation hands off: `start_research` fires and research runs in the
**same** turn, so preparation and research are persisted together, once, at the end of it
(`app/completion.py`). A later message on the same conversation is refused — see the
research-already-handed-off scenario in
[dial-agent-with-mcp](../openspec/specs/dial-agent-with-mcp/spec.md).

The hand-off is silent, and by control flow rather than by prompt wording: a `before_model`
middleware ends the preparation agent's loop as soon as `PrepState` says research has started, so
no model call follows the gate and nothing announces that research is starting. One case stays
outside that guarantee, knowingly: text the model wrote on the same assistant message that carries
the `start_research` call was already streamed before the tool ran, and DIAL content cannot be
retracted, so such a sentence can still appear ahead of the report.

## Research graph

Specs: [research-execution](../openspec/specs/research-execution/spec.md),
[report-composition](../openspec/specs/report-composition/spec.md) (what the report must look like
and the loop that enforces it),
[report-citations](../openspec/specs/report-citations/spec.md) (what the delivery step does to the
settled draft),
[dial-agent-with-mcp](../openspec/specs/dial-agent-with-mcp/spec.md) (the research-agent node, MCP
tool loading, stages, error delivery).
Code: `app/research/`.

A deterministic LangGraph with four nodes, where every phase transition is Python over the state,
never a model decision:

> `START → research-agent → (research-review when another iteration may still run, else report —
> the last permitted iteration's findings are not reviewed) → (research-agent when
> research-review returns a non-empty next plan, else report) → (END when this call was a
> revision whose own model call failed, or when the draft is the last version the budget
> permits — it is delivered without review — else report-review) → (report when the draft's
> measured word count exceeds the ceiling or report-review asks for a revision, else END)`

```mermaid
flowchart TD
    seed["Seed state from PrepState:<br/>query + approved plan as the<br/>first iteration's instruction"] --> model

    subgraph research_agent_sub["research-agent node — one iteration, a create_agent loop"]
        model["Model call<br/>tool_choice = any → it must call a tool"]
        model --> which{"which tool<br/>did it call?"}
        which -->|"an MCP tool"| mcp["The tool runs; its result is<br/>appended to the transcript"]
        mcp --> model
        which -->|"update_status, alongside<br/>the step's first real tool call"| status["The runner replaces the open<br/>activity stage with this title;<br/>no result stage, no research done"]
        status --> model
        which -->|"finish_iteration"| fin["finish_iteration is declared<br/>return_direct = True:<br/>the loop returns as soon as this tool<br/>runs, with no further model call"]
        which -.->|"a message with no tool call —<br/>the loop's other exit"| blocked["unreachable:<br/>tool_choice = any forbids it"]
    end

    fin -->|"the only way a research-agent<br/>iteration can end"| itgate{"another iteration<br/>permitted by the cap?"}
    itgate -->|yes| research_review["research-review node<br/>independent structured LLM call<br/>→ assessment + next_steps,<br/>and one DIAL stage"]
    itgate -->|"no — a 'continue' verdict could<br/>not be acted on, so the last<br/>iteration is not reviewed,<br/>announced by a closing stage"| report
    research_review --> route{"next_steps non-empty?"}
    route -->|yes| nextplan["Record the plan and inject it as<br/>the next iteration's instruction"]
    nextplan --> model
    route -->|no| report["report node<br/>LLM call over the whole findings<br/>transcript → the first draft, or a<br/>revision when a draft already exists"]
    report --> afterreport{"deliver now,<br/>or review the draft?"}
    afterreport -->|"this call was a revision whose<br/>own model call failed —<br/>the previous draft stands,<br/>announced by a closing stage"| finaldone(["END"])
    afterreport -->|"the last version the budget<br/>permits — delivered without review,<br/>announced by a closing stage"| finaldone
    afterreport -->|"otherwise"| report_review["report-review node<br/>structured LLM call over the draft and<br/>the configured sections → violations<br/>(the app adds the length one itself),<br/>and one DIAL stage"]
    report_review --> reroute{"over the word ceiling,<br/>or a revision asked for?"}
    reroute -->|yes| report
    reroute -->|no| finaldone
```

**A research-agent iteration ends only when `finish_iteration` is called.** Two mechanisms give
that guarantee, and together they mean research-agent cannot stop early, cannot write its own
summary, and cannot reach the report without a research-review verdict:

- **Forced tool choice** — every model call is issued with `tool_choice="any"`, so each step calls
  some tool. A message carrying no tool call is what would normally end a `create_agent` loop, so
  that exit is unreachable.
- **`return_direct=True` on `finish_iteration`** — the loop returns as soon as that tool executes,
  with no further model call. The tool is a no-op signal: it ends the iteration and nothing more,
  leaving review-vs-report to the graph.

The spec sentence that owns the rule:

> A research-agent iteration SHALL therefore end **only** when research-agent calls
> `finish_iteration`. That tool SHALL be declared `return_direct=True`, so the agent loop returns
> as soon as it executes, with no further model round-trip.

The rest of the loop, in brief — each item is specified in the linked specs:

- **Research-review**: an independent structured LLM call judging coverage; an empty next plan means
  research is complete. It runs after every iteration except the last one the cap permits — a
  "continue" verdict there could not be acted on, so that call is not made.
- **Iteration cap**: `max_research_iterations` (an application property). The last permitted
  iteration hands its findings straight to the report, unreviewed, so a turn always ends with a
  report; the hand-off is logged.
- **Report node**: the only node whose text becomes assistant content, and it is **appended once**,
  after the review loop settles on the draft to deliver. Nothing is streamed: a draft may still be
  revised and DIAL content is append-only, so no rejected draft ever reaches the user. The same node
  writes the first draft and every revision, branching on whether a draft already exists.
  Research-agent, research-review and report-review output never become assistant content;
  research-agent tool calls surface as timed DIAL stages. What reaches the user is that draft after
  the delivery step below, the one permitted transformation between the two.
- **Report delivery** (`ResearchRunner._deliver_report`, `app/research/citations.py`,
  `app/research/references.py`, `app/research/file_sharing.py`,
  `app/research/document_metadata.py`,
  `app/research/dataset_metadata.py`): the citation step, run once
  per turn between the graph finishing
  and the report being appended. It makes three alterations to the settled draft, in this order:
  every hyperlink form goes (a link keeps its label, an image is dropped whole, an autolink or bare
  URL is deleted), then each convertible citation marker is replaced by an empty marker tag,
  `<cit data-id="…"></cit>`, then the References section is built and appended. Each kind of citation has its own condition, and both are about
  whether the reader can open what the pill points at: a `[doc <id>, page <ix>]` marker converts
  when the file-sharing tool returned a PDF URL for that document, and a `[dataset <urn>]` marker
  converts when the dataset-metadata tool reported that URN with an absolute `http` or `https`
  URL. A marker whose condition fails keeps its text exactly as the writer wrote it. Markers
  standing next to each other, separated
  only by spaces, commas or semicolons, share one tag and render as one pill, a document and a
  dataset among them. The post-processed
  text is what is appended **and** what is persisted, so a later turn reads back what the user saw.
  One `custom_content.annotations` array follows the content, one entry per converted citation,
  each naming its tag's id. Every label is a leading part naming the source plus a fixed trailing
  part, the trailing part appended after any shortening: a document reads
  `<publication title>, page <ix>`, a dataset reads `<dataset name> dataset`, and a lookup that
  resolved nothing changes only the leading part — `doc <id>` for a document, the URN for a
  dataset — so no label says which citations fell back. The pill's copy of the leading part is
  shortened to `max_pill_title_chars` (default 20, null to switch it off) because the client does not trim an
  overflowing label; the card keeps it whole. One label that is never
  shortened is an unresolved document's, `doc <id>, page <ix>` being short by construction. A
  document annotation carries the cited page in a zero-size `pdf_bbox` selector, an
  `application/pdf` attachment type and no `body.quote`; a dataset annotation carries no selector,
  a `text/html` type — which is what makes the client's card offer "open in browser" rather than a
  download — and a `body.quote` listing `* URN: <urn>` and, when the catalogue reported one,
  `* Last update: <date>`. The payload is dumped with `exclude_none=True`, so a field that does not
  apply is absent rather than null. No label carries a URL: a dataset's page is reached by
  clicking the pill and then the card's open-in-browser action, both of which belong to the client.
  The **References section is written by the app**, not by the report writer, from the metadata
  the same step already resolved — so its rows are a server's facts rather than a model's
  recollection. It carries a `##` heading with the configured section name and one `###` table per
  configured MCP server whose sources the report cites, in the order the servers are configured;
  a server with nothing cited contributes no table, and a report that cited nothing carries the
  references section's configured `description` text instead. Each table's sub-heading and its
  ordered columns come from `mcp_servers[].references_table`, each column a heading a reader sees
  and the metadata key or catalogue field it reads. Every cited source gets a row whether or not
  its metadata resolved and whether or not its citations became pills; the first column names the
  source and falls back to `doc <id>` or the URN when its key resolves nothing, while every other
  column is left blank, and nothing marks a row as degraded. A cell renders a string as written, a
  number or boolean as its text and a list joined with `, `, escaping `|` and collapsing line
  breaks so a value cannot break the table. No row carries a link or a marker tag: a cited
  document's shared URL is storage-relative, so an ordinary Markdown link to it opens nothing, and
  making a row openable would mean an annotation and therefore a citation card. Because nothing
  here writes a link, the no-hyperlink guarantee holds over the delivered text whole. A references
  section a draft wrote anyway is removed before the built one is appended, so the reader never
  sees it twice — the draft is still judged as written, so that section is a structure violation
  and its words count toward the ceiling. A structure declaring no references section gets none.
  The build is the last pass, so its failure costs the section alone and is one WARNING
  (`kind=references_build_failed`); every pill the conversion earned is already in the text.
  The step's three resolutions are issued together in one `asyncio.gather`, each failing
  independently into an empty mapping, so the step costs one round trip. The
  document metadata comes from one MCP resource read per turn, at the URI named by
  `mcp_servers[].document_metadata_resource` with the cited ids substituted. It answers with each
  document's stored metadata whole; the label takes the value under
  `mcp_servers[].document_title_key` and a References row takes its configured columns out of the
  same answer, so a pill's title and its row's first cell are one fact rather than two lookups. A `generic_rag` server must name both, and the read asks about
  every cited document — which is what frees it from the file-sharing answer — while only the titles
  of documents that resolved a URL reach a label or the titled count. Its failures are graded one step
  below the file-sharing ones because a title costs a label rather than a link: naming no resource
  is DEBUG, a failed or unreadable read is one WARNING, and a document whose metadata simply
  carries no title is recorded only as the gap between the resolved and titled counts. The
  document URLs come from one call per turn to the tool named by `mcp_servers[].file_sharing_tool`,
  invoked tool-call-shaped so its structured result is reachable, and with the agent tools' error
  handling cleared so a failure reaches the app instead of arriving as result text. The dataset
  names, page addresses and last-update dates come from one call per turn to the tool named by
  `mcp_servers[].dataset_metadata_tool`, made with no arguments and answered with the channel's
  whole catalogue, from which the app selects the cited URNs by exact string match. A `statgpt`
  server must name that tool and only a `statgpt` server may, and it **stays in the research
  agent's tool list**, because a catalogue listing is how the agent discovers which datasets exist;
  its error handling therefore stays the agent's, and the reader takes a server error off the
  returned message's `status`. Each metadata surface is required of the server type whose citation
  ids it resolves, so a channel that resolves none of a kind is one that configures no server of
  that kind: it converts nothing of that kind and records the absence at DEBUG. Every other failure — a tool the
  server does not advertise, a failed call, an unreadable answer, an id the answer omitted, and a
  failure of the step's own passes — is one WARNING naming the kind, and none of them can fail the
  turn or withhold the report. A cited dataset the catalogue reports without a page URL is no
  failure at all, and reads only as the gap between the requested and resolved dataset counts.
  Every record of the step carries counts and never a URL, a file name,
  a document title, a dataset name, or a cited document's or dataset's id.
- **Report structure**: `default_report_structure` (an application property) — an ordered list of
  `{name, description, protected, references_section}` sections, Overview → Key Findings →
  Detailed Analysis → Conclusion → References by default. Every section is rendered as a `##`
  heading, and the app checks that itself (see the rules bullet below). A section's `description`
  is the single home for its content rules and is passed verbatim to both the report node and
  report-review — except the references section's, which is the text that section shows when the
  report cited no source, the app writing that section rather than the writer. A protected section
  (Overview and References, by default) may be neither dropped
  nor restyled by anything the user asked for; at least one section must be protected. Both models
  are told which sections are protected as a rule of their own — the marker is never rendered next
  to a section name, which the report node is told to use as the heading. `references_section`
  marks the report's sources listing; only the last section may set it, and a structure may
  declare none. That section is the one the writer does not write: it is left out of the structure
  both prompts are given, out of the protected names they are told, and out of the headings the
  structure check expects, so a draft that writes it is reported as an extra `##` heading.
- **Word ceiling**: `max_report_words` (default 2750). A report's length is the number of
  whitespace-separated tokens left after dropping the inline citations,
  so the ceiling bounds the report's prose rather than its sourcing — `count_report_words` in
  `app/research/report_length.py` is the one definition. The references section needs no
  exemption, being no part of a draft: the app appends it after the loop settles. A draft that
  writes one anyway is measured with it, so a structure violation earns no length budget. The
  count is computed in Python and given to the report node
  as a number, so no model has to count; report-review never sees the count — the app's own length
  rule adds the violation when the count exceeds the ceiling. The ceiling is enforced by
  rewriting, never by truncation: no token cap is placed on the report call, and a shortening
  revision rewrites to fit instead of cutting, so the report ends at a clean boundary. A draft over
  the ceiling forces a revision deterministically, even when report-review approved it.
- **App-checked rules** (`app/research/report_rules.py`): the three report rules the app decides
  itself, over the draft text — the section structure (every configured section present, named
  exactly as configured, in order, as a `##` heading), the word ceiling, and the absence of
  hyperlinks (no Markdown link or image, no reference-style link or its definition line, no raw
  HTML anchor or image tag, no autolink, no bare URL). Each rule owns three things in one class:
  the instruction rendered into the report writer's prompt, the check over the finished draft, and
  the wording of the violation a revision acts on, so the writer can never be told something
  different from what its draft is judged against. Their violations are prepended to
  report-review's own, and report-review is told the app checks all three — leaving it what needs a
  reader: a padded section, the protected-section rules, the banned annotations, valid Markdown,
  the citation format. The hyperlink rule's violation asks for the **sentence** to be rewritten
  rather than for the URL to be deleted, because only the report writer can produce a sentence that
  still reads well without it; the delivery step's removal is the guarantee behind it, for a draft
  the review never got to revise. The detection is shared — the rule and the delivery step both
  call `citations.find_hyperlinks` — so the two cannot disagree about what a hyperlink is. Because the structure check passes only when every heading matches the
  configuration, the references section is then found by the length measure by construction; that
  correspondence is covered by tests rather than by a runtime signal.
- **Version budget**: `max_report_versions` (default 3) — at most that many report versions, the
  first draft included, so at most three report calls. The last permitted version is delivered as
  it stands, without another review call: its verdict could not be acted on. A failed
  report-review call or a failed revision is absorbed rather than failing the turn. `1` skips
  report-review entirely.
- **Research-review stage**: each research-review call emits one DIAL stage, titled
  `[RESEARCH REVIEW RESULT]`, carrying the reviewed iteration with the iteration cap, the
  reviewer's assessment, and the next steps as a numbered list — or a line stating that research is
  complete, which is what an empty step list means. Its title names the route the graph then takes,
  `continue` or `report`, taken from the same function the router calls. The assessment and the
  steps are LLM response text, so the matching INFO record carries the step *count* only. A failed
  review call emits no stage: research-review re-raises, so the turn ends and the open activity
  stage closes as failed. An iteration the cap left unreviewed is announced by a stage of its own,
  emitted by the router as it hands over so that it precedes the report's stages: it states that the
  review budget is exhausted and carries the iteration with the cap, without a duration — no call
  was made, so it has no findings and no elapsed time. A cap of one emits nothing — one permitted
  iteration means review is off by configuration, not exhausted, the same rule a version budget of
  one follows.
- **Report stage**: the report step emits one stage in a single case — a revision whose own model
  call failed, where the previous draft is delivered instead. It carries its own
  `[REPORT REVISION FAILED]` prefix, because a prefix names the step the stage speaks for and this
  one is the report step reporting on itself, and names the draft that was not written, the draft
  delivered, and the failure kind. No draft text: only the draft the loop settles on reaches the
  response.
- **Report-review stage**: each report-review call emits one DIAL stage, titled
  `[REPORT REVIEW RESULT]`, carrying the draft number,
  the measured word count with the ceiling, and the violations as a list — the review model's
  violations, with the app-measured length violation prepended when the draft exceeds the ceiling.
  The matching INFO record carries the same numbers and only the *count* of violations — their
  text is LLM response content, which the logging content allowlist keeps out of log records at
  any level. A delivery whose draft the budget left unreviewed gets a closing stage and INFO
  record of its own, rendered without any model call, so "review approved the draft" and "the
  budget ran out, violations may remain" stay distinguishable.
- **Activity stage**: one DIAL stage is open at every moment of the research run, titled with what
  is happening right now. The runner opens the first before the graph starts; each later one
  replaces the one before it, which is what closes it — a stage name can only be appended to, never
  rewritten. research-agent sets the title by calling `update_status`, and research-review, report
  and report-review each set it on entry, so no LLM call in the graph runs behind a silent screen.
  The citation step replaces it once more after the graph finishes, and closes it before the report
  text is appended, so the content never arrives under an open stage; that step opens a stage only
  once it has work — a file-sharing call to make, or an edit to apply — because a draft citing
  nothing and carrying no link would otherwise open and close one in the same instant.
  The stage carries a title only: no body, no `[TOOL]`-style prefix, and no elapsed time — it ends
  because a new step started, not because the announced work finished, so a duration would claim
  something untrue. Several statuses in one assistant message are joined into one title rather than
  opening a stage that closes an instant later and so reads as a finished step; a status sent
  together with `finish_iteration` is ignored. `update_status` gets no result stage of its own and
  no INFO tool-call event, and its text never enters a log record, being a tool-call argument value.
  The announcements are stripped from the transcripts research-review and the report node receive,
  and kept in the one the app persists.
- **Step budget**: `max_research_graph_steps` (an application property, default 500) is passed as
  LangGraph's `recursion_limit` — the most node executions one graph run may make, counted afresh
  for each nested run. The research-agent node is a compiled graph, so every iteration gets its own
  budget, and that loop is what the budget really limits: the outer graph's length is already fixed
  by its own caps, at `2 × max_research_iterations + 2 × max_report_versions − 2` super-steps —
  24 at the default caps; the same formula gives 20 for a version budget of one, where the single
  report call is never reviewed. A research-agent that never calls `finish_iteration` exhausts the budget
  and the turn fails through the DIAL error protocol rather than returning a half-finished answer. A
  tool *error* does not end an iteration — it comes back as an error `ToolMessage` research-agent
  may retry from.
- **Image budget** (the [image-budget](../openspec/specs/image-budget/spec.md) spec): image-carrying
  tool results over the budget are substituted before each model call, so no request exceeds the
  provider's per-request image limit.
