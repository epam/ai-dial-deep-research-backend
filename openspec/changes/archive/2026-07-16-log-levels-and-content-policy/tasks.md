# Tasks: Log Levels & Content Policy

## 1. Settings and third-party payload cap

- [x] 1.1 Add `log_payloads: bool = False` and `log_payloads_max_length: int` (default 2000,
      `ge=1`) to `Settings`; extend `tests/test_settings.py` (defaults, rejection of
      non-positive cap)
- [x] 1.2 Add the payload cap to `configure_logging`: new `log_payloads` keyword; while false,
      pin `openai`/`httpx`/`httpcore` to the more severe of `LOG_LEVEL` and INFO; pass the
      setting at the `__main__.py` call site; extend `tests/test_logging_config.py` (cap on,
      cap lifted, stricter global level preserved)
- [x] 1.3 Document `LOG_PAYLOADS` / `LOG_PAYLOADS_MAX_LENGTH` in the README env table (with the
      local-development-only warning and the third-party cap semantics) and `.env.example`

## 2. Payload-debugging records (resolves #11)

- [x] 2.1 Rework `PromptLoggingMiddleware`: emit at DEBUG, truncation cap from settings, and add
      a helper returning `[middleware]` when `settings.log_payloads` else `[]`; unit tests
      (truncation marker, DEBUG level, helper gating)
- [x] 2.2 Wire the helper into all three `create_agent` graphs (`preparation/agent.py`,
      `playground/agent.py`, `research/nodes.py`)

## 3. INFO request skeleton

- [x] 3.1 Add `ModelCallLoggingMiddleware` (event 3: agent name, duration, finish kind,
      requested tool names, content length, token usage when available) and attach it to the
      three `create_agent` graphs, outside the retry middleware; unit tests over a fake handler
- [x] 3.2 Emit request-received (event 1), preparation-completed (event 2), and
      request-completed (event 7) in `DeepResearchCompletion` and `PlaygroundCompletion`;
      refactor `raise_dial_error` to take the turn start time and emit event 7 with
      `outcome=failed` and the `error_reference` alongside the existing ERROR; tests for the
      failure path (one ERROR, completion event carries the same reference)
- [x] 3.3 Emit tool-call-completed (event 4) at the runners' `_handle_tool_message` choke
      points from the existing `PendingToolCall` timing, `outcome` from `msg.status`;
      `finish_iteration` logs at DEBUG only; tests
- [x] 3.4 Emit iteration-reviewed (event 5) in the reviewer node and report-generated (event 6)
      in the report node, each with duration; tests

## 4. Level rebalance and content sweep

- [x] 4.1 `history.py`: demote the two custom-content fallback WARNINGs to DEBUG; replace the
      state-validation `logger.exception` with a WARNING logging error count + `loc` paths +
      error types (no rendered pydantic text, no traceback); tests
- [x] 4.2 `properties.py`: reshape the validation WARNING to error count + `loc` paths + error
      types; test that property values do not appear in the record
- [x] 4.3 `llm.py`: demote the chat-model construction record to DEBUG
- [x] 4.4 `image_attachments.py`: strip query string/fragment from the URL in the download
      failure record; test

## 5. Policy home and final checks

- [x] 5.1 Add a one-line convention entry to `CLAUDE.md` pointing at the `logging-policy` spec
      (levels, content allowlist, payload switch)
- [x] 5.2 Run `make format`, `make lint`, and the full test suite; fix fallout
