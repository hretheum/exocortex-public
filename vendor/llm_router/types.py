"""Frozen dataclasses for routing + usage. See ARCHITECTURE.md sec 3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Usage:
    use_case: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    started_at: datetime = field(default_factory=_utcnow)
    fallback_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderSpec:
    """A (provider, model) pair as it appears in routing yaml."""
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderConfig:
    """Static config for one provider — what set_routing_config() resolved from yaml."""
    name: str
    api_key_env: str
    default_model: str
    base_url: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    pricing: tuple[tuple[str, float], ...] = ()

    def headers_dict(self) -> dict[str, str]:
        return dict(self.headers)

    def pricing_dict(self) -> dict[str, float]:
        return dict(self.pricing)


@dataclass(frozen=True)
class RoutingDecision:
    use_case: str
    primary: ProviderSpec
    fallback: tuple[ProviderSpec, ...]
    cost_stop_per_call_usd: float
    eu_data_residency: bool = False
    shadow: ProviderSpec | None = None
