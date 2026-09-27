"""AnthropicProvider — direct port of `_common.py::call_tool` from second-brain.

Behavior must match the reference impl byte-for-byte for cost parity.
"""

from __future__ import annotations

import os
import time
from typing import Any

from llm_router.exceptions import ProviderError, SchemaValidationError
from llm_router.types import Usage

# Pricing fallback (per MTok) — matches `_common.py::estimate_cost_usd`.
DEFAULT_PRICING: dict[str, float] = {
    "input": 1.00,
    "output": 5.00,
    "cache_write": 1.25,
    "cache_read": 0.10,
}


class AnthropicProvider:
    name = "anthropic"
    supports_prompt_cache = True
    supports_strict_tool_use = True

    def __init__(
        self,
        *,
        api_key_env: str = "ANTHROPIC_API_KEY",
        default_model: str = "claude-haiku-4-5-20251001",
        pricing: dict[str, float] | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._default_model = default_model
        self._pricing: dict[str, float] = {**DEFAULT_PRICING, **(pricing or {})}
        self._base_url = base_url
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy
            api_key = os.environ.get(self._api_key_env)
            if not api_key:
                raise ProviderError(
                    self.name,
                    f"api_key not set: env var {self._api_key_env} is empty",
                    retriable=False,
                )
            kwargs: dict[str, Any] = {"api_key": api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def call_tool(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str | None = None,
        max_tokens: int = 1024,
        cache_system: bool = True,
        use_case: str = "_unknown",
    ) -> tuple[dict, Usage]:
        client = self._get_client()
        resolved_model = model or self._default_model

        sys_block: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system,
                **({"cache_control": {"type": "ephemeral"}} if cache_system else {}),
            }
        ]

        started = time.monotonic()
        try:
            response = client.messages.create(
                model=resolved_model,
                max_tokens=max_tokens,
                system=sys_block,
                tools=[schema],
                tool_choice={"type": "tool", "name": schema["name"]},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        tool_input = self._extract_tool_input(response)

        raw_usage = {
            "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0
            ) or 0,
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0
            ) or 0,
        }
        cost = self.cost_per_call(raw_usage, resolved_model)

        usage = Usage(
            use_case=use_case,
            provider=self.name,
            model=resolved_model,
            input_tokens=raw_usage["input_tokens"],
            output_tokens=raw_usage["output_tokens"],
            cache_creation_input_tokens=raw_usage["cache_creation_input_tokens"],
            cache_read_input_tokens=raw_usage["cache_read_input_tokens"],
            latency_ms=latency_ms,
            cost_usd=cost,
        )
        return tool_input, usage

    def cost_per_call(self, raw_usage: dict, model: str) -> float:
        p = self._pricing
        return (
            raw_usage.get("input_tokens", 0) * p["input"] / 1_000_000
            + raw_usage.get("output_tokens", 0) * p["output"] / 1_000_000
            + raw_usage.get("cache_creation_input_tokens", 0) * p["cache_write"] / 1_000_000
            + raw_usage.get("cache_read_input_tokens", 0) * p["cache_read"] / 1_000_000
        )

    @staticmethod
    def _extract_tool_input(response: Any) -> dict:
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                tool_input = getattr(block, "input", None)
                if isinstance(tool_input, dict):
                    return tool_input
                raise SchemaValidationError("anthropic", tool_input)
        raise SchemaValidationError("anthropic", getattr(response, "content", None))

    def _map_error(self, exc: Exception) -> ProviderError:
        try:
            import anthropic
        except ImportError:
            return ProviderError(self.name, str(exc), retriable=False)

        if isinstance(exc, getattr(anthropic, "APIStatusError", tuple())):
            status = getattr(exc, "status_code", None)
            retriable = status is not None and (status >= 500 or status == 429)
            return ProviderError(
                self.name,
                f"status={status} message={exc}",
                status=status,
                retriable=retriable,
            )
        if isinstance(exc, getattr(anthropic, "AuthenticationError", tuple())):
            return ProviderError(self.name, f"auth failed: {exc}", retriable=False)
        if isinstance(exc, getattr(anthropic, "APIConnectionError", tuple())):
            return ProviderError(self.name, f"connection error: {exc}", retriable=True)
        if isinstance(exc, getattr(anthropic, "APITimeoutError", tuple())):
            return ProviderError(self.name, f"timeout: {exc}", retriable=True)
        return ProviderError(self.name, str(exc), retriable=False)
