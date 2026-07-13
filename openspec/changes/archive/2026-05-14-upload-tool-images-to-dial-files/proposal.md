## Why

The cross-turn persistence path added in `persist-agent-history-in-dial-state` (currently in `dial-agent-with-mcp`) is intentionally disabled in `agent.py` — the `choice.set_state(...)` call is commented out — because tool-message slices that include MCP-returned page images carry hundreds of KB of base64 per image inside `custom_content.state["messages"]`. A single tool turn routinely exceeds DIAL Chat's 1 MB request-body limit (`chat-1 | ⨯ [Error: Body exceeded 1mb limit] { statusCode: 413 }`, recorded in `data/issues.md`), so persistence was switched off as a defensive measure rather than risk crashing every multimodal turn. As a result the prior turn's tool messages are dropped from history and image-using prompts cannot be referenced in follow-ups — which silently re-introduces the regression `persist-agent-history-in-dial-state` was meant to close.

We need image content to live somewhere external to the message payload — the natural place in DIAL is the files API: upload to `files/{appdata-or-bucket}/{name}`, swap the inline base64 for a URL reference, and let the message carry only the URL.

## What Changes

- Upload every `{type: "image", base64, mime_type}` content block carried by a buffered `ToolMessage` to the DIAL files API before that slice is written to `custom_content.state["messages"]`.
- Replace the uploaded block with the same LangChain v1 `ImageContentBlock`, but populated with `url` (the returned files URL) and `mime_type` instead of `base64`.
- Re-enable the `choice.set_state({"messages": ...})` call that is currently commented out in `agent.py`; persistence becomes safe again because the state blob no longer carries image payloads.
- On the next turn, when reconstructing history from `custom_content.state["messages"]`, walk reconstructed `ToolMessage`s and re-inline any `url`-form image block by downloading the file from DIAL and rebuilding the block with `base64` + `mime_type`. This keeps the in-flight invariant from `multimodal-tool-output` intact (the LLM endpoint receives base64 image blocks, not DIAL-internal URLs).
- On upload failure: drop the image block from the persisted slice and substitute a `TextContentBlock` placeholder describing the loss (size-safe fail-closed). On rehydration failure: drop the block similarly. In both cases log the cause and continue; the turn SHALL NOT fail because of an image persistence issue.
- Add `aidial-client` as a runtime dependency (`>=0.7.1,<0.8.0`). The DIAL files API surface lives there, not in `aidial-sdk`.

**Non-goals:** propagating uploaded images to `choice.attachments` for direct UI display, a `supported_types`/`propagate_types_to_choice` two-list config, lifecycle management or TTL for uploaded files, and uploading non-image content blocks (audio, video, generic blobs). All deferred until a real use case appears.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `dial-agent-with-mcp`: the existing **Tool messages persisted via DIAL custom_content state** requirement gains an image-upload precondition (no image bytes in the state blob), and a new requirement covers the round-trip contract between upload (persistence write) and re-inlining (persistence read). The existing **Reconstruction of LangChain history from DIAL request** requirement gains the rehydration step that turns URL-form image blocks back into base64 blocks for the model.

## Impact

- **Code**:
  - `src/dial_deep_research/app/agent.py`: between `astream` completion and `set_state`, walk `self._messages` for `ToolMessage` content blocks of `type == "image"` with `base64` set; for each, upload to DIAL files and rewrite the block in place to carry `url` instead. Re-enable the (currently commented) `set_state` call. In `_extract_history_from_dial_request`, after `messages_from_dict(...)`, walk reconstructed `ToolMessage`s and rehydrate `url`-form image blocks by downloading from DIAL.
  - New module `src/dial_deep_research/utils/image_attachments.py`: `AsyncDial`-backed upload / download helpers + content-block walker, plus the placeholder substitution on failure.
- **Dependencies**: add `aidial-client>=0.7.1,<0.8.0` to `pyproject.toml`. Update `uv.lock`.
- **Configuration**: no new env vars. The existing `DIAL_URL` + `DIAL_API_KEY` are sufficient to construct `AsyncDial`.
- **DIAL surface**: uploaded files appear under `files/{appdata-or-bucket}/...` for the deployment's per-conversation appdata bucket. They are not surfaced to the UI as `choice.attachments`; they are only referenced from inside `custom_content.state["messages"]`.
- **Tests**: round-trip test (synthetic `ToolMessage` with one image block → upload-rewrite → state dump → state load → download-rehydrate → original base64 recovered); upload-failure substitution test; rehydration-failure substitution test. Skip the "no images" no-op path — it's covered by the existing persistence tests.
