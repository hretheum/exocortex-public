"""LLMProvider Protocol — structural interface for every concrete provider.

See ARCHITECTURE.md sec 4 for the full spec.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm_router.types import Usage


@runtime_checkable
class LLMProvider(Protocol):
    """Strict tool-use call surface. Stateless except for a lazy HTTP client.

    Thread-safety: concurrent calls allowed (each provider holds a single
    httpx.Client / anthropic.Anthropic instance, both documented thread-safe).
    """

    @property
    def name(self) -> str: ...

    @property
    def supports_prompt_cache(self) -> bool: ...

    @property
    def supports_strict_tool_use(self) -> bool: ...

    def call_tool(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str,
        max_tokens: int = 1024,
        cache_system: bool = True,
        use_case: str = "_unknown",
    ) -> tuple[dict, Usage]:
        """Returns (tool_input_dict, Usage).

        Raises:
            ProviderError: transport / auth / 5xx / connection failure.
            SchemaValidationError: LLM output cannot be coerced to declared shape.
        """
        ...

    def cost_per_call(self, raw_usage: dict, model: str) -> float:
        """Compute USD cost from provider-native usage dict.

        Pure function: no I/O, no clock. Called by call_tool to populate
        Usage.cost_usd. Pricing values come from yaml config (set at __init__).
        """
        ...
