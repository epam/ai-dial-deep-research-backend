#!/usr/bin/env python3
"""Dump (or check) the generated DIAL application-type schema artifact.

`docs/generated-app-schema.json` must always match the schema generated from
`ApplicationProperties`. Without flags the script (re)writes the artifact;
`--check` compares without writing and exits non-zero on drift — `make lint`
runs it so a model change cannot land without regenerating the artifact
(`make format` regenerates it).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dial_deep_research.app_properties import ApplicationProperties

ARTIFACT = Path(__file__).resolve().parent.parent / "docs" / "generated-app-schema.json"


def render_schema() -> str:
    schema = ApplicationProperties.model_json_schema(include_dial_fields=True)
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed artifact is stale, instead of writing it",
    )
    args = parser.parse_args()

    rendered = render_schema()
    if args.check:
        if not ARTIFACT.exists() or ARTIFACT.read_text(encoding="utf-8") != rendered:
            print(
                f"{ARTIFACT} is stale; run `poetry run python scripts/dump_app_schema.py`",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"{ARTIFACT} is up to date")
        return

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(rendered, encoding="utf-8")
    print(f"wrote {ARTIFACT}")


if __name__ == "__main__":
    main()
