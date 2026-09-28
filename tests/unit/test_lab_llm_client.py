# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab model client records what came back, including failures."""
from __future__ import annotations

import json

import httpx
import pytest

from exocortex.lab.llm import LabLLM, parse_object


def _client(handler) -> LabLLM:
    return LabLLM(url="http://gw", client=httpx.Client(transport=httpx.MockTransport(handler)))


def _reply(content=None, tool_args=None, finish="stop", usage=(11, 5)):
    message = {"role": "assistant", "content": content}
    if tool_args is not None:
        message["tool_calls"] = [{"type": "function", "function": {"name": "x", "arguments": tool_args}}]
    return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": finish}],
                                     "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}})


def test_json_schema_mode_sends_the_schema_and_parses_the_reply():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return _reply(content='{"claims": []}')

    call = _client(handler).structured(model="m", system="s", user="u", schema={"type": "object"}, name="extract")
    assert call.ok and call.output == {"claims": []}
    assert call.prompt_tokens == 11 and call.completion_tokens == 5
    assert seen["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert seen["temperature"] == 0.0 and "tools" not in seen


def test_tools_mode_reads_the_tool_arguments():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return _reply(tool_args='{"claims": [{"claim": "a"}]}')

    call = _client(handler).structured(model="m", system="s", user="u", schema={"type": "object"}, name="extract",
                                       mode="tools", seed=7)
    assert call.output == {"claims": [{"claim": "a"}]}
    assert seen["tool_choice"]["function"]["name"] == "extract" and seen["seed"] == 7


def test_failures_are_reported_not_raised():
    llm = _client(lambda r: _reply(content="Sure! Here are the claims: ..."))
    call = llm.structured(model="m", system="s", user="u", schema={}, name="x")
    assert not call.ok and call.error == "no JSON object in the reply" and call.output is None

    call = _client(lambda r: _reply(content='{"claims": [', finish="length")).structured(
        model="m", system="s", user="u", schema={}, name="x")
    assert call.error == "truncated"

    call = _client(lambda r: httpx.Response(403, json={"error": "model not allowed"})).structured(
        model="m", system="s", user="u", schema={}, name="x")
    assert call.error == "http 403"

    def boom(request):
        raise httpx.ConnectError("down")

    assert _client(boom).structured(model="m", system="s", user="u", schema={}, name="x").error == "transport: ConnectError"


def test_parse_object_accepts_fenced_json_and_rejects_lists():
    assert parse_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_object("[1, 2]") is None
    assert parse_object("") is None


def test_embeddings_keep_input_order_and_batch():
    calls = []

    def handler(request):
        texts = json.loads(request.content)["input"]
        calls.append(len(texts))
        data = [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(texts)]
        return httpx.Response(200, json={"data": list(reversed(data))})

    vecs = _client(handler).embed("bge-m3", ["a", "bb", "ccc"], batch=2)
    assert vecs == [[1.0], [2.0], [3.0]] and calls == [2, 1]


def test_embedding_failure_raises():
    with pytest.raises(httpx.HTTPStatusError):
        _client(lambda r: httpx.Response(502, json={})).embed("bge-m3", ["a"])
