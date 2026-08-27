## 1. Spike deployment

- [x] 1.1 Add `enable_annotations_spike: bool = False` to `src/dial_deep_research/settings.py`.
- [x] 1.2 Add `ANNOTATIONS_SPIKE_DEPLOYMENT_NAME` to `src/dial_deep_research/app_properties.py`.
- [x] 1.3 Create `src/dial_deep_research/app/annotations_spike/report.py`: the fixed report text
      authored with inline placeholder markers, plus a helper that strips the markers and returns
      the clean text with each citation's character offsets, so editing the wording cannot
      desynchronise the offsets.
- [x] 1.4 Create `src/dial_deep_research/app/annotations_spike/annotations.py`: build the
      `custom_content.annotations` array from those offsets and the two PDFs' DIAL file paths,
      assigning a sequential integer `index` to every entry.
- [x] 1.5 Create `src/dial_deep_research/app/annotations_spike/completion.py`: stream the report
      text, then send one `ArbitraryChunk` carrying the annotations, then a duplicate
      `text/markdown` attachment of the report (option B from the placement analysis) and the
      reference-only `#page=N` attachment variant for side-by-side comparison.
- [x] 1.6 Register the deployment in `src/dial_deep_research/app/factory.py`, gated on
      `settings.enable_annotations_spike`, mirroring the playground registration.

## 2. PDFs

- [x] 2.1 Copy the two spike papers into the repo (or a gitignored local path) under short,
      space-free names.
- [x] 2.2 Write `scripts/upload_spike_pdfs.py`: upload both to DIAL file storage via the DIAL file
      API and print their `files/<bucket>/...` paths.
- [x] 2.3 Record the resulting paths in the spike config so the annotations reference real files.

## 3. Local stack

- [x] 3.1 Add `docker-compose.spike.yml`: override `chat` to `epam/ai-dial-chat:1.0.0-rc.6` with
      the next-gen environment (`DIAL_CORE_URL`, `THEMES_CONFIG_URL`, `AUTH_*`,
      `AUTH_COOKIE_SECURE=false`), override `themes` to `0.19.1`, and pass `.env` through with
      `env_file` so the Keycloak values are never inlined.
- [x] 3.2 Confirm the app port does not collide with the chat backend. Not needed in practice:
      the local setup already runs the app on 5011, and the chat is published on host port 3020
      (3010 was held by a stale Rancher Desktop reservation).
- [x] 3.5 Register the spike with DIAL Core: `dial_conf/core/spike-applications.json` declares it
      with a plain `endpoint`, and the overlay adds that file to core's `aidial.config.files`.
      No application-type schema is needed — the spike reads no application properties.
- [x] 3.3 Add `make spike-up` / `make spike-down` targets wrapping the two-file compose invocation.
- [ ] 3.4 Confirm plain `make infra-up` still starts the legacy stack unchanged.

## 4. Automated end-to-end check

- [x] 4.1 Write `scripts/check_spike_annotations.py`: call the deployment through DIAL Core with an
      API key and capture the full response.
- [x] 4.2 Assert the payload: `custom_content.annotations` is present; every entry has a sequential
      integer `index`; every entry has `body.source.attachment.url` (the condition `useAnnotations`
      filters on); each `target.selector.end` lands at the intended sentence in the returned
      content; and the same-page-twice pair shares one `url` while the two-different-pages pair
      does not.
- [x] 4.3 Assert Core's auto-sharing: fetch each cited `files/<bucket>/...` URL with the caller's
      key and confirm it is readable.
- [x] 4.4 Assert the non-streaming path too (`stream: false`), which exercises the SDK's
      `merge_indexed_lists` and so proves the `index` contract.

## 5. Manual browser pass

Cannot be automated — no browser driver, and reaching the UI needs an interactive Keycloak login.

- [ ] 5.1 Confirm the pill renders inline, immediately after the cited sentence (R1).
- [ ] 5.2 Click a pill and confirm it opens the correct PDF at the correct page (R2), and note
      whether the degenerate zero-size `pdf_bbox` leaves a visible artifact.
- [ ] 5.3 Confirm whether the same page cited twice renders one pill or two (R4) — the decisive
      observation for whether a DIAL Chat change is needed.
- [ ] 5.4 Compare the annotation pill against the reference-only `#page=N` trailing pill.
- [ ] 5.5 Open the duplicate markdown attachment and confirm the canvas renders it without pills,
      as the placement analysis predicts.
- [ ] 5.6 Reload and re-share the conversation, confirming the annotations survive.

## 6. Write up

- [ ] 6.1 Fold the findings into `docs/deep_research/inline_annotations.md` in the StatGPT team
      documentation repository, resolving or sharpening gaps §1, §4 and §5.
- [ ] 6.2 Decide, from the R4 observation, whether to raise an `ai-dial-chat` issue and with what
      requested behaviour.
