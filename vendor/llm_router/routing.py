"""YAML routing config loader + use_case → RoutingDecision resolver.

See ARCHITECTURE.md sec 6 for the schema and resolution priority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from llm_router.exceptions import ConfigError
from llm_router.types import ProviderConfig, ProviderSpec, RoutingDecision

# Providers that v0.1 considers EU-data-residency-safe. Treated as an explicit
# allow-list — any provider not on this list is rejected when a use_case sets
# eu_data_residency: true.
_EU_SAFE_PROVIDERS: frozenset[str] = frozenset({"anthropic"})


class RoutingConfig:
    """In-memory, validated routing config.

    Built once at startup via `set_routing_config()`. Read-only afterwards.
    """

    def __init__(
        self,
        providers: dict[str, ProviderConfig],
        defaults: RoutingDecision,
        use_cases: dict[str, RoutingDecision],
    ) -> None:
        self._providers = providers
        self._defaults = defaults
        self._use_cases = use_cases

    @property
    def providers(self) -> dict[str, ProviderConfig]:
        return self._providers

    def resolve(self, use_case: str) -> RoutingDecision:
        """Resolution priority: exact → prefix `<x>.*` → defaults."""
        # 1. Exact match.
        if use_case in self._use_cases:
            return self._use_cases[use_case]
        # 2. Prefix match: longest `<prefix>.*` key that prefixes use_case.
        best: tuple[int, str] | None = None
        for key in self._use_cases:
            if key.endswith(".*"):
                prefix = key[:-2]
                if use_case.startswith(prefix + ".") or use_case == prefix:
                    if best is None or len(prefix) > best[0]:
                        best = (len(prefix), key)
        if best is not None:
            return self._use_cases[best[1]]
        # 3. defaults block.
        return self._defaults


def _parse_provider_config(name: str, raw: dict[str, Any]) -> ProviderConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"providers.{name}: expected mapping, got {type(raw).__name__}")
    if "api_key_env" not in raw:
        raise ConfigError(f"providers.{name}: missing required field 'api_key_env'")
    if "default_model" not in raw:
        raise ConfigError(f"providers.{name}: missing required field 'default_model'")
    headers = raw.get("headers") or {}
    pricing = raw.get("pricing") or {}
    if not isinstance(headers, dict):
        raise ConfigError(f"providers.{name}.headers: expected mapping")
    if not isinstance(pricing, dict):
        raise ConfigError(f"providers.{name}.pricing: expected mapping")
    return ProviderConfig(
        name=name,
        api_key_env=str(raw["api_key_env"]),
        default_model=str(raw["default_model"]),
        base_url=raw.get("base_url"),
        headers=tuple((str(k), str(v)) for k, v in headers.items()),
        pricing=tuple((str(k), float(v)) for k, v in pricing.items()),
    )


def _parse_provider_spec(raw: Any, *, where: str) -> ProviderSpec:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: expected mapping with 'provider' + 'model'")
    if "provider" not in raw or "model" not in raw:
        raise ConfigError(f"{where}: missing 'provider' or 'model' key")
    return ProviderSpec(provider=str(raw["provider"]), model=str(raw["model"]))


def _parse_decision(
    use_case: str,
    raw: dict[str, Any],
    *,
    providers: dict[str, ProviderConfig],
    require_cost_stop: bool,
) -> RoutingDecision:
    if "primary" not in raw:
        raise ConfigError(f"use_cases.{use_case}: missing 'primary'")
    primary = _parse_provider_spec(raw["primary"], where=f"use_cases.{use_case}.primary")
    fallback_raw = raw.get("fallback") or []
    if not isinstance(fallback_raw, list):
        raise ConfigError(f"use_cases.{use_case}.fallback: expected list")
    fallback = tuple(
        _parse_provider_spec(item, where=f"use_cases.{use_case}.fallback[{i}]")
        for i, item in enumerate(fallback_raw)
    )
    eu_residency = bool(raw.get("eu_data_residency", False))
    cost_stop = raw.get("cost_stop_per_call_usd")
    if cost_stop is None:
        if require_cost_stop:
            raise ConfigError(
                f"use_cases.{use_case}: 'cost_stop_per_call_usd' is required"
            )
        cost_stop_value = float("inf")
    else:
        cost_stop_value = float(cost_stop)
    shadow = None
    if "shadow" in raw and raw["shadow"] is not None:
        shadow = _parse_provider_spec(
            raw["shadow"], where=f"use_cases.{use_case}.shadow"
        )

    # Validate referenced providers exist.
    for spec, label in [(primary, "primary"), *((s, "fallback") for s in fallback)]:
        if spec.provider not in providers:
            raise ConfigError(
                f"use_cases.{use_case}.{label}: provider {spec.provider!r} "
                f"not declared in providers: section"
            )
    if shadow is not None and shadow.provider not in providers:
        raise ConfigError(
            f"use_cases.{use_case}.shadow: provider {shadow.provider!r} "
            f"not declared in providers: section"
        )

    # EU residency enforcement.
    if eu_residency:
        non_eu = [s.provider for s in (primary, *fallback) if s.provider not in _EU_SAFE_PROVIDERS]
        if non_eu:
            raise ConfigError(
                f"use_cases.{use_case}: eu_data_residency=true but chain "
                f"references non-EU-safe providers: {non_eu}"
            )

    return RoutingDecision(
        use_case=use_case,
        primary=primary,
        fallback=fallback,
        cost_stop_per_call_usd=cost_stop_value,
        eu_data_residency=eu_residency,
        shadow=shadow,
    )


def load_routing_config(source: str | Path | dict) -> RoutingConfig:
    """Load + validate yaml at `source` (path or already-parsed dict)."""
    if isinstance(source, dict):
        raw = source
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise ConfigError(f"routing config not found: {path}")
        with path.open() as f:
            raw = yaml.safe_load(f) or {}
    else:
        raise ConfigError(
            f"routing config: source must be a path or dict, got {type(source).__name__}"
        )
    if not isinstance(raw, dict):
        raise ConfigError("routing config: top-level must be a mapping")

    providers_raw = raw.get("providers") or {}
    if not isinstance(providers_raw, dict) or not providers_raw:
        raise ConfigError("routing config: 'providers' section is required and must have entries")
    providers = {
        name: _parse_provider_config(name, cfg)
        for name, cfg in providers_raw.items()
    }

    defaults_raw = raw.get("defaults")
    if not defaults_raw:
        raise ConfigError("routing config: 'defaults' section is required")
    defaults = _parse_decision(
        "_default",
        defaults_raw,
        providers=providers,
        require_cost_stop=False,
    )

    use_cases_raw = raw.get("use_cases") or {}
    if not isinstance(use_cases_raw, dict):
        raise ConfigError("routing config: 'use_cases' must be a mapping")
    use_cases: dict[str, RoutingDecision] = {}
    for key, cfg in use_cases_raw.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"use_cases.{key}: expected mapping")
        use_cases[str(key)] = _parse_decision(
            str(key),
            cfg,
            providers=providers,
            require_cost_stop=True,
        )

    return RoutingConfig(providers=providers, defaults=defaults, use_cases=use_cases)
