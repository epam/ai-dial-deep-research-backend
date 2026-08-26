## 1. Implementation

- [x] 1.1 Add `EmptyDownloadError` to `utils/image_attachments.py`, with a message that reads
      correctly inside the placeholder template.
- [x] 1.2 Raise it from `_download_one` when `aget_content()` returns no bytes, inside the existing
      `try` so the caller's fail-closed path runs unchanged.
- [x] 1.3 Note the empty-download case in the module docstring.

## 2. Tests

- [x] 2.1 Assert an empty download leaves a text placeholder naming the loss, and no image block
      carrying an empty `base64`.
- [x] 2.2 Assert the failure is logged at WARNING.

## 3. Verification

- [x] 3.1 Run `make format` and `make lint`.
- [x] 3.2 Run the full test suite and confirm it passes.
- [x] 3.3 Run `openspec validate warn-on-empty-image-rehydration --strict`.
