# Tasks — prompt-caching

## 1. Settings and header wiring

- [x] 1.1 Add `llm_cache_policy: Literal["availability-priority", "cache-priority"] | None = None`
      to `Settings` (`src/dial_deep_research/settings.py`), with a comment explaining the
      knob (DIAL Core cache routing retry policy; unset sends no header)
- [x] 1.2 Pass `default_headers={"X-DIAL-CACHE-POLICY": settings.llm_cache_policy}` in
      `get_chat_model` (`src/dial_deep_research/utils/llm.py`) when the policy is set; no
      header otherwise
- [x] 1.3 Unit-test the setting (default unset, both valid values, invalid value rejected
      with a `ValidationError` naming the field) and the header (present with configured
      value when set, absent when unset)
- [x] 1.4 Update the README environment-variables table with `LLM_CACHE_POLICY` (optional,
      default unset, one-line semantics, pointer to the DIAL prompt-caching tutorial)

## 2. Prefix stability

- [x] 2.1 Sort each server's tools by name in `load_mcp_tools`
      (`src/dial_deep_research/app/mcp_tools.py`), after the `tools_to_include` filter,
      keeping configured server order; adjust/extend its tests for deterministic ordering
- [x] 2.2 Reorder the reviewer's user message in
      `src/dial_deep_research/app/research/nodes.py` to question → findings → plans, and
      update any test fixtures that assert the old layout

## 3. Cache observability

- [x] 3.1 Extend `ModelCallLoggingMiddleware` (`src/dial_deep_research/utils/agent_logging.py`)
      to include the cached-input count from `usage_metadata.input_token_details["cache_read"]`
      in the existing `tokens=` field (e.g. `tokens=in/out/cached`, `n/a` when usage absent)
- [x] 3.2 Add the same token-usage field to the reviewer's "Iteration reviewed" event and
      the report node's "Report generated" event (report: read `usage_metadata` from the
      streamed chunk that carries it)
- [x] 3.3 Unit-test the three events: cached count rendered when present, graceful when
      usage or `input_token_details` is absent

## 4. Docs and verification

- [x] 4.1 Document the DIAL Core prerequisite next to the local-stack config templates
      (`dial_conf/`): the model-deployment flag `auto_caching_supported` the app relies on
      for sticky-upstream routing
- [x] 4.2 Run `make format` and `make lint`
- [x] 4.3 Manual verification against a running stack (`scripts/send_conversation.py`):
      confirm cached-token counts appear and grow in the model-call events on repeated
      calls within a research turn, and that the header shows up when `LLM_CACHE_POLICY`
      is set (LOG_PAYLOADS on a local stack). Confirmed against a live stack.
      (`X-DIAL-CACHE-POLICY` propagation was also verified offline onto the openai client's
      default headers — present when set, absent when unset.)
