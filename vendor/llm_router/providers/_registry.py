"""Provider name → class lookup with lazy imports.

Lazy imports keep the dep tree honest: an anthropic-only consumer never has to
import httpx, an openrouter-only smoke test never has to import the anthropic
SDK, etc.
"""

from __future__ import annotations

from typing import Callable

from llm_router.exceptions import ConfigError


def _load_anthropic():
    from llm_router.providers.anthropic import AnthropicProvider
    return AnthropicProvider


def _load_openrouter():
    from llm_router.providers.openrouter import OpenRouterProvider
    return OpenRouterProvider


def _load_deepinfra():
    from llm_router.providers.deepinfra import DeepInfraProvider
    return DeepInfraProvider


_LOADERS: dict[str, Callable[[], type]] = {
    "anthropic": _load_anthropic,
    "openrouter": _load_openrouter,
    "deepinfra": _load_deepinfra,
}


def get_provider_class(name: str) -> type:
    """Resolve a provider name to its class, importing lazily.

    Raises ConfigError with the available names when `name` is unknown.
    """
    loader = _LOADERS.get(name)
    if loader is None:
        available = ", ".join(sorted(_LOADERS))
        raise ConfigError(
            f"unknown provider {name!r}; registered providers: {available}"
        )
    return loader()


def register_provider(name: str, loader: Callable[[], type]) -> None:
    """Register an additional provider at runtime (for tests / 3rd-party plugins)."""
    _LOADERS[name] = loader
