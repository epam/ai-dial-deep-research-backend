## Context

`agent.py` already buffers the full `[AIMessage | ToolMessage]` slice of each turn into `self._messages`, and the `dial-agent-with-mcp` capability already requires that the slice be persisted into `assistant.custom_content.state["messages"]` via `messages_to_dict`. The implementation of the persistence write is present but **disabled** — `agent.py:158-160`:

```python
# NOTE: dial has limit on message content size (including custom content).
# TODO: uncomment after saving image to dial file storage instead of custom content.
# state_dumped = DialState(messages=self._messages).to_dict()
# self._choice.set_state(state_dumped)
```

The reason is concrete: the only MCP tool currently in use (`get_page` on the generic-RAG MCP server) returns `ImageContent` whose `data` field carries the base64 of a full page image (hundreds of KB). The MCP→LangChain adapter at `langchain_mcp_adapters/tools.py:103` converts that to a LangChain v1 image block:

```python
create_image_block(base64=content.data, mime_type=content.mimeType)
```

which yields `{type: "image", base64, mime_type}`. That block sits inside the `ToolMessage.content` list, gets serialized verbatim by `messages_to_dict`, and pushes the `custom_content.state` blob past DIAL Chat's 1 MB request-body limit (the `[Error: Body exceeded 1mb limit]` recorded in `data/issues.md`). The defensive fix in code (`set_state` commented out) reintroduces exactly the data loss `persist-agent-history-in-dial-state` was meant to close.

The shape we need is straightforward: upload-to-DIAL-files (appdata bucket, fall back to bucket), replace inline `data` with `url`, and let the message carry only the URL. The SDK surface for bucket/files is in `aidial-client`, not `aidial-sdk`.

Constraints inherited from earlier specs that this design SHALL NOT break:
- `multimodal-tool-output` requires that the LLM endpoint receive image content in LangChain v1 `{type: "image", base64, mime_type}` form on tool-result messages.
- `dial-agent-with-mcp` requires that `messages_to_dict` is the encoding, `messages_from_dict` is the decoding, and that `custom_content.state["messages"]` is the sole authoritative carrier of intermediate tool-call structure across turns.
- The DIAL-native `assistant.message.content` field is the UI display projection and SHALL continue to carry only the final assistant text.

## Goals / Non-Goals

**Goals:**
- Re-enable `choice.set_state(...)` unconditionally on every turn, including multimodal turns, by removing image payloads from the state blob before the write.
- Faithful cross-turn round-trip: on turn N+1, the agent's reconstructed `ToolMessage` from turn N SHALL contain the same `{type: "image", base64, mime_type}` block the model originally saw, byte-equivalent. The persistence layer is transparent to the model.
- Use DIAL files storage (appdata-or-bucket) so deployments don't need a new storage backend or new env vars.
- Fail-closed on storage errors: never leave inline image bytes in the persisted state. A turn with a flaky upload degrades to a text placeholder, never to a 413 crash.

**Non-Goals:**
- Surfacing uploaded images to the chat UI as `choice.attachments` for direct display. Deep-research's UI already shows the tool result via stages and doesn't need image preview. Deferred until a real use case appears.
- A two-list `supported_types` / `propagate_types_to_choice` config. There is exactly one rule today (image blocks in tool messages → upload), and YAGNI says ship the rule, not the config that lets you turn it off per tool.
- Lifecycle management / TTL / cleanup for uploaded files. DIAL's appdata bucket retention applies; we inherit whatever DIAL does. If storage growth becomes a problem the deployment can apply a bucket-level policy.
- Uploading non-image content blocks (audio, video, generic binary). No tool emits them today; adding speculative support is out of scope.
- Token-budget management for rehydrated histories. Same disposition as `persist-agent-history-in-dial-state` — orthogonal future change.
- Changing the in-flight (same-turn) path. `_handle_tool_message` already sees the unmodified `ToolMessage` with inline `base64`; the model receives it via langchain → LLM endpoint, satisfying `multimodal-tool-output` for the current turn. Upload is purely a persistence-side rewrite.

## Decisions

### D1. Storage location — DIAL files API (chosen) vs sidecar in `custom_content.attachments` vs custom external store

DIAL files requires no new infrastructure, and DIAL provides the bucket and authentication via the same `DIAL_URL` / `DIAL_API_KEY` the app already has. It also matches DIAL's own model for app-scoped binary data (the `appdata` bucket exists for exactly this).

Alternative considered: stash images base64-encoded in DIAL's native `assistant.custom_content.attachments` slot (separate from `state`). Rejected — `custom_content` size is part of the same 1 MB request body the chat container rejects, so it doesn't solve the problem.

Alternative considered: external storage (S3, MinIO, etc.). Rejected — deployments would need new credentials and a new bucket, the data lifecycle would no longer follow the DIAL conversation, and we'd be reinventing what DIAL files already provides.

### D2. Bucket selection — `appdata` with fallback to `bucket` (chosen) vs explicit per-app bucket env var

