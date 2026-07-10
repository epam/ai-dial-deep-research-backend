import os

# The DIAL SDK reads PYDANTIC_V2 once, at import time, and defaults to pydantic v1. This app runs
# on pydantic v2, so force the SDK into v2 mode here — the package's earliest import point, which
# runs before any aidial_sdk import for the app, the tests (which do not load .env), and scripts.
# setdefault leaves an explicit environment override untouched.
os.environ.setdefault("PYDANTIC_V2", "True")
