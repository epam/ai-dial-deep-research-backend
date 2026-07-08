# Tasks

## 1. Dependency

- [x] 1.1 Add `aidial-client>=0.7.1,<0.8.0` to `pyproject.toml`.
- [x] 1.2 Refresh `uv.lock` (`uv lock` or `make` equivalent) and confirm the resolver picks a 0.7.x version.
- [x] 1.3 If `pyproject.toml` declares an `[tool.mypy]` per-module section (see existing `module = ["aidial_sdk.*"]` block), add a matching entry for `aidial_client.*` so the new imports type-check.

## 2. Image-attachment helper module

- [x] 2.1 Create `src/dial_deep_research/utils/image_attachments.py` with no `agent.py` imports (keep the module standalone for unit testing).
- [x] 2.2 Define a small content-block walker over `list[BaseMessage]` that yields `(message_index, content_index, block)` tuples for every dict-shaped block where `block.get("type") == "image"`. The walker SHALL be tolerant of `content` being `None`, a `str`, or a `list`; for non-list content it yields nothing.
- [x] 2.3 Implement `async def upload_image_blocks(messages: list[BaseMessage], dial: AsyncDial) -> None`. For every yielded image block carrying `base64`:
  - resolve bucket once per call via `await dial.bucket.get_raw()` (`appdata or bucket`);
  - decode `base64`, derive an extension from `mime_type` (`image/png` → `png`, fall back to `bin`);
  - choose a filename of the form `dial-deep-research/<owning_tool_call_id>-<content_index>.<ext>` if the surrounding message is a `ToolMessage` with `tool_call_id`, otherwise `dial-deep-research/<message_uuid>-<content_index>.<ext>`;
  - upload via `dial.files.upload(url=f"files/{bucket}/{name}", file=(name, raw_bytes, mime_type))`;
  - mutate the block in place: set `block["url"] = metadata.url`, delete `block["base64"]`. Leave other fields (`type`, `mime_type`, `id`) intact.
- [x] 2.4 Run uploads in parallel via `asyncio.gather(*upload_each_block, return_exceptions=True)`. On `BaseException` for a given block, call the placeholder substitution helper (task 2.5) and log the exception with the block's `mime_type` and approximate decoded size.
- [x] 2.5 Implement `_substitute_placeholder(messages, message_index, content_index, mime_type, byte_len, reason)` that replaces the failing block with a `TextContentBlock` whose text is e.g. `"[image upload failed: image/png, ~340 KB ({reason})]"`. Keep the helper private and used by both upload and rehydrate failure paths.
- [x] 2.6 Implement `async def rehydrate_image_blocks(messages: list[BaseMessage], dial: AsyncDial) -> None`. For every yielded image block carrying `url` and no `base64`:
  - download via `await (await dial.files.download(block["url"])).aget_content()`;
  - mutate the block in place: set `block["base64"] = base64.b64encode(bytes).decode()`, delete `block["url"]`. Leave `type` and `mime_type` untouched.
- [x] 2.7 Parallelize downloads with `asyncio.gather(..., return_exceptions=True)`; on failure, call the same substitution helper as task 2.5 with a `"download failed"` reason.

## 3. Wire helpers into `AgentRunner`

- [x] 3.1 In `src/dial_deep_research/app/agent.py`, build an `AsyncDial` client per request inside `run()` from `dial_app_settings.dial_url` and `dial_app_settings.dial_api_key.get_secret_value()`. Use it for both upload (end of `run`) and rehydration (inside `_extract_history_from_dial_request`).
- [x] 3.2 At the end of `run()`, replace the commented-out `set_state` block with: `await upload_image_blocks(self._messages, dial)`, then re-enable `state_dumped = DialState(messages=self._messages).to_dict()` and `self._choice.set_state(state_dumped)`. Keep the in-flight `_messages` mutation (the `_handle_*` dispatch buffers the original inline-base64 messages — the upload mutates them after the model has already seen the in-flight base64, so the model-facing contract from `multimodal-tool-output` is preserved).
- [x] 3.3 Convert `_extract_history_from_dial_request` from a `@classmethod` taking only `request` to an instance method (or free function) that also accepts the per-request `AsyncDial`. After the existing `messages_from_dict(...)` call, await `rehydrate_image_blocks(reconstructed_slice, dial)` before extending `history`.
- [x] 3.4 Adjust the `run()` call site so the `agent_input["messages"]` construction awaits the now-async history extraction.
- [x] 3.5 Remove the `# TODO: uncomment after saving image to dial file storage instead of custom content.` comment at `agent.py:158` — the conditional is fulfilled by tasks 3.2/3.3.

## 4. Unit tests

