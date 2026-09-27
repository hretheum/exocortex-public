# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class McpTool(ABC):
    """Contract for MCP tool implementations registered on the server."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name as it appears in the MCP schema, e.g. 'search_thoughts'."""

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """JSON Schema dict describing the tool's input parameters."""

    @abstractmethod
    def handler(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool and return a result dict."""


class _LegacyMcpTool(McpTool):
    """Thin adapter wrapping an existing mcp_server.py function.

    Subclasses set ``_legacy_fn_name`` to the function name in
    ``exocortex.mcp_server``.  ``setup_from_registry`` resolves the function
    via ``_get_fn()`` and passes it directly to ``FastMCP.add_tool()`` so
    FastMCP can introspect the full parameter-type annotations.

    The ``handler(args)`` path is available for testing and future dispatch;
    production wiring uses ``_get_fn()`` so FastMCP's schema generation is
    powered by the real function signature.
    """

    _legacy_fn_name: str = ""

    def __init__(self) -> None:
        self._fn_cache: Any = None

    @property
    def schema(self) -> dict[str, Any]:
        # FastMCP builds schema from fn annotations — setup_from_registry
        # passes _get_fn() directly to add_tool() instead of using this dict.
        return {}

    def handler(self, args: dict[str, Any]) -> Any:
        return self._get_fn()(**args)

    def _get_fn(self) -> Any:
        if self._fn_cache is not None:
            return self._fn_cache
        if not self._legacy_fn_name:
            raise AttributeError(
                f"{type(self).__name__}._legacy_fn_name is empty — "
                "subclass must set it to the function name in exocortex.mcp_server"
            )
        import importlib
        mod = importlib.import_module("exocortex.mcp_server")
        fn = getattr(mod, self._legacy_fn_name, None)
        if fn is None:
            raise AttributeError(
                f"exocortex.mcp_server has no function {self._legacy_fn_name!r}"
            )
        self._fn_cache = fn
        return fn
