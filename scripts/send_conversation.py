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

Beside the messages file, every turn's full response is stored in a raw file next to it,
e.g. `conv.json` -> `conv.raw.json`, one entry per turn in the order sent:

    [
      {"turn": 1, "query": "...", "started_at": "...", "ended_at": "...",
       "response": {"choices": [...], "statistics": {...}, ...}, "error": null},
      ...
    ]

`started_at` and `ended_at` are UTC timestamps in ISO 8601, taken just before the request is sent
and just after the last chunk arrives or the turn fails, so their difference is the turn's wall
time as the client saw it.

`response` is the whole chat-completion response in the blocking shape, every field
kept. A streamed response is merged the way the SDK merges one into its blocking form, so
nothing it carried is lost. Fields outside the message, such as
`statistics.usage_per_model`, live only here, because the messages file cannot hold them:
its messages are resent verbatim. `turn` is the count of user messages sent so far.

A failed turn is recorded too: `error` says what failed, and `response` holds whatever
arrived before the failure, or `null` if nothing did. The messages file is written only
after a successful response, so a failed `continue` never corrupts existing history, and a
retried turn therefore appears in the raw file once per attempt, under the same `turn`.
(`overwrite` clears both files up front by design.)

The target deployment is the application instance registered in DIAL Core, passed via
`--deployment`. The DIAL Core URL is `DIAL_URL`, read from the environment or from the env file:
`--env-file`, or `.env` in the working directory by default. Which env file is read decides which
DIAL environment the conversation goes to, so a caller that must reach a specific one passes
`--env-file` explicitly. The script exits before sending anything when `DIAL_URL` is not set.

Requests stream (`stream: true`), like DIAL Chat. This matters for long turns: the app
emits keep-alive heartbeats only on the streaming path, and without them DIAL Core sees an
idle connection and closes it (its default client idle timeout is 300s), which surfaces
here as `Server disconnected without sending a response`. `--no-stream` sends one blocking
request instead — fine for short turns, and the way to exercise that path.

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
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import dotenv
import httpx

# Reassemble a streamed reply the way the SDK itself builds a blocking one, rather than
# hand-rolling delta accumulation: `aidial_sdk.utils.streaming.merge_chunks` merges every
# chunk and then runs `cleanup_indices` over the result. See `reply_from_chunks`.
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge

# Streaming makes this a per-read gap, not a budget for the whole turn: with heartbeats
# arriving every few seconds, only a stall longer than this trips it.
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
        help="DIAL deployment id of the application instance to call",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=(
            f"timeout in seconds (default: {DEFAULT_TIMEOUT}); when streaming this bounds "
            "the gap between chunks, not the whole turn"
        ),
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="send stream=false (one blocking JSON reply); see the module docstring",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="env file to read DIAL_URL and DIAL_API_KEY from (default: .env in the working directory)",
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


