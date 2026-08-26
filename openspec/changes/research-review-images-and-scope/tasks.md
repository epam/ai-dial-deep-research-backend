## 1. Prompts

- [x] 1.1 In `app/research/prompts.py`, add the report-format-out-of-scope and no-report-exists-yet
      rules to `RESEARCH_REVIEW_SYSTEM_PROMPT`.
- [x] 1.2 Split `RESEARCH_REVIEW_HUMAN_MESSAGE` into `RESEARCH_REVIEW_HUMAN_MESSAGE_HEAD` and
      `RESEARCH_REVIEW_HUMAN_MESSAGE_TAIL`, keeping the existing tags and wrapping text unchanged.

## 2. Findings rendering

- [x] 2.1 In `app/research/nodes.py`, change `_render_findings` to return a list of content blocks
      (text blocks plus each `ToolMessage`'s own image blocks, positioned where its text sits)
      instead of a `str`.
- [x] 2.2 Update `make_research_review_node` to assemble the `HumanMessage` content as
      `[head_text_block, *findings_blocks, tail_text_block]` using the two split templates.

## 3. Tests

- [x] 3.1 Update `tests/test_status_filtering.py` for `_render_findings`'s new return type.
- [x] 3.2 Add/update a test in `tests/test_research_review_stage.py` (or a new test file) asserting
      an image-carrying tool result reaches the research-review call as an image content block,
      not a marker.
- [x] 3.3 Add a test asserting the reviewer's assembled message still shares a byte-identical
      prefix across two iterations when only new findings are appended (the prompt-caching
      property `design.md` calls out).

## 4. Report-review format check

- [x] 4.1 In `app/research/prompts.py`, add a sixth check to `REPORT_REVIEW_SYSTEM_PROMPT`: when a
      user-specified format request doesn't conflict with checks 1-5, verify the draft honors it;
      when it does conflict, checks 1-5 win and that is never a violation.
- [x] 4.2 Add tests in `tests/test_report_loop.py` asserting the new check's language is present
      and states the conflict-resolution rule (protected sections and the other checks win).

## 5. Research-review: data vs. presentation

- [x] 5.1 In `app/research/prompts.py`, rewrite `RESEARCH_REVIEW_SYSTEM_PROMPT`'s scope rule so a
      format instruction naming real data (e.g. "compare X and Y in a table") still drives an
      ordinary coverage-gap next step; only the presentation itself stays out of scope.
- [x] 5.2 Add a test in `tests/test_research_review_stage.py` asserting the prompt names a
      coverage gap for missing data and states there is no report to check.

## 6. Verification

- [x] 6.1 Run `make format` and `make lint`.
- [x] 6.2 Run `make test` (or `poetry run pytest tests/unit -v` per the project's test command)
      and confirm all tests pass.
- [x] 6.3 Run `openspec validate research-review-images-and-scope --strict` and confirm it passes.
