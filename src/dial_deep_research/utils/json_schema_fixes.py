from typing import Any

from langchain_core.tools import BaseTool


def hoist_defs_to_root(tools: list[BaseTool]) -> list[BaseTool]:
    """Fix schemas emitted by MCP servers where `$defs` are nested inside properties.

    Root cause (fastmcp bug): generic-rag's `DynamicSchemasTransform` replaces a
    parameter's type via `ArgTransform`. fastmcp calls `TypeAdapter.json_schema()` for the new type,
    which returns a self-contained schema with `$defs` at its own top level, and then
    does `property_schema.update(type_schema)` — dumping `$defs` directly into the
    property node. The subsequent merge step in `_merge_schema_with_precedence` tries
    to hoist `$defs` but only inspects `override_schema["$defs"]` (top-level), missing
    the ones now buried inside `override_schema["properties"]["<param>"]["$defs"]`.

    Result: `$defs` are stranded inside a property node while every `$ref` still uses
    an absolute path (`#/$defs/...`) anchored at the schema root. LangChain's
    `dereference_refs` raises `KeyError` when it can't find `$defs` at the root.

    Fix: hoist any nested `$defs` to the schema root before the schema is used.

    TODO: newer fastmcp versions have this fixed. upgrade and remove this fix.
    """
    for tool in tools:
        schema = getattr(tool, "args_schema", None)
        if isinstance(schema, dict):
            _hoist_nested_defs(schema)
    return tools


def _hoist_nested_defs(schema: dict[str, Any]) -> None:
    """Move any `$defs` found in nested nodes up to the schema root."""
    root_defs: dict[str, Any] = schema.setdefault("$defs", {})
    _collect_nested_defs(schema, root_defs, is_root=True)
    if not root_defs:
        del schema["$defs"]


def _collect_nested_defs(node: Any, root_defs: dict[str, Any], is_root: bool = False) -> None:
    if isinstance(node, dict):
        if not is_root and "$defs" in node:
            for name, defn in node.pop("$defs").items():
                root_defs.setdefault(name, defn)
        for value in node.values():
            _collect_nested_defs(value, root_defs)
    elif isinstance(node, list):
        for item in node:
            _collect_nested_defs(item, root_defs)
