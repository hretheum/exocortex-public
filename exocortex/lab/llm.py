# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Client of the lab's model gateway (exocortex/lab/llm_gateway.py).

Two calls: a chat completion that must return one JSON object, and
embeddings. A structured call asks for the object either through the
server's JSON-schema mode (a grammar in llama.cpp) or through a native tool
call, since some models support only one of the two. The result carries
the parsed object, or the reason there is none, with token counts and time,
so callers can record reliability instead of hiding it.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_URL = "unix:/run/lab-llm/gateway.sock"
_FENCE = re.compile(r"\A```(?:json)?\s*(.*?)\s*```\Z", re.DOTALL)


@dataclass
class Call:
    """Outcome of one structured call. ``output`` is None when ``error`` says why."""

    model: str
    output: dict | None = None
    error: str | None = None
    raw: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def _client(url: str, timeout: float) -> tuple[httpx.Client, str]:
    if url.startswith("unix:"):
        transport = httpx.HTTPTransport(uds=url.removeprefix("unix:"))
        return httpx.Client(transport=transport, timeout=timeout, trust_env=False), "http://gateway"
    return httpx.Client(timeout=timeout, trust_env=False), url.rstrip("/")


def parse_object(text: str) -> dict | None:
    """The JSON object in a reply, tolerating a Markdown code fence around it."""
    text = (text or "").strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


class LabLLM:
    def __init__(self, url: str | None = None, timeout: float = 900.0, client: httpx.Client | None = None):
        url = url or os.environ.get("LAB_LLM_URL", DEFAULT_URL)
        if client is not None:
            self.client, self.base = client, "http://gateway" if url.startswith("unix:") else url.rstrip("/")
        else:
            self.client, self.base = _client(url, timeout)
        self.url = url

    def structured(self, *, model: str, system: str, user: str, schema: dict, name: str,
                   mode: str = "json_schema", max_tokens: int = 2048, temperature: float = 0.0,
                   seed: int | None = None, extra: dict | None = None) -> Call:
        """One chat call that must return a JSON object matching ``schema``."""
        body: dict = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if seed is not None:
            body["seed"] = seed
        if mode == "json_schema":
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": name, "schema": schema, "strict": True}}
        elif mode == "tools":
            body["tools"] = [{"type": "function", "function": {"name": name, "parameters": schema,
                                                               "description": "Return the result."}}]
            body["tool_choice"] = {"type": "function", "function": {"name": name}}
        else:
            raise ValueError(f"unknown mode {mode!r}")
        body.update(extra or {})

        started = time.monotonic()
        call = Call(model=model)
        try:
            r = self.client.post(self.base + "/v1/chat/completions", json=body)
        except httpx.HTTPError as exc:
            call.error = f"transport: {type(exc).__name__}"
            call.latency_ms = round((time.monotonic() - started) * 1000)
            return call
        call.latency_ms = round((time.monotonic() - started) * 1000)
        if r.status_code != 200:
            call.error = f"http {r.status_code}"
            call.raw = r.text[:500]
            return call
        try:
            data = r.json()
            choice = data["choices"][0]
            message = choice.get("message") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            call.error = "malformed response"
            return call
        usage = data.get("usage") or {}
        call.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        call.completion_tokens = int(usage.get("completion_tokens") or 0)
        call.finish_reason = choice.get("finish_reason")
        tool_calls = message.get("tool_calls") or []
        if mode == "tools" and tool_calls:
            call.raw = (tool_calls[0].get("function") or {}).get("arguments") or ""
        else:
            call.raw = message.get("content") or ""
        call.output = parse_object(call.raw)
        if call.output is None:
            call.error = "truncated" if call.finish_reason == "length" else "no JSON object in the reply"
        return call

    def chat(self, *, model: str, system: str, user: str, response_format: dict | None = None,
             max_tokens: int = 2048, temperature: float = 0.0, seed: int | None = None,
             extra: dict | None = None) -> Call:
        """One chat call whose reply text is returned as it came, never parsed or repaired.

        For experiments that measure the reply itself (format conformity). ``response_format`` and ``extra``
        go into the request body as given, so a caller can force an answer format or leave it free.
        ``error`` is set only when no reply arrived (transport, HTTP status, a malformed envelope); an empty
        or unusable reply is a reply and the caller judges it.
        """
        body: dict = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if seed is not None:
            body["seed"] = seed
        if response_format is not None:
            body["response_format"] = response_format
        body.update(extra or {})
        started = time.monotonic()
        call = Call(model=model)
        try:
            r = self.client.post(self.base + "/v1/chat/completions", json=body)
        except httpx.HTTPError as exc:
            call.error = f"transport: {type(exc).__name__}"
            call.latency_ms = round((time.monotonic() - started) * 1000)
            return call
        call.latency_ms = round((time.monotonic() - started) * 1000)
        if r.status_code != 200:
            call.error = f"http {r.status_code}"
            call.raw = r.text[:500]
            return call
        try:
            data = r.json()
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise TypeError("content is not text")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            call.error = "malformed response"
            return call
        usage = data.get("usage") or {}
        call.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        call.completion_tokens = int(usage.get("completion_tokens") or 0)
        call.finish_reason = choice.get("finish_reason")
        call.raw = content
        return call

    def embed(self, model: str, texts: list[str], batch: int = 32, max_chars: int = 1000) -> list[list[float]]:
        """Unit-length embeddings in input order. Raises on any failure: callers cannot guess vectors.

        The local server embeds at most one batch of tokens per input (512
        for bge-m3 as deployed), so a text longer than ``max_chars`` is split
        at sentence ends into pieces, and its vector is the length-weighted
        mean of the pieces' vectors.
        """
        pieces: list[str] = []
        owner: list[int] = []
        for n, text in enumerate(texts):
            for piece in split_for_embedding(text, max_chars):
                pieces.append(piece)
                owner.append(n)
        vectors: list[list[float]] = []
        for i in range(0, len(pieces), batch):
            r = self.client.post(self.base + "/v1/embeddings", json={"model": model, "input": pieces[i:i + batch]})
            r.raise_for_status()
            rows = sorted(r.json()["data"], key=lambda d: d["index"])
            vectors.extend(row["embedding"] for row in rows)
        if len(vectors) != len(pieces):
            raise RuntimeError(f"expected {len(pieces)} embeddings, got {len(vectors)}")
        sums: dict[int, list[float]] = {}
        for n, piece, vec in zip(owner, pieces, vectors):
            weight = max(1, len(piece))
            acc = sums.setdefault(n, [0.0] * len(vec))
            for k, x in enumerate(vec):
                acc[k] += weight * x
        return [_unit(sums[n]) for n in range(len(texts))]


_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


def split_for_embedding(text: str, max_chars: int) -> list[str]:
    """Pieces of at most ``max_chars`` characters, cut at sentence ends where possible."""
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return [text or " "]
    pieces, current = [], ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > max_chars:  # one sentence longer than a piece: cut it at a space
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _unit(vec: list[float]) -> list[float]:
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec] if norm else vec
