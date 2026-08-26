## Context

The full background, the shipped DIAL capabilities, the wire format, and the open gaps live in
`docs/deep_research/inline_annotations.md` in the StatGPT team documentation repository. This
document covers only the decisions specific to building the spike.

Relevant facts established there, not re-derived here:

- Core's annotation auto-sharing landed in **0.44.0**; `docker-compose.yml` already pins
  `epam/ai-dial-core:0.45.1`, so **no Core change is needed**.
- Chat next-gen is the `1.0.0-rc.x` release line of `epam/ai-dial-chat` (same image name as the
  legacy `0.4x.x` line). It is one image: a NestJS backend-for-frontend that also serves the React
  app, listening on port 5000.
- Inline markers are injected at the `end` offset of `target.selector`
  (`text_character_range`, 0-based, inclusive). Only `end` is read; `start` is ignored.
- Markers are suppressed while `isStreaming` is true, so annotations may be sent last.
- Every annotation needs an integer `index`: the SDK's non-streaming merge asserts on it, and
  Chat merges streaming deltas by it.

## Goals / Non-Goals

**Goals:**

- Answer the three empirical questions in `proposal.md` with a running system.
- Keep the default developer experience untouched: `make infra-up` and `make app` behave exactly
  as before, and the spike deployment does not exist unless explicitly enabled.
- Automate every check that does not require a rendered browser, so the manual pass is a short,
  specific checklist rather than open-ended poking.

**Non-Goals:**

- Any real citation extraction. The report text and its citation offsets are hardcoded.
- Highlighting cited text inside the PDF, or highlighting the cited span in the report. Both are
  explicitly out of scope for the feature (R2, R3).
- Wiring annotations through StatGPT. StatGPT drops `custom_content.annotations` today; that is a
  separate fix in `statgpt-backend`, tracked in the documentation repository.
- Production-shaped code. This is a spike.

## Decisions

### Emit annotations via `ArbitraryChunk`, not a patched SDK

`Choice.send_chunk(chunk: BaseChunk)` is public and performs no validation beyond logging, and
`ArbitraryChunk.to_dict()` returns its dict unchanged. Emitting the annotations delta is therefore
a supported call, not a hack:

```python
choice.send_chunk(ArbitraryChunk({
    "choices": [{"index": choice.index, "finish_reason": None,
                 "delta": {"custom_content": {"annotations": annotations}}}],
    "usage": None,
}))
```

`ArbitraryChunk` is not in the SDK's `__all__`, so this imports from
`aidial_sdk.chat_completion.chunks` — an unexported path that could move between SDK versions.
Accepted for a spike; the upstream ask for a real `choice.add_annotation()` is recorded in the
documentation repository.

**Alternative rejected:** post-processing the response body outside the SDK. It would require
bypassing `DIALApp`'s streaming entirely and buys nothing over the above.

### Compute offsets from markers embedded in the report source

The report is a hardcoded string, so its citation offsets could be hardcoded too — but then every
edit to the wording silently invalidates them, which is exactly the failure mode hardest to
recognise in a rendered pill. Instead the report is authored with inline placeholder markers, and a
helper strips them and returns both the clean text and the resulting offsets. Editing the report
text then cannot desynchronise the offsets.

### Cover the page-navigation question with two variants in one response

The report cites the same page twice (far apart) and cites two different pages of the same PDF, and
also cites the second PDF. That single conversation answers the grouping question (R4), the
per-page pill question, and the cross-document case at once, instead of needing three runs.

Both PDF-page mechanisms are exercised so they can be compared side by side:

- a degenerate zero-size `pdf_bbox` carrying the page, on the annotation path;
- a reference-only attachment whose `reference_url` ends in `.pdf#page=N`, which is the path that
  already works today and renders as a trailing pill.

### Gate on a setting, mirroring the playground

`create_app()` already registers the playground deployment conditionally on
`settings.enable_playground_channel`. The spike follows the identical shape, so the pattern is
familiar and the default (`False`) keeps the deployment absent from `/openai/deployments`.

### Keycloak comes from `.env`, not from a container

The DIAL Chat team supplied credentials for an existing Keycloak
(`AUTH_KEYCLOAK_CLIENT_ID`, `AUTH_KEYCLOAK_SECRET`, `AUTH_KEYCLOAK_HOST`,
`AUTH_KEYCLOAK_DIAL_ROLES_FIELD`), so the overlay passes them through with `env_file` rather than
running an identity provider locally. Next-gen chat has no `AUTH_DISABLED` equivalent, so some
provider is mandatory.

`AUTH_COOKIE_SECURE=false` is set, which the upstream `.env.template` sanctions for local HTTP.
`AUTH_CALLBACK_BASE_URL` must match a redirect URI registered on that Keycloak client — the one
piece of the setup that can only fail at run time.

## Risks

- **Keycloak redirect URI mismatch.** If the client does not allow a `http://localhost:<port>`
  callback, the browser half of the spike is blocked until the DIAL Chat team adds one. The
  automated half does not depend on it, because it talks to Core directly with an API key.
- **Port 5000 is contended three ways**: next-gen chat-api, the Deep Research app default, and (on
  macOS) AirPlay Receiver. The overlay moves the app off 5000 and `make infra-config` must be re-run
  so Core's rendered application-schema endpoint follows.
- **The degenerate bbox may render a visible dot.** If it does, the fallback is to ask the DIAL Chat
  team to have `annotationToPdfCanvasContent` fall back to `parsePdfPageReference`, which the
  neighbouring reference-attachment path already does.
