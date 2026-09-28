# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Plain-text replies from local models are recovered only when safe."""
from __future__ import annotations

from llm_router.providers._openai_compat import _tool_input_from_content

PROSE = {"name": "graphrag_answer", "input_schema": {
    "type": "object", "properties": {"response": {"type": "string"}},
    "required": ["response"]}}
STRUCT = {"name": "synthesize", "input_schema": {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "decisions": {"type": "array"}},
    "required": ["summary", "decisions"]}}


def test_prose_tool_takes_plain_text() -> None:
    assert _tool_input_from_content("  Marża spadła [[acme]]. ", PROSE) == {
        "response": "Marża spadła [[acme]]."}


def test_json_object_in_content_is_used() -> None:
    text = '```json\n{"summary": "s", "decisions": []}\n```'
    assert _tool_input_from_content(text, STRUCT) == {"summary": "s", "decisions": []}


def test_structured_tool_rejects_prose() -> None:
    assert _tool_input_from_content("just words", STRUCT) is None


def test_json_missing_required_field_is_rejected() -> None:
    assert _tool_input_from_content('{"summary": "s"}', STRUCT) is None


def test_empty_or_no_schema() -> None:
    assert _tool_input_from_content("", PROSE) is None
    assert _tool_input_from_content("text", None) is None
