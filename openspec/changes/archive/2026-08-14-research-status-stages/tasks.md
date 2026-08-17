## 1. Settle the open question first

- [x] 1.1 Write a test that calls a tool taking an `InjectedState` parameter inside a `create_agent`
      graph and asserts the injected state's last message is the `AIMessage` carrying that tool's own
      call, with its full `tool_calls` list visible. This decides where misuse detection lives.
- [x] 1.2 If 1.1 fails, switch tasks 2.3 and 2.4 to the `before_model` `ToolMessage`-substitution
      pattern used by `ImageBudgetMiddleware` (`app/middleware.py:22-124`) and record the switch in
      design.md — Open Questions. The specified behavior does not change either way. **Not needed:
      1.1 passed**, so misuse detection stays in the tool.

## 2. The update_status tool

- [x] 2.1 In `app/research/tools.py`, add module-level constants for the acknowledgement and for the
      two corrective notes ("never the only tool call in a message", "at most once per message"), plus
      the sentence for each rule that the prompt and the tool description both reuse, so the three
      places that state a rule cannot drift.
- [x] 2.2 Add `build_update_status_tool()` returning a tool named `update_status` with one required
      string argument for the status text, its description composed from the shared rule sentences and
      carrying the length guidance ("usually five to eight words, never more than twenty") and the two
      examples: "Looking for US GDP forecasts", "Searching for latest risks to economic outlook".
- [x] 2.3 Give the tool an `InjectedState` parameter and count the tool calls in the assistant message
      carrying its own call.
- [x] 2.4 Return the acknowledgement plus the "not the only tool call" note when nothing else was
      called, plus the "at most once" note when the message held more than one status call, and both
      when both apply.
- [x] 2.5 Register the tool in `ResearchRunner.run` beside `build_finish_iteration_tool()`
      (`app/research/runner.py:80-81`).

## 3. The runner's activity stage

- [x] 3.1 Add a single open-stage slot to `ResearchRunner` plus a helper that closes the current stage
      and opens a new one with a given title. Manage `open()`/`close()` by hand with the runner's own
      "already closed" flag — never a `with` block, since `Stage.__exit__` closes unconditionally on
      the exception path and a double close raises `RuntimeServerError` over the real exception.
- [x] 3.2 Open the first activity stage in `run` before the graph stream loop starts.
- [x] 3.3 In `_handle_ai_message`, collect the status texts from `msg.tool_calls` in order; if the
      message also calls `finish_iteration`, leave the stage untouched; otherwise join the texts with
      `"; "` and make exactly one call to the replace helper. Do not register status calls as
      `PendingToolCall`s.
- [x] 3.4 Make `_handle_tool_message` skip `update_status` explicitly, mirroring how `_FINISH_TOOL` is
      handled at `runner.py:189-201`, so it emits no `[TOOL]` result stage and no INFO
      tool-call-completed record.
- [x] 3.5 Log one WARNING per assistant message when the message's only tool call was `update_status`,
      and one when it carried more than one, each with tool-call counts and never the status text.
- [x] 3.6 Wrap the stream loop in `try/finally`: close the open stage as `Status.FAILED` on exception
      and as `Status.COMPLETED` on normal exit, before `_emit_unreviewed_delivery_stage` and
      `_deliver_report` run.

## 4. Node entry announcements

- [x] 4.1 Add an activity-emitter type and thread it through `build_research_graph`
      (`app/research/graph.py:34-48`) beside the report-review result-stage emitter, wired from
      `ResearchRunner.run` to the replace helper from 3.1.
- [x] 4.2 Call the emitter as the first action of the research-review, report and report-review nodes
      in `app/research/nodes.py`, with fixed titles written to the same convention as the model's:
      plain, short, present tense, no prefix.

## 5. Hiding statuses from the transcript readers

- [x] 5.1 Add a helper in `app/research/nodes.py` that returns a message list with every
      `update_status` tool call stripped from its assistant message and every matching `ToolMessage`
      dropped, leaving each remaining tool call paired with its result. Strip the call, never the whole
      message — the usual case is a status riding with real tool calls.
- [x] 5.2 Apply it at `_render_findings(state["messages"])` (`nodes.py:163`) and at the report node's
      `*state["messages"]` (`nodes.py:274`). Apply it nowhere else: report-review reads no transcript,
      and the transcript persisted to `custom_content.state` keeps the status calls.

## 6. Prompt

- [x] 6.1 Add an `update_status` section to `RESEARCH_AGENT_SYSTEM_PROMPT`
      (`app/research/prompts.py:62`) saying when to announce — on starting a meaningfully new step, not
      on every tool call and not on every iteration — and stating the four rules: never more than once
      per turn; never as a turn's only tool call; never together with `finish_iteration`; five to eight
      words and never more than twenty. Build the first two from the shared constants of 2.1.
- [x] 6.2 Edit the prompt's "You must always call a tool" section (lines 78-84), which currently reads
      as though every step is a research tool call or `finish_iteration`.

## 7. Tests

- [x] 7.1 Extend the `_StageSpy` / `_ChoiceSpy` harness from `tests/test_preparation_streaming.py:21-40`
      to record stage open/close order and status, for the research runner.
- [x] 7.2 Assert exactly one activity stage is open at every point of a run, starting before the graph
      runs; that an announcement closes the previous and opens a new one; and that the closed stage's
      name is unchanged, with no elapsed time appended and no content.
- [x] 7.3 Assert an activity stage stays open across the tool result stages that follow it.
- [x] 7.4 Assert two `update_status` calls in one message yield exactly one stage carrying both texts,
      and that no stage anywhere in a run is opened and closed at the same instant.
