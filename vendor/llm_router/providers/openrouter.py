"""OpenRouterProvider — OpenAI-compat client with cost parsed from response.

OpenRouter ships `usage.cost` (USD) in every response — that's the killer
feature vs. hand-rolling per-model token-rate tables. We use that as the
primary cost source, fall back to yaml pricing if a model variant ever
omits it (rare for older models).
"""

from __future__ import annotations

import httpx

from llm_router.providers._openai_compat import (
    OpenAICompatProvider,
    _to_openai_tool,
    _to_openai_tool_choice,
)


_DEFAULT_HEADERS: dict[str, str] = {
    "HTTP-Referer": "https://github.com/hretheum/router",
    "X-Title": "llm_router",
}


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    supports_prompt_cache = False
    supports_strict_tool_use = True

    def __init__(
        self,
        *,
        api_key_env: str = "OPENROUTER_API_KEY",
        default_model: str = "anthropic/claude-haiku-4.5",
        base_url: str = "https://openrouter.ai/api/v1",
        headers: dict[str, str] | None = None,
        pricing: dict[str, float] | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # OpenRouter requires HTTP-Referer + X-Title for attribution + ratelimit.
        # User-supplied headers override defaults; defaults always present.
        merged_headers = {**_DEFAULT_HEADERS, **(headers or {})}
        super().__init__(
            api_key_env=api_key_env,
            default_model=default_model,
            base_url=base_url,
            headers=merged_headers,
            pricing=pricing,
            timeout=timeout,
            transport=transport,
        )

    def cost_per_call(self, raw_usage: dict, model: str) -> float:
        # Preferred path: OpenRouter returns dollar cost in usage.cost.
        payload = raw_usage.get("_payload") or {}
        usage_block = payload.get("usage") or {}
        if "cost" in usage_block:
            try:
                return float(usage_block["cost"])
            except (TypeError, ValueError):
                pass
        # Fallback: compute from yaml pricing table.
        p = self._pricing
        if not p:
            return 0.0
        return (
            raw_usage.get("input_tokens", 0) * p.get("input", 0.0) / 1_000_000
            + raw_usage.get("output_tokens", 0) * p.get("output", 0.0) / 1_000_000
            + raw_usage.get("cache_read_input_tokens", 0)
            * p.get("cached_read", p.get("cache_read", 0.0))
            / 1_000_000
        )


__all__ = [
    "OpenRouterProvider",
    "_to_openai_tool",
    "_to_openai_tool_choice",
]
