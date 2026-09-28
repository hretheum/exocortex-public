# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Deterministic OpenAI-compatible stand-in for an LLM server.

Used by the CI end-to-end smoke test so the ingest -> synth -> compile ->
query path runs without a paid API key. It checks the data path, not the
quality of answers; the nightly run against a real local model covers that.

Endpoints:
  GET  /v1/models            one fake model
  POST /v1/embeddings        hashed bag-of-words vectors (lexical overlap
                             gives real cosine similarity, so retrieval works)
  POST /v1/chat/completions  with tools: a tool call whose arguments are
                             generated from the tool's JSON schema; without
                             tools: plain text

Run:  python tests/fakes/fake_llm_server.py [--host 127.0.0.1] [--port 8080]
Env:  FAKE_LLM_EMBED_DIM (default 1024, matches the bge-m3 schema)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EMBED_DIM = int(os.environ.get("FAKE_LLM_EMBED_DIM", "1024"))
MODEL_ID = "fake-llm"
_WORD = re.compile(r"[\w-]{3,}", re.UNICODE)


# ---------------------------------------------------------------------------
# embeddings
# ---------------------------------------------------------------------------


def embed(text: str) -> list[float]:
    """Hashed bag-of-words vector, L2-normalised."""
    vec = [0.0] * EMBED_DIM
    for word in _WORD.findall(text.lower()):
        h = int.from_bytes(hashlib.md5(word.encode()).digest()[:8], "big")
        vec[h % EMBED_DIM] += 1.0 if (h >> 32) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# text and schema-driven tool arguments
# ---------------------------------------------------------------------------


def summary(user: str) -> str:
    """Short deterministic answer built from the prompt itself."""
    question = ""
    for line in user.splitlines():
        if line.lower().startswith("question:"):
            question = line.split(":", 1)[1].strip()
            break
    slugs = re.findall(r"^slug:\s*(\S+)", user, flags=re.MULTILINE)
    words = _WORD.findall(question or user)
    core = " ".join(words[:40]) or "no content"
    cite = f" [[{slugs[0]}]]" if slugs else ""
    return f"Summary: {core}.{cite}"


def fill(schema: dict[str, Any], text: str, key: str = "") -> Any:
    """Smallest value that satisfies a JSON schema, with text in strings."""
    if not isinstance(schema, dict):
        return text
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    for combo in ("anyOf", "oneOf"):
        if schema.get(combo):
            options = [s for s in schema[combo] if s.get("type") != "null"]
            return fill((options or schema[combo])[0], text, key)
    if schema.get("allOf"):
        merged: dict[str, Any] = {}
        for part in schema["allOf"]:
            merged.update(part)
        return fill(merged, text, key)

    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "string")
    if kind is None:
        kind = "object" if "properties" in schema else "string"

    if kind == "object":
        props = schema.get("properties") or {}
        return {name: fill(sub, text, name) for name, sub in props.items()}
    if kind == "array":
        count = max(1, int(schema.get("minItems", 1)))
        items = schema.get("items") or {"type": "string"}
        return [fill(items, text, key) for _ in range(count)]
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 0.5))
    if kind == "boolean":
        return False
    # string
    fmt = schema.get("format")
    if fmt == "date":
        return datetime.now(UTC).date().isoformat()
    if fmt == "date-time":
        return f"{datetime.now(UTC).date().isoformat()}T00:00:00Z"
    value = text
    max_len = schema.get("maxLength")
    if max_len:
        value = value[: int(max_len)]
    min_len = int(schema.get("minLength", 0))
    if len(value) < min_len:
        value = value.ljust(min_len, ".")
    return value


def chat_completion(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages") or []
    user = "\n".join(
        m.get("content") or "" for m in messages
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    )
    text = summary(user)
    tools = body.get("tools") or []
    message: dict[str, Any]
    if tools:
        fn = tools[0].get("function") or {}
        args = fill(fn.get("parameters") or {}, text)
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_fake_0",
                "type": "function",
                "function": {"name": fn.get("name", "tool"),
                             "arguments": json.dumps(args, ensure_ascii=False)},
            }],
        }
        finish = "tool_calls"
    else:
        message = {"role": "assistant", "content": text}
        finish = "stop"
    prompt_tokens = sum(len(str(m.get("content") or "")) for m in messages) // 4
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "model": body.get("model") or MODEL_ID,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 32,
                  "total_tokens": prompt_tokens + 32},
    }


def embeddings(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("input")
    inputs = raw if isinstance(raw, list) else [raw]
    data = [{"object": "embedding", "index": i, "embedding": embed(str(t or ""))}
            for i, t in enumerate(inputs)]
    return {"object": "list", "data": data, "model": body.get("model") or MODEL_ID,
            "usage": {"prompt_tokens": 0, "total_tokens": 0}}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-llm/1"

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, {"object": "list",
                             "data": [{"id": MODEL_ID, "object": "model"}]})
        elif self.path in ("/health", "/"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        if self.path.endswith("/chat/completions"):
            self._send(200, chat_completion(body))
        elif self.path.endswith("/embeddings"):
            self._send(200, embeddings(body))
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"fake-llm: {self.command} {self.path}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write(f"fake-llm listening on {args.host}:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
