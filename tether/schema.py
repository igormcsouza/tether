"""Tiny JSON Schema subset validator for `--output-schema` (no `jsonschema` dependency, Rule 7).

Supports: type, enum, required, properties, items. Anything else is ignored.
"""

from __future__ import annotations

import json
from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
    "integer": (int,),
    "number": (int, float),
}


def _check(value: Any, schema: dict[str, Any], path: str) -> str | None:
    t = schema.get("type")
    if t is not None:
        ok = isinstance(value, _TYPES.get(str(t), ()))
        if t in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            return f"{path}: expected {t}, got {type(value).__name__}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: {value!r} not in {schema['enum']}"
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                return f"{path}: missing required `{key}`"
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                err = _check(value[key], sub, f"{path}.{key}")
                if err:
                    return err
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            err = _check(item, schema["items"], f"{path}[{i}]")
            if err:
                return err
    return None


def validate_output(text: str, schema: dict[str, Any]) -> str | None:
    """Return None when `text` is JSON matching `schema`, else a short error message."""
    raw = text.strip()
    if raw.startswith("```"):  # tolerate a fenced block from small models
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(raw)
    except ValueError as exc:
        return f"deliverable is not valid JSON: {exc}"
    return _check(value, schema, "$")
