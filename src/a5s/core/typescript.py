"""TypeScript types from an API's own description (its OpenAPI document), for the studio, whose
pages read the people's API (docs/studio.md). Each schema the description names becomes a type
of the same name, so the studio reads each answer as the code that makes it says it is, and a
change to an answer changes the studio's types with it, or the tests fail
(tests/test_studio_types.py).

It covers what the API's models use, and fails on anything else rather than guess: objects,
their fields, required or not, and any others a provider's payload may have; lists, maps,
unions, null, strings, numbers and booleans.
"""

from __future__ import annotations

import json
import re
from typing import Any

HEADER = ("// The studio API's types, made from its description by `uv run python -m "
          "a5s.core.studio_api`:\n// don't edit them here, but in core/studio_models.py, and "
          "make them again.\n")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REF = "#/components/schemas/"


class Unsupported(ValueError):
    """A schema the API's description holds that this makes no type of."""


def _type(schema: dict[str, Any], indent: str) -> str:
    """The TypeScript type of a schema."""
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith(_REF):
            raise Unsupported(f"a reference outside the description's schemas: {ref}")
        return _name(ref.removeprefix(_REF))
    if "anyOf" in schema:
        return " | ".join(dict.fromkeys(_type(s, indent) for s in schema["anyOf"]))
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    kind = schema.get("type")
    if kind is None and set(schema) <= {"title", "description", "default"}:
        return "unknown"  # any value at all, as for `Any`
    if kind == "string":
        return "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "array":
        item = _type(schema.get("items", {}), indent)
        return f"({item})[]" if " | " in item else f"{item}[]"
    if kind == "object":
        return _object(schema, indent)
    raise Unsupported(f"a schema this makes no type of: {json.dumps(schema)[:200]}")


def _object(schema: dict[str, Any], indent: str) -> str:
    fields = schema.get("properties") or {}
    extra = schema.get("additionalProperties")
    if not fields:
        if isinstance(extra, dict):
            return f"Record<string, {_type(extra, indent)}>"
        return "Record<string, unknown>"
    if extra not in (None, False, True):
        raise Unsupported("an object with named fields, and others of a type besides")
    required = set(schema.get("required", []))
    inner = indent + "  "
    lines = []
    for name, field in fields.items():
        key = name if _NAME.match(name) else json.dumps(name)
        mark = "" if name in required else "?"
        lines.append(f"{inner}{key}{mark}: {_type(field, inner)};")
    if extra is True:  # a provider's own payload: the fields named, and whatever else it has
        lines.append(f"{inner}[key: string]: unknown;")
    return "{\n" + "\n".join(lines) + f"\n{indent}}}"


def _name(name: str) -> str:
    """A schema's name as a TypeScript type's: FastAPI names some with a module's path."""
    found = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not _NAME.match(found):
        raise Unsupported(f"a schema's name that makes no type's: {name}")
    return found


def types(document: dict[str, Any]) -> str:
    """The TypeScript types of every schema an API's description names, in name order."""
    schemas = document.get("components", {}).get("schemas", {})
    parts = [HEADER]
    for name in sorted(schemas):
        schema = schemas[name]
        about = schema.get("description")
        if about:
            parts.append("".join(f"// {line}".rstrip() + "\n"
                                 for line in about.strip().splitlines()))
        parts.append(f"export type {_name(name)} = {_type(schema, '')};\n\n")
    return "".join(parts).rstrip("\n") + "\n"
