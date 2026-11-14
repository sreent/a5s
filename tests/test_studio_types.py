"""The studio's TypeScript types are made from the studio API's own description
(core/studio_api.py's `described`, core/typescript.py), which each route's response model
makes (core/studio_models.py). The types the studio is built with are what the code makes now,
so the studio can't read an answer as anything but what the code says it is, and its build
checks every page against them (`npm run build`, which type-checks)."""

from pathlib import Path

import pytest

from a5s.core import studio_api, typescript

MADE = Path(__file__).parents[1] / "studio" / "src" / "api.gen.ts"
REMAKE = "uv run python -m a5s.core.studio_api > studio/src/api.gen.ts"


def test_the_studios_types_are_what_the_code_makes():
    assert MADE.read_text() == typescript.types(studio_api.described()), (
        f"the studio's types aren't what the code makes: {REMAKE}")


# The routes whose answers have no model yet, those for making agents: a list that only shrinks,
# as each gets one, so a route added without one fails here
UNTYPED = {("get", "/studio/api/tools"), ("get", "/studio/api/templates"),
           ("get", "/studio/api/drafts"), ("post", "/studio/api/drafts"),
           ("get", "/studio/api/drafts/{draft}"), ("put", "/studio/api/drafts/{draft}"),
           ("delete", "/studio/api/drafts/{draft}"), ("get", "/studio/api/drafts/{draft}/co-authors"),
           ("post", "/studio/api/drafts/{draft}/hand-over"), ("get", "/studio/api/sandbox"),
           ("post", "/studio/api/drafts/{draft}/try"), ("get", "/studio/api/drafts/{draft}/cases"),
           ("post", "/studio/api/drafts/{draft}/cases/{number}"),
           ("post", "/studio/api/drafts/{draft}/publish"), ("get", "/studio/api/publishes/{publish}"),
           ("get", "/studio/api/drafts/{draft}/pull-request")}
FILES = {("get", "/studio/api/drafts/{draft}/folder")}  # a file, not an answer to type


def test_each_answer_of_the_studios_api_has_a_type():
    """Every route of the API says what it answers, in its description, from its model: but a
    file, and those still on the list above, which only shrinks."""
    document = studio_api.described()
    untyped = {(method, path) for path, methods in document["paths"].items()
               for method, route in methods.items()
               if "$ref" not in str(route["responses"].get("200", route["responses"].get(
                   "202", {})).get("content", {}).get("application/json", {}).get("schema"))}
    assert untyped - FILES == UNTYPED, "a route whose answer has no model in core/studio_models.py"


def test_a_field_left_out_is_optional_and_one_that_may_be_null_says_so():
    found = typescript.types({"components": {"schemas": {"A": {
        "type": "object", "description": "One.\nTwo lines.",
        "properties": {"kept": {"type": "string"},
                       "absent": {"type": "array", "items": {"type": "integer"}},
                       "nullable": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                       "map": {"type": "object",
                               "additionalProperties": {"$ref": "#/components/schemas/B"}},
                       "loose": {}, "either": {"type": "array", "items": {
                           "anyOf": [{"type": "string"}, {"type": "integer"}]}}},
        "required": ["kept", "nullable", "map", "loose", "either"]},
        "B": {"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"]}}}})
    assert found.splitlines()[2:] == [
        "// One.", "// Two lines.",
        "export type A = {", "  kept: string;", "  absent?: number[];",
        "  nullable: string | null;", "  map: Record<string, B>;", "  loose: unknown;",
        "  either: (string | number)[];", "};", "",
        "export type B = {", "  on: boolean;", "};"]


@pytest.mark.parametrize("schema", [
    {"oneOf": [{"type": "string"}, {"type": "integer"}]},  # not what the models make
    {"$ref": "https://example.test/elsewhere.json"},
    {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": True},
])
def test_a_schema_it_makes_no_type_of_fails_rather_than_guess(schema):
    with pytest.raises(typescript.Unsupported):
        typescript.types({"components": {"schemas": {"A": schema}}})
