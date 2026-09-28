# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The CI stand-in LLM must return schema-valid tool calls and usable vectors."""
from __future__ import annotations

import json
import math

from tests.fakes import fake_llm_server as fake


def test_embed_is_normalised_and_sized() -> None:
    vec = fake.embed("ACME margin pressure review")
    assert len(vec) == fake.EMBED_DIM
    assert math.isclose(sum(v * v for v in vec), 1.0, rel_tol=1e-9)


def test_embed_reflects_lexical_overlap() -> None:
    query = fake.embed("Q3 margin pressure")
    near = fake.embed("ACME Q3 margin pressure review, margin fell")
    far = fake.embed("pricing model shift to value based contracts")
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert dot(query, near) > dot(query, far)


def test_fill_satisfies_nested_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "minLength": 20},
            "kind": {"type": "string", "enum": ["decision", "problem"]},
            "items": {"type": "array", "minItems": 2,
                      "items": {"type": "object",
                                "properties": {"n": {"type": "integer", "minimum": 3}}}},
            "maybe": {"type": ["string", "null"]},
            "when": {"type": "string", "format": "date"},
        },
    }
    out = fake.fill(schema, "short")
    assert len(out["summary"]) >= 20
    assert out["kind"] == "decision"
    assert out["items"] == [{"n": 3}, {"n": 3}]
    assert isinstance(out["maybe"], str)
    assert len(out["when"]) == 10


def test_chat_completion_returns_tool_call_with_citation() -> None:
    body = {
        "model": "x",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Question: what about margin?\n\nslug: acme-margin\n"},
        ],
        "tools": [{"type": "function", "function": {
            "name": "graphrag_answer",
            "parameters": {"type": "object",
                           "properties": {"response": {"type": "string"}}},
        }}],
    }
    reply = fake.chat_completion(body)
    call = reply["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "graphrag_answer"
    answer = json.loads(call["arguments"])["response"]
    assert "margin" in answer and "[[acme-margin]]" in answer


def test_chat_completion_without_tools_is_plain_text() -> None:
    reply = fake.chat_completion({"messages": [{"role": "user", "content": "hello there"}]})
    assert reply["choices"][0]["message"]["content"].startswith("Summary:")