- [x] 7.5 Assert a message carrying both `update_status` and `finish_iteration` changes no stage.
- [x] 7.6 Assert entering research-review, report and report-review each replaces the open stage.
- [x] 7.7 Assert a mid-run failure closes the open stage as `FAILED` without masking the original
      exception, and that the emitted chunks leave no stage with an unset status.
- [x] 7.8 Assert the transcript filter keeps a mixed message's research tool calls and their results
      while removing only the status call and its acknowledgement; and that neither `_render_findings`'
      output nor the report node's message list contains status text, while the persisted state does.
- [x] 7.9 Assert the tool's response carries the right note for each misuse and for both together, and
      the plain acknowledgement for correct use.
- [x] 7.10 Assert `update_status` produces no `[TOOL]` result stage and no INFO tool-call-completed
      record, that each misuse logs one WARNING per assistant message rather than per call, and that no
      log record at any level contains status text.

## 8. Docs and closeout

- [x] 8.1 Update `docs/architecture.md`: the research graph flowchart (lines 123-150) and the loop
      invariants (152-242), including the bullet ending "Research review emits no stage", which becomes
      false.
- [x] 8.2 Run `make format` and `make lint`, and fix what they report.
- [x] 8.3 Run the full test suite.
- [x] 8.4 Drive a real query end to end with
      `poetry run python scripts/send_conversation.py "<question that triggers research>" -f conv.json
      -m overwrite -d <deployment>` against a running server, and confirm in the DIAL UI that one stage
      renders as running at any moment, that its title changes as research proceeds, and that no
      spinner is left behind at the end.
      All three confirmed in the client. A turn that failed mid-research stopped the spinner and
      showed the failure icon, so nothing was left spinning. The first full run announced only once
      in an iteration that ran ~2m45s over 28 tool results in 8 turns; the prompt's frequency
      guidance was rewritten in response, after which the title tracks the work.

## 9. The research review's findings as a stage

- [x] 9.1 In `utils/dial_stages.py`, add an in-progress emoji constant (🔄) and set
      `DialStageReportReviewFormatter._PREFIX` to `[REPORT REVIEW RESULT]`. A revising outcome carries
      the in-progress emoji; the unreviewed delivery keeps ⚠️ and a failed call keeps ❌. Update the
      five title assertions in `tests/test_dial_stages.py:48-122`.
- [x] 9.2 Add `DialStageResearchReviewFormatter` beside it, prefixed `[RESEARCH REVIEW RESULT]`, with
      `format_title` over the iteration number, the `will_continue` flag and the duration, and
      `format_body` over the iteration number, the iteration cap, the assessment and the next steps —
      the steps as a numbered markdown list, or a line stating research is complete when there are
      none.
- [x] 9.3 Add `ResearchReviewOutcome` and `ResearchReviewResultStageEmitter` to
      `app/research/nodes.py`, beside their report-review counterparts. Fields: the reviewed iteration
      number, the iteration cap, the assessment, the next steps, `will_continue`, and the call's
      duration in seconds. No error field — research-review re-raises instead of absorbing a failure.
- [x] 9.4 Give `make_research_review_node` an `emit_result_stage` parameter and the
      `max_research_iterations` value, and emit the outcome once the call has returned, with
      `will_continue` taken from `_should_continue_research` so the title cannot disagree with the
      routing. The INFO record stays as it is: it already carries the iteration number, the duration,
      the verdict and the step count.
- [x] 9.5 Thread `emit_research_review_result_stage` through `build_research_graph` and add
      `ResearchRunner._emit_research_review_result_stage`, rendering the outcome through the new
      formatter.
- [x] 9.6 Assert the formatter's titles and bodies for both verdicts, including the numbered list of
      next steps and the research-is-complete line.
- [x] 9.7 Assert the node emits exactly one outcome per call, carrying the iteration number, the
      assessment and the steps, with `will_continue` matching where the graph routes next.
- [x] 9.8 Assert an iteration the cap left unreviewed emits no research-review stage.
- [x] 9.9 Assert no log record at any level, including DEBUG, carries the assessment or the next-step
      text, and that the INFO record still carries the step count.
- [x] 9.10 Update `docs/architecture.md`: the research-review node in the research graph flowchart, and
      the stage list in the loop invariants, which names the report-review and activity stages only.
- [x] 9.11 Run `make format` and `make lint`, then the full test suite.
- [x] 9.12 Drive a real query end to end with `scripts/send_conversation.py` against a running server,
      and confirm in the DIAL UI that a research review that continues and one that completes each
      render their own stage, next to the live activity stage. Confirmed in the client.

## 10. The tool-stage title format

- [x] 10.1 In `utils/dial_stages.py`, shorten the tool-stage title to
      `[TOOL] <name> <emoji> (<timings>)`: no quotes around the name, and no `result`/`error` word,
      which the mark already carries.
- [x] 10.2 Update the two tool-stage title assertions in `tests/test_dial_stages.py`.
- [x] 10.3 Update the `dial-agent-with-mcp` delta — the normalized title form, the error-stage
      scenario's example, and the `update_status` scenario's literal — and the report-review stage's
      title sentence in the `report-composition` delta, which described its shape by pointing at the
      tool stages'.
- [x] 10.4 Normalize the three requirements that call the failure stage the `error ❌` variant, which
      the shorter title leaves behind: the researcher requirement's tool-error scenario in
      `research-execution`, and "Opik tracing of agent runs when configured" and "Failures delivered
      as DIAL protocol errors" in `dial-agent-with-mcp`. Each is copied into its delta as a MODIFIED
      requirement — extracted from the main spec rather than retyped, then diffed against it, so the
      copy differs in the intended phrase alone.
- [x] 10.5 Run `make format` and `make lint`, then the full test suite.
