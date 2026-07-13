## 1. Force the flag in code

- [x] 1.1 Add `import os` and `os.environ.setdefault("PYDANTIC_V2", "True")` as the first
      statements in `src/dial_deep_research/__init__.py`, with a short comment explaining the
      DIAL SDK reads the flag at import time and the app runs on pydantic v2.

## 2. Verify

- [x] 2.1 Add a test asserting that after importing `dial_deep_research`, the DIAL SDK is in
      pydantic v2 mode (`aidial_sdk._pydantic.PYDANTIC_V2 is True`, or the SDK `Request` model
      subclasses `pydantic.BaseModel`).
- [x] 2.2 Add a test asserting `setdefault` semantics: an explicit `PYDANTIC_V2` value already in
      the environment is not overwritten.
- [x] 2.3 Run `make format` and `make lint`; confirm the added import ordering passes.
- [x] 2.4 Run `make test`; confirm the suite passes with the SDK in pydantic v2 mode.
