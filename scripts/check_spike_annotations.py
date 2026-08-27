#!/usr/bin/env python3
"""Check the inline-annotations spike's payload and DIAL Core's auto-sharing.

Everything here can be asserted without a browser. What cannot: whether the pill actually
renders inline, whether clicking it opens the right PDF page, and whether one page cited twice
collapses into a single pill. Those need the next-generation chat UI and a human.

What this does assert:

- every annotation carries a sequential integer `index` on the streaming wire — the key DIAL
  Chat merges streaming deltas by. It is deliberately absent on the blocking path: the SDK's
  `cleanup_indices` strips `index` from every list element when it assembles a non-streaming
  reply, so the check asserts it is gone there and that order carries the sequence instead;
- every annotation carries `body.source.attachment.url`, the condition `useAnnotations` filters
  on before an annotation can render at all;
- every `target.selector.end` falls inside the returned report and lands on a sentence end, so
  a pill would be placed where it was meant to be;
- the grouping shape DIAL Chat will apply (one pill per distinct attachment url);
- each cited file is readable with the caller's key, which is what Core's auto-sharing grants;
- the same holds on the non-streaming path, which runs the SDK's indexed-list merge.

Usage (from the repo root, with the stack up and the app running):
  poetry run python scripts/check_spike_annotations.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

import dotenv
import httpx
from aidial_sdk.utils.merge_chunks import merge

DEFAULT_DEPLOYMENT = "annotations-spike"
DEFAULT_TIMEOUT = 120

# A citation pill is injected after the character at `end`, so an offset that lands on the
# closing period of a sentence is the intended placement.
SENTENCE_END = "."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-d", "--deployment", default=DEFAULT_DEPLOYMENT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args()


def call_deployment(
    *, base_url: str, headers: dict[str, str], deployment: str, stream: bool, timeout: float
) -> dict[str, Any]:
    """Call the spike and return `choices[0].message`."""
    url = f"{base_url}/openai/deployments/{deployment}/chat/completions"
    body = {"messages": [{"role": "user", "content": "anything"}], "stream": stream}

    if not stream:
        response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        if response.status_code != 200:
            raise SystemExit(f"HTTP {response.status_code} from {url}:\n{response.text}")
        return response.json()["choices"][0]["message"]

    chunks: list[dict] = []
    with httpx.stream("POST", url, json=body, headers=headers, timeout=timeout) as response:
        if response.status_code != 200:
            response.read()
            raise SystemExit(f"HTTP {response.status_code} from {url}:\n{response.text}")
        for line in response.iter_lines():
            if not line or line.startswith(":"):
                continue
            payload = line.removeprefix("data:").strip()
            if not payload or payload == "[DONE]":
                continue
            chunks.append(json.loads(payload))

    # `merge` alone, deliberately without the SDK's `cleanup_indices`: that helper strips
    # `index` from every list element, and this check exists to see the annotations as DIAL
    # Chat receives them off the wire.
    choice = merge(*chunks)["choices"][0]
    return choice.get("message") or choice["delta"]


def check_annotations(*, message: dict[str, Any], label: str, expect_index: bool) -> list[str]:
    """Assert the annotation payload. Returns the failures found, empty when all held.

    `expect_index` is true only for the streaming wire. On the blocking path the SDK's
    `cleanup_indices` removes `index` from every list element, so its absence there is the
    SDK behaving as designed, and list order is what carries the sequence.
    """
    failures: list[str] = []
    content = message.get("content") or ""
    annotations = (message.get("custom_content") or {}).get("annotations")

    if not annotations:
        return [f"{label}: no custom_content.annotations in the reply"]

    print(f"  {label}: {len(annotations)} annotation(s), {len(content)} chars of content")

    indices = [a.get("index") for a in annotations]
    if expect_index:
        if indices != list(range(len(annotations))):
            failures.append(f"{label}: index is not sequential 0..N-1, got {indices}")
    elif any(i is not None for i in indices):
        failures.append(
            f"{label}: expected the SDK to strip `index` on this path, but got {indices}"
        )

    for annotation in annotations:
        index = annotation.get("index")
        url = (
            ((annotation.get("body") or {}).get("source") or {}).get("attachment") or {}
        ).get("url")
        if not url:
            failures.append(f"{label}: annotation {index} has no body.source.attachment.url")

        selector = (annotation.get("target") or {}).get("selector") or {}
        end = selector.get("end")
        if not isinstance(end, int):
            failures.append(f"{label}: annotation {index} has no integer target.selector.end")
            continue
        if not 0 <= end < len(content):
            failures.append(
                f"{label}: annotation {index} end={end} is outside the content "
                f"(0..{len(content) - 1}); DIAL Chat would clamp the pill to the end"
            )
            continue
        if content[end] != SENTENCE_END:
            failures.append(
                f"{label}: annotation {index} end={end} lands on {content[end]!r}, "
                f"not a sentence end — context: ...{content[max(0, end - 40) : end + 1]!r}"
            )

    return failures


def report_grouping(*, message: dict[str, Any]) -> list[str]:
    """Print the pill grouping DIAL Chat will apply, and return the cited urls."""
    annotations = (message.get("custom_content") or {}).get("annotations") or []
    urls = Counter(
        (((a.get("body") or {}).get("source") or {}).get("attachment") or {}).get("url")
        for a in annotations
    )
    print(f"  DIAL Chat groups by attachment url — {len(urls)} pill(s) expected:")
    for url, count in urls.items():
        print(f"    {count} annotation(s) -> {url}")
    return [url for url in urls if url]


def check_auto_sharing(
    *, base_url: str, headers: dict[str, str], urls: list[str], timeout: float
) -> list[str]:
    """Fetch each cited file with the caller's key; Core's auto-sharing should permit it."""
    failures: list[str] = []
    for url in urls:
        # The `#page=N` fragment is a viewer instruction, not part of the stored path.
        path = url.split("#", 1)[0]
        response = httpx.get(f"{base_url}/v1/{path}", headers=headers, timeout=timeout)
        if response.status_code != 200:
            failures.append(
                f"auto-sharing: HTTP {response.status_code} fetching {path} "
                "— Core did not grant the caller access to the cited file"
            )
        else:
            print(f"  readable: {path} ({len(response.content) / 1_000_000:.1f} MB)")
    return failures


def main() -> None:
    args = parse_args()
    dotenv.load_dotenv(os.path.join(os.getcwd(), ".env"))

    # Imported after .env is loaded: the import instantiates the settings singleton.
    from dial_deep_research.settings import settings

    base_url = settings.dial_url.encoded_string().rstrip("/")
    headers = {
        "Api-Key": os.getenv("DIAL_API_KEY", "dial_api_key"),
        "Content-Type": "application/json",
    }
    print(f"→ {base_url} | deployment {args.deployment}", file=sys.stderr)

    failures: list[str] = []

    print("streaming path:")
    streamed = call_deployment(
        base_url=base_url,
        headers=headers,
        deployment=args.deployment,
        stream=True,
        timeout=args.timeout,
    )
    failures += check_annotations(message=streamed, label="streaming", expect_index=True)
    urls = report_grouping(message=streamed)

    print("non-streaming path (exercises the SDK's indexed-list merge):")
    blocking = call_deployment(
        base_url=base_url,
        headers=headers,
        deployment=args.deployment,
        stream=False,
        timeout=args.timeout,
    )
    failures += check_annotations(message=blocking, label="non-streaming", expect_index=False)

    print("auto-sharing:")
    failures += check_auto_sharing(
        base_url=base_url, headers=headers, urls=urls, timeout=args.timeout
    )

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("all automated checks passed — the browser pass is what remains")


if __name__ == "__main__":
    main()