Resolve the bucket as:

```python
bucket_resp = await dial_client.bucket.get_raw()
bucket = bucket_resp.appdata or bucket_resp.bucket
```

`appdata` is the per-app, per-conversation scoped bucket — exactly the lifecycle we want for transient tool-image payloads. The `or bucket` fallback handles DIAL deployments that don't expose an appdata bucket (older Core, simpler test stacks); falling back to the user bucket means the file is still reachable for re-download on the next turn, which is the only invariant the upload needs to satisfy.

Alternative considered: introduce a `DIAL_FILES_BUCKET` env var so deployments can pin storage. Rejected — adds a configuration knob with no current consumer. The appdata-or-bucket resolution is sufficient and matches the auto-deferred-cleanup story.

### D3. Upload timing — batch at end of turn (chosen) vs incrementally in `_handle_tool_message` vs at decode time

Three points in the turn could carry the upload:

1. **In `_handle_tool_message`, as ToolMessages arrive** — uploads overlap with later streaming work. Pros: latency hidden behind ongoing streaming. Cons: error handling has to interleave with the streaming dispatch; rolling back a half-uploaded slice when a later step fails is awkward.
2. **After `astream` completes, before `set_state`** *(chosen)* — single, predictable code site. The user has already received the streamed assistant text, so the upload latency is purely a tail cost on the response close. Errors aggregate cleanly: walk slice, await `asyncio.gather(upload_each_image, return_exceptions=True)`, substitute placeholders for the failed ones, then call `set_state`.
3. **At decode time on the next turn** — defer everything. Rejected: the state blob would still contain the base64 (just compressed or chunked) and the 1 MB cap would still trip on the write.

Within option 2, uploads happen in parallel via `asyncio.gather` to keep tail latency bounded by the slowest single upload, not the sum.

### D4. Replacement block shape — same `ImageContentBlock` with `url` set, `base64` unset (chosen) vs custom marker block vs strip-and-replace-with-text

LangChain's `ImageContentBlock` (`langchain_core/messages/content.py:498-546`) already supports both `url` and `base64` as `NotRequired` fields — they are mutually exclusive *carriers* of the same image. Persisting the `url` form preserves block identity (the same `type: "image"`, same `mime_type`, same `id` if present), so the rehydration path can do a structural swap (`base64 = download(block["url"]); del block["url"]`) without rebuilding the surrounding `content` list.

Alternative considered: replace the block with a custom `{type: "image_ref", files_url}` block. Rejected — non-standard, breaks any downstream code that pattern-matches on the `"image"` discriminator.

Alternative considered: replace with a `TextContentBlock` describing the image. Rejected — the rehydration target is exact byte-equivalence with the original; we shouldn't lose the `image` discriminator on the happy path.

### D5. Rehydration strategy — download-and-reinline on read (chosen) vs leave URL in place vs eager prefetch

The `multimodal-tool-output` requirement is unambiguous: the LLM endpoint receives `{type: "image", base64, mime_type}`. A `url` pointing at `files/{bucket}/...` is a DIAL-internal reference that the LLM provider cannot fetch (it's not a public HTTP URL, it requires DIAL bearer auth, and even with auth most providers don't proxy unsolicited URL fetches from tool-result content). So on the read side, every URL-form block must be downloaded and converted back to base64 before it reaches the agent's `messages_from_dict` output.

`_extract_history_from_dial_request` is the natural site: after `messages_from_dict(state["messages"])` returns, walk the reconstructed `ToolMessage`s and rehydrate. Like uploads, downloads can run in parallel across the whole history via `asyncio.gather`.

Alternative considered: leave URL-form blocks in the rehydrated history and rely on the LLM/adapter to fetch. Rejected per the above — there is no fetch path that works.

Alternative considered: eagerly prefetch all images on app startup and cache them in memory. Rejected — couples lifecycle to process restarts, blows up memory for long-lived deployments, and gains nothing over per-turn fetch (each turn rehydrates exactly the slice it needs anyway).

### D6. Upload-failure behaviour — drop block, substitute `TextContentBlock` placeholder, log (chosen) vs fail-open (keep inline `data`) vs fail the turn

A fail-open handler would catch the exception and **leave the inline `data` in place** on failure. For deep-research that option is unsafe: an upload failure followed by `set_state` would push the inline base64 back into `custom_content.state` and hit the original 1 MB ceiling — the very condition this change exists to prevent.

Fail-closed: on upload error, replace the image block with a `TextContentBlock(text="[image upload failed: <mime_type>, ~<size>KB]")`, log the exception, and continue with `set_state`. The current turn already finished streaming the model's natural-language answer; the only loss is the model's ability to *reference this specific image* on a follow-up turn. That degradation is recoverable (the user can ask the tool to re-fetch the page) and infinitely preferable to a 413 that nukes the entire turn's persistence.

Alternative considered: abort the turn and surface the friendly-error string. Rejected — the user has already received a complete, valid assistant answer streamed via the same Choice; replacing it with an error after the fact would be a worse UX than a slightly degraded follow-up.

