"""Router orchestrator — resolves use_case to a provider chain, runs primary
plus fallback with one retry per entry, and emits telemetry on success.

Internal module — public surface is in llm_router/__init__.py.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import replace
from typing import Any

from llm_router.exceptions import (
    BudgetExceeded,
    ConfigError,
    ProviderError,
    RoutingNotConfigured,
)
from llm_router.providers._registry import get_provider_class
from llm_router.routing import RoutingConfig
from llm_router.telemetry import emit
from llm_router.types import ProviderConfig, ProviderSpec, RoutingDecision, Usage

_logger = logging.getLogger(__name__)

# Module-level state — written once by set_routing_config(), read elsewhere.
_routing_config: RoutingConfig | None = None
_provider_cache: dict[str, Any] = {}

# Total wall-clock budget for primary + retries + full fallback chain.
_TOTAL_WALL_BUDGET_S: float = 60.0
_RETRY_BACKOFF_S: float = 1.0


def set_routing_config(config: RoutingConfig | None) -> None:
    """Install (or clear) the routing config. Resets the provider singleton cache."""
    global _routing_config
    _routing_config = config
    _provider_cache.clear()


def get_routing_config() -> RoutingConfig | None:
    return _routing_config


def _instantiate_provider(provider_cfg: ProviderConfig) -> Any:
    cached = _provider_cache.get(provider_cfg.name)
    if cached is not None:
        return cached
    cls = get_provider_class(provider_cfg.name)
    kwargs: dict[str, Any] = {
        "api_key_env": provider_cfg.api_key_env,
        "default_model": provider_cfg.default_model,
        "pricing": provider_cfg.pricing_dict() or None,
    }
    if provider_cfg.base_url is not None:
        kwargs["base_url"] = provider_cfg.base_url
    if provider_cfg.headers:
        kwargs["headers"] = provider_cfg.headers_dict()
    instance = cls(**kwargs)
    _provider_cache[provider_cfg.name] = instance
    return instance


def _estimate_cost(
    *,
    system: str,
    user: str,
    max_tokens: int,
    pricing: dict[str, float],
) -> float:
    # Rough heuristic: 4 chars/token for input, full max_tokens for output.
    input_tokens = max(1, math.ceil((len(system) + len(user)) / 4))
    output_tokens = max(1, max_tokens)
    in_rate = pricing.get("input", 0.0)
    out_rate = pricing.get("output", 0.0)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000 * 1.2


def _attempt_provider(
    *,
    provider_cfg: ProviderConfig,
    spec: ProviderSpec,
    system: str,
    user: str,
    schema: dict,
    max_tokens: int,
    cache_system: bool,
    use_case: str,
    deadline: float,
) -> tuple[dict, Usage]:
    instance = _instantiate_provider(provider_cfg)
    last_error: ProviderError | None = None
    for attempt in (0, 1):
        if time.monotonic() >= deadline:
            break
        try:
            return instance.call_tool(
                system=system,
                user=user,
                schema=schema,
                model=spec.model,
                max_tokens=max_tokens,
                cache_system=cache_system,
                use_case=use_case,
            )
        except ProviderError as exc:
            last_error = exc
            if not exc.retriable or attempt == 1:
                raise
            time.sleep(_RETRY_BACKOFF_S)
    if last_error is not None:
        raise last_error
    raise ProviderError(provider_cfg.name, "exhausted attempts before success", retriable=False)


def call_tool(
    *,
    system: str,
    user: str,
    schema: dict,
    use_case: str = "_unknown",
    max_tokens: int = 1024,
    cache_system: bool = True,
) -> tuple[dict, Usage]:
    """Public entry point — routes to a provider per use_case, runs fallback chain."""
    config = _routing_config
    if config is None:
        raise RoutingNotConfigured(
            "set_routing_config(...) must be called before call_tool()"
        )
    decision: RoutingDecision = config.resolve(use_case)

    fallback_enabled = os.environ.get("LLM_ROUTER_FALLBACK", "on").strip().lower() not in ("off", "0", "false")
    chain: list[ProviderSpec] = [decision.primary] if not fallback_enabled else [decision.primary, *decision.fallback]
    primary_cfg = config.providers[decision.primary.provider]
    estimated = _estimate_cost(
        system=system,
        user=user,
        max_tokens=max_tokens,
        pricing=primary_cfg.pricing_dict(),
    )
    if estimated > decision.cost_stop_per_call_usd:
        raise BudgetExceeded(
            use_case=use_case,
            cost_usd=estimated,
            threshold=decision.cost_stop_per_call_usd,
        )

    deadline = time.monotonic() + _TOTAL_WALL_BUDGET_S
    failed: list[str] = []
    last_error: ProviderError | None = None
    for spec in chain:
        if spec.provider not in config.providers:
            raise ConfigError(
                f"resolution returned unknown provider {spec.provider!r} "
                f"for use_case={use_case}"
            )
        provider_cfg = config.providers[spec.provider]
        try:
            tool_input, usage = _attempt_provider(
                provider_cfg=provider_cfg,
                spec=spec,
                system=system,
                user=user,
                schema=schema,
                max_tokens=max_tokens,
                cache_system=cache_system,
                use_case=use_case,
                deadline=deadline,
            )
        except ProviderError as exc:
            _logger.warning(
                "provider %s failed for use_case=%s status=%s retriable=%s: %s",
                spec.provider,
                use_case,
                exc.status,
                exc.retriable,
                exc,
            )
            failed.append(spec.provider)
            last_error = exc
            if time.monotonic() >= deadline:
                break
            continue

        usage_with_chain = replace(usage, fallback_chain=tuple(failed))
        emit(usage_with_chain)
        return tool_input, usage_with_chain

    if last_error is not None:
        raise last_error
    raise ProviderError(
        "router",
        f"empty fallback chain for use_case={use_case}",
        retriable=False,
    )


def reset_for_tests() -> None:
    """Test-only: clear module state between tests."""
    global _routing_config
    _routing_config = None
    _provider_cache.clear()
