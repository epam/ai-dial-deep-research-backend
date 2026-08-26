## Context

`rehydrate_image_blocks` already has a fail-closed path: `_download_one` returns the exception it
caught, and the caller replaces the block with a text placeholder and logs a WARNING carrying the
query-stripped URL. Only the *trigger* was too narrow — a raised exception. See `proposal.md` for
how a successful-but-empty download slipped through it.

## Goals / Non-Goals

**Goals:**
- Make an empty download reach the failure path that already exists.

**Non-Goals:**
- Changing the placeholder text, the log level, or the caller's substitution logic — all of it
  already does the right thing once the failure is recognized.
- Fixing the local stack's non-persistent redis, which is what produces empty files today. That is
  a dev-environment property, and the app has to survive a missing file regardless of why it is
  missing.
- Retrying a failed download. A file whose content is gone will not appear on a retry, and the
  placeholder already keeps the turn running.

## Decisions

**1. A dedicated `EmptyDownloadError` rather than reusing a built-in.**

`str(exc)` is interpolated into the placeholder a user-facing message may quote, so the text is
part of the contract: "the stored file is empty" reads correctly there, where a bare `ValueError`
would render as an empty parenthetical. A named type also makes the WARNING's `exc_info` say what
happened rather than showing a generic error.

**2. Raised inside the existing `try`, not returned directly.**

`_download_one` has one exit convention — return the exception the `try` caught. Raising keeps that
single path, so the caller needs no new branch and the exception arrives with a traceback for
`exc_info`.

**3. Emptiness is judged on the bytes, not on a status code or a `Content-Length` header.**

`aget_content()` is the only thing the helper sees, and it is what the block would be built from —
so checking it is checking exactly the value that would have been corrupted. A status- or
header-based check would be a second source of truth that could disagree with the payload.

## Risks / Trade-offs

- **A legitimately empty file is now an error.** A zero-byte image is not a renderable image, so
  the placeholder is the more honest outcome — but if some upstream ever stores a meaningful
  zero-byte artifact, this would report it as a failure. → Accepted: the block type is `image`, and
  there is no valid empty image.
- **Turns that previously "succeeded" with an invisible empty image now show a placeholder.** That
  is the intent, and it may surface pre-existing data loss that was silently tolerated before. →
  Desirable: the loss already happened; this only makes it visible.
