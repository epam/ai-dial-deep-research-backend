## Why

DIAL now has everything needed for inline citation pills, but nothing in our stack produces them.
DIAL Core auto-shares cited attachments from `custom_content.annotations[*].body.source.attachment`
(epam/ai-dial-core#1560, in Core since 0.44.0), and DIAL Chat next-gen renders inline citation
markers from `custom_content.annotations[]` (`libs/quotations`, shipped in the `1.0.0-rc.x` line).
Deep Research is the intended first producer: it emits a long final report, all at once rather than
incrementally, which is the easy case for computing citation offsets.

Several questions cannot be answered by reading the DIAL source, only by running it:

- Does a degenerate zero-size `pdf_bbox` (`x1=y1=x2=y2=0`) actually navigate the PDF viewer to a
  page, and does it leave a visible artifact? `annotationsToPdfHighlights` applies a hardcoded
  visible style (2px border, 0.5 opacity), unlike the reference-attachment path which uses a
  transparent one. We need page navigation without highlighting.
- Does citing the *same* page in two distant places in the report really collapse into one pill?
  `groupAnnotationsBySource` groups by `body.source.attachment.url` and renders one marker per
  group at the *first* annotation's offset, which would silently drop the second citation.
- Does the whole chain hold end to end — the app's emitted payload, Core's auto-sharing, and the
  rendered result?

This change is a **local-only spike** to answer them. It is deliberately throwaway: it changes no
Deep Research behaviour and ships nothing to any environment.

## What Changes

- A new `annotations-spike` chat-completion deployment, registered only when
  `ENABLE_ANNOTATIONS_SPIKE` is true (default false), mirroring how `enable_playground_channel`
  gates the playground. It ignores the user's message and replies with a fixed report referencing
  two PDFs, plus a hand-built `custom_content.annotations` array.
- Annotations are emitted through `choice.send_chunk(ArbitraryChunk(...))`, because the DIAL SDK
  has no annotations API at 0.39.0 or at HEAD. `send_chunk` is public and `ArbitraryChunk` returns
  whatever dict it is given, so this needs no SDK change and no monkey-patching.
- A `docker-compose.spike.yml` opt-in overlay that swaps the chat UI to next-gen
  (`epam/ai-dial-chat:1.0.0-rc.6`), bumps themes to `0.19.1`, and passes the Keycloak variables
  through from `.env`. Plain `make infra-up` is untouched.
- A script that uploads the two spike PDFs to DIAL file storage and prints their
  `files/<bucket>/...` paths, since `body.source.attachment.url` must be a DIAL file for Core's
  auto-sharing to have something to grant.
- An automated end-to-end check that drives the deployment through Core and asserts the response
  payload, covering everything short of browser rendering.

## Capabilities

### Modified Capabilities

- `local-stack`: gains the spike Compose overlay and the flag-gated spike deployment. Both are
  local-development affordances, which is what this capability owns. No product capability
  (`research-execution`, `report-composition`) changes — the spike does not touch how Deep
  Research researches or writes reports.

## Impact

- **New**: `docker-compose.spike.yml`, `scripts/upload_spike_pdfs.py`,
  `src/dial_deep_research/app/annotations_spike/`, and a spike section in the local-stack docs.
- **Modified**: `src/dial_deep_research/app/factory.py` (register the third deployment),
  `src/dial_deep_research/settings.py` (the gating flag).
- **Not affected**: the research graph, the report writer, prompts, MCP wiring, and every existing
  deployment. With the flag off — the default — the app behaves exactly as before.
- **Throwaway**: this change is expected to be reverted or heavily rewritten once the findings land
  in `docs/deep_research/inline_annotations.md` (StatGPT team documentation repository). It is not
  a foundation to build the real producer on.
