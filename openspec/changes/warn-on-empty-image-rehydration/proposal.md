## Why

A persisted image whose stored bytes are gone is rehydrated silently into an empty image. DIAL
core answers `HTTP 200` with an empty body for such a file, and `_download_one` treats any
non-raising download as a success — so the block ends up carrying `base64: ""` and an empty image
is sent to the model. Every other download failure leaves a text placeholder and a WARNING; this
one leaves nothing to notice.

The case is not hypothetical. Measured on the local stack: uploaded file bytes live only in a
redis configured with `--save ""`, `--appendonly no` and no volume, so a `docker compose down`
drops them and leaves 0-byte files behind. A probe upload read back `HTTP 200` with 0 bytes after
the stack was restarted, and 27 of 31 images referenced by saved research conversations were
0-byte files.

## What Changes

- A download that returns no bytes is treated as a failure (`EmptyDownloadError`), so the existing
  fail-closed path runs: the image block is replaced by a text placeholder naming the loss, and the
  failure is logged as a WARNING.

## Capabilities

### Modified Capabilities

- `dial-agent-with-mcp`: the history-reconstruction requirement's rehydration-failure scenario
  currently enumerates only 404, network and auth errors. A successful-but-empty download is a
  distinct case the requirement did not name, and it now counts as a failure.

## Impact

- `src/dial_deep_research/utils/image_attachments.py`: adds `EmptyDownloadError`; `_download_one`
  raises it on an empty payload.
- `tests/test_image_attachments.py`: covers the placeholder substitution and the log record.
- No behavior change for downloads that succeed with content, or that already raise.
