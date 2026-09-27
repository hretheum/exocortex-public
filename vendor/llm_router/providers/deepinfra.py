"""DeepInfraProvider — DeepInfra OpenAI-compat endpoint.

DeepInfra ships the OpenAI-compatible REST API at `api.deepinfra.com/v1/openai`.
Cost source: response payload contains `usage.estimated_cost` (USD per call,
verified live 2026-05-04 by team-lead smoke test on Qwen 3.5-397B-A17B). Used
as primary cost source; yaml pricing + built-in pricing table act as fallbacks
if a future model omits the field.

Reasoning models (Qwen 3.5-397B-A17B et al.): the response includes
`reasoning_content` (~100-300 tokens of internal thinking) before any tool call.
Default `max_tokens=1024` will exhaust the budget on reasoning alone, leaving
nothing for the tool call. We bump to a 2048 floor for this provider.

Model IDs use DeepInfra native naming (`Qwen/Qwen3.5-397B-A17B`), NOT the
OpenRouter slug format. Caller's yaml is authoritative.
"""

from __future__ import annotations

import httpx

from llm_router.providers._openai_compat import OpenAICompatProvider
from llm_router.types import Usage


# Reasoning-budget floor — Qwen 3.5-397B-A17B (default) emits ~100-300 tokens
# of reasoning before tool call, so 1024 is too tight. Bump everywhere.
_DEEPINFRA_MAX_TOKENS_FLOOR: int = 2048


# Built-in pricing table for v0.1 (per Mtok). Yaml `pricing:` block overrides
# these defaults entirely (yaml is the source of truth; the table is only
# a safety net for misconfigured deployments). Verified live 2026-05-04
# against deepinfra.com/models/text-generation.
_DEEPINFRA_PRICING: dict[str, dict[str, float]] = {
    "Qwen/Qwen3.5-397B-A17B":  {"input": 0.54, "output": 3.40},
    "Qwen/Qwen3.5-122B-A10B":  {"input": 0.29, "output": 2.40},
    "Qwen/Qwen3.6-35B-A3B":    {"input": 0.15, "output": 0.95},
    "Qwen/Qwen3-Max":          {"input": 1.20, "output": 6.00},
    "Qwen/Qwen3-Max-Thinking": {"input": 1.20, "output": 6.00},
    # Common cross-provider models also served by DeepInfra:
    "anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    "meta-llama/Llama-4-Scout-17B": {"input": 0.27, "output": 1.10},
}


class DeepInfraProvider(OpenAICompatProvider):
    name = "deepinfra"
    supports_prompt_cache = False
    supports_strict_tool_use = True

    def __init__(
        self,
        *,
        api_key_env: str = "DEEPINFRA_API_KEY",
        default_model: str = "Qwen/Qwen3.5-397B-A17B",
        base_url: str = "https://api.deepinfra.com/v1/openai",
        headers: dict[str, str] | None = None,
        pricing: dict[str, float] | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # DeepInfra rejects OpenRouter-style attribution headers.
        super().__init__(
            api_key_env=api_key_env,
            default_model=default_model,
            base_url=base_url,
            headers=headers or {},
            pricing=pricing,
            timeout=timeout,
            transport=transport,
        )

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
        # Reasoning models need a wider token budget than the generic 1024
        # default; bump to floor without surprising callers who pass higher.
        effective_max_tokens = max(max_tokens, _DEEPINFRA_MAX_TOKENS_FLOOR)
        return super().call_tool(
            system=system,
            user=user,
            schema=schema,
            model=model,
            max_tokens=effective_max_tokens,
            cache_system=cache_system,
            use_case=use_case,
        )

    def cost_per_call(self, raw_usage: dict, model: str) -> float:
        # 1) Preferred: `usage.estimated_cost` from response payload (USD).
        payload = raw_usage.get("_payload") or {}
        usage_block = payload.get("usage") or {}
        if "estimated_cost" in usage_block:
            try:
                return float(usage_block["estimated_cost"])
            except (TypeError, ValueError):
                pass
        # 2) yaml `pricing:` block (caller-configured override).
        if self._pricing:
            p = self._pricing
        else:
            # 3) Built-in pricing table (safety net for misconfigured yaml).
            p = _DEEPINFRA_PRICING.get(model, {})
        if not p:
            # Unknown model + no yaml pricing — return 0.0 rather than raising.
            # Telemetry will record cost=0; that's a visible signal to fix yaml.
            return 0.0
        return (
            raw_usage.get("input_tokens", 0) * p.get("input", 0.0) / 1_000_000
            + raw_usage.get("output_tokens", 0) * p.get("output", 0.0) / 1_000_000
            + raw_usage.get("cache_read_input_tokens", 0)
            * p.get("cached_read", p.get("cache_read", 0.0))
            / 1_000_000
        )