### D7. Rehydration-failure behaviour — same as D6 (chosen)

A `download()` failure on read (file 404, network error, auth) is operationally similar to an upload failure on write. Same treatment: substitute a `TextContentBlock` placeholder, log, continue. The current-turn agent run proceeds with a degraded slice in its history rather than aborting; the user-visible failure mode (the model can't see one prior image) matches D6 and stays inside the existing top-level error funnel's tolerance.

### D8. Where the upload/download code lives — new `utils/image_attachments.py` module (chosen) vs inline in `agent.py` vs subclass on `AgentRunner`

`agent.py` is already the largest module in the app and mixes streaming dispatch, history reconstruction, and DIAL state shaping. Adding upload/download walkers plus an `AsyncDial` client lifecycle in-line would push it past readable size and entangle three concerns. A new module `src/dial_deep_research/utils/image_attachments.py` with a small surface — `upload_image_blocks(messages, dial)`, `rehydrate_image_blocks(messages, dial)`, plus the placeholder helper — keeps `agent.py` focused on the agent loop and makes the upload logic independently testable. The module sits under `utils/` rather than `app/` because it has no awareness of `AgentRunner` or DIAL `Choice` — only LangChain content blocks and `AsyncDial` — and the `app/history.py` module is the only consumer.

The `AsyncDial` client itself is constructed per-request (cheap, just an HTTP client around `httpx`) inside `run()` and threaded into both helpers. Deep-research has no DI container and the per-request construction is fine.

### D9. Bucket lookup cost — per turn (chosen) vs cached at process startup

`bucket.get_raw()` is one DIAL Core call per turn. The same call already happens implicitly inside `aidial-client` for every files operation, so caching at the app level is a micro-optimization with non-trivial invariants to keep (bucket invalidation on auth refresh, etc.). Defer until profiling shows it matters.

### D10. Naming the uploaded files — `{tool_call_id}-{block_index}.{ext}` under a turn-scoped prefix (chosen) vs random UUID

A random name would be fine for one-shot attachments. For tool messages the `tool_call_id` is already a stable correlation identifier for the slice and the block index is unambiguous within that tool result, so `<tool_call_id>-<block_index>.<ext>` makes operational debugging much easier (you can grep DIAL logs for a tool call and see exactly which files it produced) at the cost of no extra entropy — the `tool_call_id` is already cryptographically random.

Storage path: `files/{bucket}/dial-deep-research/{tool_call_id}-{block_index}.{ext}`. The fixed `dial-deep-research/` prefix scopes the app's files within a shared appdata bucket so collisions with other apps using the same bucket can't happen. The extension is inferred from `mime_type` (e.g. `image/png` → `png`); unknown types get `bin`.

### D11. Dependency version range — `aidial-client>=0.7.1,<0.8.0` (chosen)

`aidial-client>=0.7.1,<0.8.0` matches the Files / Bucket APIs we're calling.

## Risks / Trade-offs

- **Two extra round-trips per multimodal turn** (one upload set on write, one download set on read of *prior* turns). Each is parallelizable across images, but tail latency is bounded by the slowest single transfer per direction. → Mitigation: monitor `set_state` time and history-extraction time in tracing; if either becomes a perceptible portion of turn latency, prefetch in `__init__` of `AgentRunner` once the bucket is known. Acceptable for now since the alternative is full text-only history.
- **DIAL files storage growth** — every multimodal turn produces N image files that never get cleaned up by the app. → Mitigation: out of scope (D10 note). DIAL deployments can apply bucket-level retention if it becomes an issue.
- **Fail-closed loses information visible to the model** — D6's placeholder is strictly less informative than the original image. → Mitigation: the current behaviour is *also* lossy (whole tool slice is dropped from history because `set_state` is commented out), so this is strictly better; and the failure mode is recoverable through a tool re-execution on the user's next request.
- **`aidial-client` version drift** — if our deployment runs against a DIAL Core that prefers a newer client surface, the pin may need to move and the pattern may need adjustment. → Mitigation: lock the version, watch the dependency in `uv.lock`, and revisit when needed.
- **No tests for the in-DIAL upload path** — our unit tests will use a fake `AsyncDial` (or `respx`-mocked httpx) rather than a real DIAL Core. Integration smoke is via `make up` + manual chat. → Mitigation: the round-trip test on a fake client covers the rewrite logic; the actual DIAL HTTP contract is owned by `aidial-client`. Manual end-to-end is in `tasks.md`.
- **Image content blocks emitted by the model itself** (not just by tools) — `_handle_ai_message` could in principle see an AIMessage whose content contains `{type: "image", ...}` blocks. Today no model used by this app emits image content on the assistant path, but if one starts to, the AIMessage will also be subject to the same 1 MB ceiling. → Mitigation: the upload walker iterates the *whole* `_messages` slice, not just ToolMessages, so AIMessage image blocks get the same treatment automatically. The decision lives in the walker, not in a per-role branch.
