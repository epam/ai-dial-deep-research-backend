#!/usr/bin/env python3
"""Drive a multi-turn conversation with the dial-deep-research app from the CLI.

The app is a *stateful* DIAL app: stateless per HTTP request, but it threads
conversation state across turns via `assistant.custom_content.state` on each
message. `app/history.py:reconstruct_history` rebuilds the agent's view by
walking the full `messages` array we send back — every `user` becomes a turn,
every `assistant` carrying a `custom_content.state` is decoded into its slice.
So the only thing a client must get right is re-sending prior assistant messages
*verbatim, state included*. The state blob is opaque — we capture and resend it,
never construct or inspect it.

This script makes the artifact file *be* the `messages` array, so threading is
verbatim by construction:

    [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "...", "custom_content": {"state": {...}}},
      ...
    ]

Modes:
  overwrite  Clear the file (if it exists), then start a fresh conversation
             with just this query. No past context is threaded.
  continue   Load prior messages from the file (error if missing/empty),
             append this query, send, and append the reply back to the file.

The file is written only after a successful response, so a failed `continue`
never corrupts existing history. (`overwrite` clears up front by design.)

The target deployment is the application instance registered in DIAL Core, passed via
`--deployment`.

Usage (from the repo root):
  poetry run python scripts/send_conversation.py "what tools are available?" -f conv.json -m overwrite -d deep-research-acme
  poetry run python scripts/send_conversation.py "and which one searches docs?" -f conv.json -m continue -d deep-research-acme
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import dotenv
import httpx

DEFAULT_TIMEOUT = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="the user message to send this turn")
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        type=Path,
        help="path to the conversation artifact (a JSON array of messages)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        required=True,
        choices=("overwrite", "continue"),
        help="overwrite: fresh conversation (clears file); continue: thread prior history",
    )
    parser.add_argument(
        "-d",
        "--deployment",
        required=True,
        help="DIAL deployment id of the application instance to call"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    return parser.parse_args()


def load_continue_history(path: Path) -> list[dict]:
    """Read prior messages for `continue` mode; raise on missing/empty/invalid."""
    if not path.exists():
        raise SystemExit(f"continue mode: file does not exist: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(f"continue mode: file is empty: {path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"continue mode: file is not valid JSON ({exc}): {path}") from None
    if not isinstance(data, list) or not data:
        raise SystemExit(f"continue mode: no prior messages found in: {path}")
    return data


def write_messages(path: Path, messages: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def conversation_id_for(path: Path) -> str:
    """A stable conversation id derived from the artifact path.

    All turns sent against the same file share this id, so the app's Opik tracer
    (which reads `X-Conversation-Id`) groups them into a single thread.
    """
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"send-conv-{digest}"


def send(
    timeout: float,
    messages: list[dict],
    conversation_id: str,
    deployment: str,
) -> dict:
    """POST the chat-completion request and return `choices[0].message` verbatim.

    The DIAL URL comes from the app settings singleton (.env); the client `Api-Key` comes
    from the `DIAL_API_KEY` env var (default: the local-stack dev key `dial_api_key`). The
    target deployment is the application instance registered in DIAL Core, passed by the
    caller.
    """
    # Imported here, not at module top: importing the settings module instantiates the
    # singleton, which must happen after main() has loaded .env.
    from dial_deep_research.settings import settings

    base_url = settings.dial_url.encoded_string().rstrip("/")
    url = f"{base_url}/openai/deployments/{deployment}/chat/completions"
    # Client-side key to authenticate to DIAL Core. The app itself no longer holds a static
    # key (it uses the per-request key), so this client supplies its own, like the chat UI.
    api_key = os.getenv("DIAL_API_KEY", "dial_api_key")
    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "X-Conversation-Id": conversation_id,
    }
    body = {"messages": messages, "stream": False}
    print(
        f"→ {url} | {len(messages)} message(s) | conversation-id {conversation_id}",
        file=sys.stderr,
    )
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
    except httpx.RequestError as exc:
        raise SystemExit(f"request failed ({url}): {exc}") from None
    if resp.status_code != 200:
        raise SystemExit(f"HTTP {resp.status_code} from {url}:\n{resp.text}")
    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise SystemExit(f"non-JSON response from {url}:\n{resp.text}") from None
    if isinstance(data, dict) and data.get("error"):
        raise SystemExit(f"API error:\n{json.dumps(data['error'], indent=2, ensure_ascii=False)}")
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise SystemExit(
            f"unexpected response shape from {url}:\n{json.dumps(data, indent=2)}"
        ) from None


def report_extras(message: dict) -> None:
    """Print a one-line note to stderr if the reply carries attachments/stages."""
    custom = message.get("custom_content") or {}
    notes = []
    if attachments := custom.get("attachments"):
        notes.append(f"{len(attachments)} attachment(s)")
    if stages := custom.get("stages"):
        notes.append(f"{len(stages)} stage(s)")
    if custom.get("state"):
        notes.append("state threaded")
    if notes:
        print(f"[{', '.join(notes)}]", file=sys.stderr)


def main() -> None:
    args = parse_args()
    dotenv.load_dotenv(os.path.join(os.getcwd(), ".env"))

    deployment = args.deployment
    if not deployment:
        raise SystemExit("no deployment id: pass --deployment")

    if args.mode == "overwrite":
        if args.file.exists():
            args.file.write_text("", encoding="utf-8")  # clear up front, by design
        messages: list[dict] = [{"role": "user", "content": args.query}]
    else:  # continue
        messages = load_continue_history(args.file)
        messages.append({"role": "user", "content": args.query})

    conversation_id = conversation_id_for(args.file)

    reply = send(
        timeout=args.timeout,
        messages=messages,
        conversation_id=conversation_id,
        deployment=deployment,
    )
    messages.append(reply)
    write_messages(args.file, messages)

    print(reply.get("content", ""))
    report_extras(reply)


if __name__ == "__main__":
    main()
