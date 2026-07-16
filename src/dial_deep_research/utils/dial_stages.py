import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

_PREFIX = "[TOOL]"
_RESULT_EMOJI = "✅"
_ERROR_EMOJI = "❌"


class PendingToolCall(BaseModel):
    """Bookkeeping for a tool call awaiting its result."""

    start: datetime
    tool_name: str
    args_json: str


def log_tool_call_completed(
    log: logging.Logger,
    *,
    tool_call: PendingToolCall,
    tool_call_id: str,
    end: datetime,
    is_error: bool,
    level: int = logging.INFO,
) -> None:
    """Emit the tool-call event of the logging-policy INFO skeleton.

    One renderer for every runner, so the event's shape — a scraping hook — cannot
    drift between flows. Takes the caller's logger so the record carries the
    emitting flow's logger name.
    """
    log.log(
        level,
        "Tool call completed: tool=%s tool_call_id=%s duration=%.1fs outcome=%s",
        tool_call.tool_name,
        tool_call_id,
        (end - tool_call.start).total_seconds(),
        "error" if is_error else "success",
    )


def timed_stage_title(base_name: str, start: datetime, end: datetime) -> str:
    elapsed = (end - start).total_seconds()
    return f"{base_name} ({elapsed:.2f}s, start: {start:%H:%M:%S}, end: {end:%H:%M:%S})"


class DialStageToolCallFormatter:
    @classmethod
    def format_title(
        cls, tool_name: str, start: datetime, end: datetime, is_error: bool = False
    ) -> str:
        action = f"error {_ERROR_EMOJI}" if is_error else f"result {_RESULT_EMOJI}"
        return timed_stage_title(f'{_PREFIX} "{tool_name}" - {action}', start, end)

    @classmethod
    def format_body(cls, *, args_json: str, content: object, is_error: bool) -> str:
        """Render the **Input** + **Output**/**Error** markdown body for a tool stage.

        Tool content frequently arrives as one or more LangChain content blocks
        of the shape ``{"type": "text", "text": "...", "id": "..."}``; those
        are rendered as a structured **id** / **type** / **text** layout (see
        :py:meth:`_render_content_block`). Non-block content falls back to a
        single fenced code block so multi-line payloads stay readable.
        """
        output_label = "Error" if is_error else "Output"
        return (
            f"**Input**\n\n```json\n{args_json}\n```\n\n"
            f"**{output_label}**\n\n{cls._render_output_section(content)}"
        )

    @classmethod
    def _render_output_section(cls, content: object) -> str:
        """Render the body of the Output/Error section"""
        if isinstance(content, list):
            return "\n\n---\n\n".join(cls._render_output_section(item) for item in content)
        if isinstance(content, dict) and cls._looks_like_content_block(content):
            return cls._render_content_block(content)
        return str(content)

    @staticmethod
    def _looks_like_content_block(d: dict) -> bool:
        """LangChain convention: content blocks carry a ``type`` discriminator."""
        return "type" in d

    @classmethod
    def _render_content_block(cls, block: dict) -> str:
        """Render a single ``{type, text, id, ...}`` block as **id** / **type** / **text**."""
        lines: list[str] = []

        block_id = block.get("id", 'missing')
        lines.append(f"**id**: {block_id}")

        block_type = block.get("type", 'missing')
        lines.append(f"**type**: {block_type}")

        text = block.get("text")
        if text is not None:
            text_str = text if isinstance(text, str) else str(text)
            pretty, lang = cls._maybe_prettify_json(text_str)
            lines.append(f"**text**:\n\n```{lang}\n{pretty}\n```")

        return "\n\n".join(lines) if lines else "_(empty content block)_"

    @classmethod
    def _maybe_prettify_json(cls, text: str) -> tuple[str, str]:
        """Try to parse `text` as JSON; on success re-dump with indent=2.

        Recursively unwraps JSON-encoded strings inside the structure so that a
        field whose value is itself a JSON document (e.g. ``{"text": "{\"foo\": 1}"}``)
        renders as nested JSON rather than as an escaped string blob.

        Returns ``(rendered, fence_lang)``. Only objects/arrays trigger
        prettification — bare scalars round-trip to themselves so we leave them
        as-is. Any parse error falls back to the original text.
        """
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text, ""
        if not isinstance(parsed, (dict, list)):
            return text, ""
        return json.dumps(cls._deep_parse_json(parsed), indent=2, ensure_ascii=False), "json"

    @classmethod
    def _deep_parse_json(cls, value: Any) -> Any:
        """Walk ``value`` and replace any JSON-encoded object/array string with
        the parsed structure, recursing through dicts, lists, and the parsed
        result. Strings that don't parse — or that parse to a bare scalar — are
        left as-is so we don't mangle plain text that happens to look like a
        number/boolean.
        """
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
            if not isinstance(parsed, (dict, list)):
                return value
            return cls._deep_parse_json(parsed)
        if isinstance(value, dict):
            return {k: cls._deep_parse_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._deep_parse_json(item) for item in value]
        return value