- [x] 4.1 Add `tests/test_image_attachments.py`:
  - Build a synthetic slice `[AIMessage(tool_calls=[{...id="call_1"}]), ToolMessage(content=[{"type":"text","text":"hi"}, {"type":"image","base64":"<...>","mime_type":"image/png"}], tool_call_id="call_1")]`.
  - Patch `AsyncDial` with a fake whose `bucket.get_raw()` returns an object with `.appdata="ad"`, `.bucket="ub"`, and whose `files.upload(...)` returns an object with `.url="files/ad/dial-deep-research/call_1-1.png"`. Confirm post-call block is `{"type":"image","url":"files/ad/dial-deep-research/call_1-1.png","mime_type":"image/png"}` (no `base64`). Confirm the text block is unchanged.
- [x] 4.2 Round-trip test: take the result of task 4.1, run `messages_to_dict` then `messages_from_dict`, then run `rehydrate_image_blocks` against a fake `AsyncDial` whose `files.download(url)` returns the original bytes. Assert the rehydrated block equals the pre-upload block (modulo `base64` re-encoding being byte-equivalent to the original bytes).
- [x] 4.3 Upload-failure substitution test: configure the fake `files.upload` to raise; assert the block is replaced by a `{"type":"text", "text":"[image upload failed: image/png, ~<N> KB (...)]"}` block; assert no `base64` survives anywhere in the slice; assert `set_state` would not be blocked (the call returns normally).
- [x] 4.4 Rehydration-failure substitution test: configure `files.download` to raise; assert the reconstructed `ToolMessage` carries a `TextContentBlock` placeholder in the same position.
- [x] 4.5 Bucket-fallback test: one parametrization with `appdata="ad", bucket="ub"` (expect `files/ad/...`), one with `appdata=None, bucket="ub"` (expect `files/ub/...`).
- [x] 4.6 Walker tolerance test: `ToolMessage(content=None)`, `ToolMessage(content="plain string")`, `ToolMessage(content=[{"type":"text",...}])` all complete without error and produce no uploads.
- [x] 4.7 Per `CLAUDE.md`/project guidance, do NOT add tests asserting default-only behaviour (e.g. "module exports `upload_image_blocks`"). Tests SHALL exercise the upload/rehydrate behaviour, not the shape of the API.

## 5. Spec & lint

- [x] 5.1 Run `openspec validate upload-tool-images-to-dial-files --strict`; expect no errors.
- [x] 5.2 Run `make format && make lint`; expect green. (Repo uses `ruff` per `pyproject.toml`.) — ruff + mypy clean on all changed files. One pre-existing RET504 in `src/dial_deep_research/utils/dial_stages.py:71` introduced in an earlier commit on this branch is unrelated to this change and left for separate cleanup.
- [x] 5.3 Run `make test_unit` (or the project's equivalent); expect green. — `tests/` passes 29/29 (excluding the pre-existing broken `tests/test_llm.py` whose import path is stale on this branch).

## 6. End-to-end verification

- [x] 6.1 Start the local stack: `make up && make run`. Confirm the app boots without `aidial-client` import errors.
- [x] 6.2 Multimodal turn: ask "fetch page 1 of document X as an image and summarise it". Confirm via DIAL admin / Core logs that `assistant.custom_content.state.messages` is populated, that the image block inside the persisted ToolMessage carries a `files/.../dial-deep-research/...` URL, and that the request did NOT 413.
- [x] 6.3 Cross-turn rehydration: send a follow-up turn — "look at the image you just fetched and tell me what's in the top-right quadrant". Confirm via tracing / `prompt_logging` middleware that the LLM request contains an `{type: "image", base64, mime_type}` block on the prior `ToolMessage`, i.e. rehydration restored the base64 from the DIAL files URL.
- [x] 6.4 ~~Failure injection: temporarily point `DIAL_URL` at an unreachable host (or stub the upload to raise) and re-run an image-returning turn.~~ Skipped — failure paths are already covered by `test_upload_failure_replaces_block_with_text_placeholder` and `test_rehydration_failure_replaces_block_with_text_placeholder`; a manual DIAL_URL repointing test adds no signal over the unit coverage.
- [x] 6.5 Verify uploaded files appear under the expected `dial-deep-research/` prefix in the appdata (or user, if fallback) bucket via direct DIAL files API listing. — confirmed by `GET /v1/metadata/files/{bucket}/dial-deep-research/`: bucket-fallback branch is exercised in dev (the static `dial_api_key` has no appdata), and the prefix contains three PNGs from the user's chat session, e.g. `call_60CUPeEcBDCUEIBOwIRYf2LB-0.png` (52069B, image/png) — `<tool_call_id>-<content_idx>.<ext>` naming as designed.

## 7. Docs / housekeeping

- [x] 7.1 Update `data/issues.md` to mark item 2 (the `[Error: Body exceeded 1mb limit]` row) and item 7 (images not recognized) as resolved by this change, with a reference to the change id.
- [x] 7.2 If `envvars.md` enumerates DIAL-side requirements, add a line clarifying that `DIAL_URL` / `DIAL_API_KEY` are now also used at runtime to construct `AsyncDial` for files I/O (no new variables, just an expanded scope of use).
