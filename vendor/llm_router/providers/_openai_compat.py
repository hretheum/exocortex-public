"""Shared base for OpenAI-compatible providers (OpenRouter, DeepInfra, ...).

Both OpenRouter and DeepInfra ship the same `/chat/completions` wire format.
The differences are: base_url, auth headers (attribution-required vs. not),
and how cost lands in the response (OpenRouter returns `usage.cost` in USD;
DeepInfra never does — must compute from yaml pricing).

Subclasses override `_extra_request_headers()` (attribution headers) and
`cost_per_call()` (cost source). The wire body, schema mapping, response
parsing, and error mapping are inherited unchanged.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from llm_router.exceptions import ProviderError, SchemaValidationError
from llm_router.types import Usage


def _to_openai_tool(anthropic_schema: dict) -> dict:
    """Anthropic {name, description, input_schema} → OpenAI function tool block."""
    return {
        "type": "function",
        "function": {
            "name": anthropic_schema["name"],
            "description": anthropic_schema.get("description", ""),
            "parameters": anthropic_schema["input_schema"],
        },
    }


def _to_openai_tool_choice(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


def _tool_input_from_content(content: object, schema: dict | None) -> dict | None:
    """Recover tool arguments from a plain-text reply.

    Local llama.cpp models with tool_choice="auto" sometimes answer in
    `content` instead of emitting the tool call. Accept the reply when it is
    a JSON object carrying every required field, or when the tool has a
    single required string field (a prose answer, e.g. GraphRAG) and the
    reply is non-empty text. Anything else stays a schema failure.
    """
    if not isinstance(content, str) or not content.strip() or not schema:
        return None
    params = schema.get("input_schema") or {}
    required = list(params.get("required") or [])
    props = params.get("properties") or {}
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and all(k in parsed for k in required):
        return parsed
    if len(required) == 1 and (props.get(required[0]) or {}).get("type") == "string":
        return {required[0]: text}
    return None


class OpenAICompatProvider:
    """Base impl for OpenAI-compatible REST providers.

    Subclasses override:
      - `name` (class attr)
      - `_extra_request_headers()` (return dict to merge into request headers)
      - `cost_per_call()` (compute cost from raw_usage + model)
    """

    name: str = "openai-compat"
    supports_prompt_cache: bool = False
    supports_strict_tool_use: bool = True

    def __init__(
        self,
        *,
        api_key_env: str,
        default_model: str,
        base_url: str,
        headers: dict[str, str] | None = None,
        pricing: dict[str, float] | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._extra_headers: dict[str, str] = dict(headers or {})
        self._pricing: dict[str, float] = pricing or {}
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout, transport=transport)

    # --- subclass override hooks --------------------------------------------------

    def _extra_request_headers(self) -> dict[str, str]:
        """Headers merged into every request (besides Authorization + Content-Type).

        OpenRouter overrides to inject attribution defaults; DeepInfra returns
        only what the user explicitly configured.
        """
        return dict(self._extra_headers)

    def cost_per_call(self, raw_usage: dict, model: str) -> float:
        """Subclasses MUST override.

        OpenRouter parses `usage.cost` from the response payload (cheaper +
        accurate); DeepInfra computes from token counts × yaml pricing table.
        """
        raise NotImplementedError

    # --- shared call flow ---------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise ProviderError(
                self.name,
                f"api_key not set: env var {self._api_key_env} is empty",
                retriable=False,
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **self._extra_request_headers(),
        }

    def call_tool(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str | None = None,
        max_tokens: int = 1024,
        cache_system: bool = True,  # protocol parity, no-op for OpenAI-compat v0.1
        use_case: str = "_unknown",
    ) -> tuple[dict, Usage]:
        resolved_model = model or self._default_model
        # LLM_ROUTER_OPENAI_TOOL_CHOICE=auto: opt-in for local llama.cpp servers
        # (llama-swap). llama.cpp b10079 with the Qwen3.6 jinja template ignores a
        # forced/named tool_choice whenever an explicit system message is present
        # (verified empirically on K12 2026-07-28: named+system -> plain content,
        # "auto"+system -> tool_calls, 3/3). Real OpenAI-compat APIs (OpenRouter,
        # DeepInfra) honor named tool_choice, so the default stays unchanged.
        tool_choice: object = _to_openai_tool_choice(schema["name"])
        if os.environ.get("LLM_ROUTER_OPENAI_TOOL_CHOICE") == "auto":
            tool_choice = "auto"
        body = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [_to_openai_tool(schema)],
            "tool_choice": tool_choice,
        }
        url = f"{self._base_url}/chat/completions"

        started = time.monotonic()
        try:
            response = self._client.post(url, json=body, headers=self._auth_headers())
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, f"timeout: {exc}", retriable=True) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                self.name, f"connection error: {exc}", retriable=True
            ) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            self._raise_for_status(response)

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise SchemaValidationError(self.name, response.text) from exc

        tool_input = self._extract_tool_input(payload, schema)
        raw_usage = self._normalize_usage(payload.get("usage") or {})
        cost = self.cost_per_call({**raw_usage, "_payload": payload}, resolved_model)

        usage = Usage(
            use_case=use_case,
            provider=self.name,
            model=resolved_model,
            input_tokens=raw_usage.get("input_tokens", 0),
            output_tokens=raw_usage.get("output_tokens", 0),
            cache_creation_input_tokens=raw_usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=raw_usage.get("cache_read_input_tokens", 0),
            latency_ms=latency_ms,
            cost_usd=cost,
        )
        return tool_input, usage

    @staticmethod
    def _normalize_usage(raw: dict) -> dict:
        prompt_details = raw.get("prompt_tokens_details") or {}
        cached = int(prompt_details.get("cached_tokens", 0) or 0)
        return {
            "input_tokens": int(raw.get("prompt_tokens", 0) or 0),
            "output_tokens": int(raw.get("completion_tokens", 0) or 0),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": cached,
        }

    def _extract_tool_input(self, payload: dict, schema: dict | None = None) -> dict:
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SchemaValidationError(self.name, payload) from exc

        finish_reason = choice.get("finish_reason")

        # Reasoning models (Qwen 3.5-397B-A17B et al.) return content="" + a
        # tool_calls array; non-reasoning models also use tool_calls when
        # tool_choice is set. Either way, content is irrelevant — only
        # tool_calls[0].function.arguments matters.
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # finish_reason='length' here means the LLM hit max_tokens before
            # emitting any tool call (typical for reasoning models when budget
            # is burned on reasoning_content). That's a transient capacity
            # problem; mark retriable so the router can fail over.
            if finish_reason == "length":
                raise ProviderError(
                    self.name,
                    "response truncated before tool_call emitted "
                    "(finish_reason=length); upstream budget exhausted",
                    retriable=True,
                )
            # Otherwise: real schema/format failure. Surface the diagnostic
            # hint so debugging is fast.
            recovered = _tool_input_from_content(message.get("content"), schema)
            if recovered is not None:
                return recovered
            hint = {
                "finish_reason": finish_reason,
                "has_reasoning_content": bool(message.get("reasoning_content")),
                "content_len": len(message.get("content") or ""),
            }
            raise SchemaValidationError(self.name, hint)

        try:
            arguments = tool_calls[0]["function"]["arguments"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SchemaValidationError(self.name, tool_calls) from exc

        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                # Truncated JSON mid-string is the most common shape of
                # finish_reason='length' for OpenAI-compat providers (the
                # LLM emits a `tool_calls` array but its `arguments` JSON
                # string is incomplete). Some providers (e.g. deepinfra
                # with Qwen) report finish_reason='stop' even when the
                # JSON is clearly truncated. Detect truncation by looking
                # at the tail of the string and treat as retriable.
                def _looks_like_truncation(s: str) -> bool:
                    s = s.strip()
                    if not s:
                        return False
                    # Unclosed string literal
                    if s.count('"') % 2 == 1:
                        return True
                    # Ends mid-object/array/value without closing
                    last_char = s[-1]
                    if last_char in '{[\"\'':
                        return True
                    # Missing closing braces
                    open_braces = s.count('{') - s.count('}')
                    open_brackets = s.count('[') - s.count(']')
                    if open_braces > 0 or open_brackets > 0:
                        return True
                    # Truncated key or value (ends with colon or comma)
                    if last_char in ',:':
                        return True
                    return False

                is_truncated = finish_reason == "length" or _looks_like_truncation(arguments)
                if is_truncated:
                    raise ProviderError(
                        self.name,
                        f"tool_call arguments truncated mid-JSON "
                        f"(finish_reason={finish_reason}); upstream budget exhausted",
                        retriable=True,
                    ) from exc
                raise SchemaValidationError(self.name, arguments) from exc
            if not isinstance(parsed, dict):
                raise SchemaValidationError(self.name, parsed)
            return parsed
        raise SchemaValidationError(self.name, arguments)

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = response.text
        retriable = status >= 500 or status == 429
        raise ProviderError(
            self.name,
            f"status={status} body={body!r}"[:500],
            status=status,
            retriable=retriable,
        )

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
