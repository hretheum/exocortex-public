"""llm_router — provider-agnostic LLM call_tool router.

Public surface (consumer-facing):
    call_tool(use_case, system, user, schema, ...) -> (dict, Usage)
    set_routing_config(path_or_dict_or_RoutingConfig)
    set_telemetry_sink(callable_or_None)

See docs/INTEGRATION.md for quick-start.
See docs/ARCHITECTURE.md for design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from llm_router.exceptions import (
    BudgetExceeded,
    ConfigError,
    LLMError,
    ProviderError,
    RoutingNotConfigured,
    SchemaValidationError,
)
from llm_router.providers import LLMProvider
from llm_router.router import call_tool as _router_call_tool
from llm_router.router import (
    get_routing_config,
    reset_for_tests,
    set_routing_config as _router_set_routing_config,
)
from llm_router.routing import RoutingConfig, load_routing_config
from llm_router.telemetry import set_telemetry_sink
from llm_router.types import ProviderConfig, ProviderSpec, RoutingDecision, Usage

__version__ = "0.1.1"

__all__ = [
    "__version__",
    # Public API.
    "call_tool",
    "set_routing_config",
    "set_telemetry_sink",
    # Types (re-exported for sink signatures + tests).
    "Usage",
    "ProviderConfig",
    "ProviderSpec",
    "RoutingDecision",
    "RoutingConfig",
    "LLMProvider",
    # Exceptions.
    "LLMError",
    "ProviderError",
    "BudgetExceeded",
    "SchemaValidationError",
    "ConfigError",
    "RoutingNotConfigured",
]


def set_routing_config(source: Union[str, Path, dict, RoutingConfig, None]) -> RoutingConfig | None:
    """Install routing config from a yaml path, dict, or pre-built RoutingConfig.

    Returns the resolved RoutingConfig (or None when clearing). Calling with
    None resets routing — useful between tests.
    """
    if source is None:
        _router_set_routing_config(None)
        return None
    if isinstance(source, RoutingConfig):
        config = source
    else:
        config = load_routing_config(source)
    _router_set_routing_config(config)
    return config


def call_tool(
    *,
    system: str,
    user: str,
    schema: dict,
    use_case: str = "_unknown",
    max_tokens: int = 1024,
    cache_system: bool = True,
) -> tuple[dict, Usage]:
    """Route an LLM tool call. See docs/INTEGRATION.md sec 4."""
    return _router_call_tool(
        system=system,
        user=user,
        schema=schema,
        use_case=use_case,
        max_tokens=max_tokens,
        cache_system=cache_system,
    )