def raw_path_for(path: Path) -> Path:
    """The file holding every turn's full response, next to the messages file."""
    return path.with_name(f"{path.stem}.raw.json")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def append_raw_turn(
    path: Path,
    *,
    turn: int,
    query: str,
    started_at: str,
    ended_at: str,
    response: dict | None,
    error: str | None,
) -> Path:
    """Append one turn's entry to the raw file, creating the file if it is missing."""
    raw_path = raw_path_for(path)
    entries: list[dict] = []
    if raw_path.exists() and (text := raw_path.read_text(encoding="utf-8").strip()):
        entries = json.loads(text)
    entries.append(
        {
            "turn": turn,
            "query": query,
            "started_at": started_at,
            "ended_at": ended_at,
            "response": response,
            "error": error,
        }
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return raw_path


class TurnFailedError(Exception):
    """A turn that produced no usable reply. `chunks` holds whatever arrived before it."""

    def __init__(self, message: str, chunks: list[dict] | None = None) -> None:
        super().__init__(message)
        self.chunks = chunks or []


def conversation_id_for(path: Path) -> str:
    """A stable conversation id derived from the artifact path.

    All turns sent against the same file share this id, so the app's Opik tracer
    (which reads `X-Conversation-Id`) groups them into a single thread.
    """
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"send-conv-{digest}"


def iter_sse_chunks(response: httpx.Response) -> Iterator[dict]:
    """Yield the parsed `data:` payloads of an SSE response.

    Heartbeats arrive as SSE comments (`: heartbeat`) and carry no payload, so they are
    skipped here — their only job is keeping bytes on the wire.
    """
    for line in response.iter_lines():
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            return
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            raise TurnFailedError(f"non-JSON chunk in stream:\n{payload}") from None


def merge_response(chunks: list[dict]) -> dict:
    """Merge chunks into one response in the blocking shape, as the SDK builds one.

    Starting from `{}` (so no caller chunk is mutated), then `cleanup_indices` over each
    choice's accumulated delta, which becomes its `message` — the steps
    `aidial_sdk.utils.streaming.merge_chunks` performs. The cleanup is not optional: merging
    leaves the OpenAI-style `index` key on indexed list elements such as
    `custom_content.stages`, and this script resends the message verbatim on the next turn,
    where those keys would be re-slotted and stripped again (see CLAUDE.md).

    Every field outside the choices, such as `statistics`, is kept as merged, except
    top-level strings. The SDK merge concatenates strings, which is right for content deltas
    but not for `id` and `object`, which every chunk repeats in full; for those the last value
    wins. A blocking response arrives already in this shape and passes through unchanged.
    Chunks cut short by a failure merge too, so a failed turn keeps what it received.
    """
    scalars: dict[str, str] = {}
    deltas: list[dict] = []
    for chunk in chunks:
        scalars.update({key: value for key, value in chunk.items() if isinstance(value, str)})
        deltas.append({key: value for key, value in chunk.items() if not isinstance(value, str)})
    merged = merge({}, *deltas)
    merged.update(scalars)
    for choice in merged.get("choices") or []:
        if isinstance(choice, dict) and (delta := choice.pop("delta", None)) is not None:
            choice["message"] = cleanup_indices(delta)
    return merged


def reply_of(response: dict) -> dict:
    """Return `choices[0].message` of a merged response, or fail the turn."""
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        message = None
    if not isinstance(message, dict):
        raise TurnFailedError(f"no message in response:\n{json.dumps(response, indent=2)}")
    return message


def send(
    timeout: float,
    messages: list[dict],
    conversation_id: str,
    deployment: str,
    stream: bool,
) -> list[dict]:
    """POST the chat-completion request and return the chunks received.

    The chunks are every payload exactly as received — one per SSE `data:` line when
    streaming, the single JSON body when blocking. Any failure raises `TurnFailedError`
    carrying the chunks that arrived before it.

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
    body = {"messages": messages, "stream": stream}
    mode = "stream" if stream else "blocking"
    print(
        f"→ {url} | {len(messages)} message(s) | {mode} | conversation-id {conversation_id}",
        file=sys.stderr,
    )

    chunks: list[dict] = []

    def fail_on_error(payload: object) -> None:
        # `object`, not `dict`: a blocking reply is whatever `resp.json()` produced, so the
        # isinstance check is load-bearing rather than decorative.
        if isinstance(payload, dict) and payload.get("error"):
            raise TurnFailedError(
                f"API error:\n{json.dumps(payload['error'], indent=2, ensure_ascii=False)}",
                chunks,
            )

    if not stream:
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.RequestError as exc:
            raise TurnFailedError(f"request failed ({url}): {exc}") from None
        if resp.status_code != 200:
            raise TurnFailedError(f"HTTP {resp.status_code} from {url}:\n{resp.text}")
        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise TurnFailedError(f"non-JSON response from {url}:\n{resp.text}") from None
        chunks.append(data)
        fail_on_error(data)
        return chunks

    try:
        with httpx.stream("POST", url, json=body, headers=headers, timeout=timeout) as resp:
            if resp.status_code != 200:
                resp.read()
                raise TurnFailedError(f"HTTP {resp.status_code} from {url}:\n{resp.text}")
            for chunk in iter_sse_chunks(resp):
                chunks.append(chunk)
                fail_on_error(chunk)
    except httpx.RequestError as exc:
        raise TurnFailedError(f"request failed ({url}): {exc}", chunks) from None
    except TurnFailedError as exc:
        exc.chunks = chunks
        raise
    if not chunks:
        raise TurnFailedError(f"stream from {url} carried no chunks")
    return chunks


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
    env_file = args.env_file or Path(os.getcwd()) / ".env"
    if args.env_file and not env_file.is_file():
        raise SystemExit(f"env file not found: {env_file}")
    dotenv.load_dotenv(env_file)
    if not os.getenv("DIAL_URL"):
        raise SystemExit(f"DIAL_URL is not set: put it in {env_file} or in the environment")

    deployment = args.deployment
    if not deployment:
        raise SystemExit("no deployment id: pass --deployment")

    if args.mode == "overwrite":
        if args.file.exists():
            args.file.write_text("", encoding="utf-8")  # clear up front, by design
        raw_path_for(args.file).unlink(missing_ok=True)
        messages: list[dict] = [{"role": "user", "content": args.query}]
    else:  # continue
        messages = load_continue_history(args.file)
        messages.append({"role": "user", "content": args.query})

    conversation_id = conversation_id_for(args.file)

    turn = sum(1 for message in messages if message.get("role") == "user")
    chunks: list[dict] = []
    started_at = utc_now()
    try:
        chunks = send(
            timeout=args.timeout,
            messages=messages,
            conversation_id=conversation_id,
            deployment=deployment,
            stream=not args.no_stream,
        )
        response = merge_response(chunks)
        reply = reply_of(response)
    except TurnFailedError as exc:
        ended_at = utc_now()
        received = exc.chunks or chunks
        partial = merge_response(received) if received else None
        raw_path = append_raw_turn(
            args.file,
            turn=turn,
            query=args.query,
            started_at=started_at,
            ended_at=ended_at,
            response=partial,
            error=str(exc),
        )
        print(f"failed turn recorded: {raw_path}", file=sys.stderr)
        raise SystemExit(str(exc)) from None

    ended_at = utc_now()
    messages.append(reply)
    write_messages(args.file, messages)
    raw_path = append_raw_turn(
        args.file,
        turn=turn,
        query=args.query,
        started_at=started_at,
        ended_at=ended_at,
        response=response,
        error=None,
    )
    print(f"raw response: {raw_path}", file=sys.stderr)

    print(reply.get("content", ""))
    report_extras(reply)


if __name__ == "__main__":
    main()
