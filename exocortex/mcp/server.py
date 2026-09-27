# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Registry-driven MCP server wiring.

Usage::

    from exocortex.core.registry import registry
    from exocortex.mcp.server import setup_builtins, setup_from_registry
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("exocortex")
    setup_builtins(registry)          # register all 6 built-in tools
    setup_from_registry(registry, mcp) # wire into FastMCP
    mcp.run()                          # start stdio transport
"""
from __future__ import annotations

from typing import Any


def setup_builtins(registry: Any) -> None:
    """Register the 6 MUST-HAVE built-in MCP tools into *registry*."""
    from exocortex.mcp.tools import (
        ask,
        expand_node,
        find_action_items,
        find_contradictions,
        search_thoughts,
        synthesize,
    )
    for mod in (
        search_thoughts,
        expand_node,
        synthesize,
        find_action_items,
        find_contradictions,
        ask,
    ):
        mod.setup(registry)


def setup_from_registry(registry: Any, mcp_instance: Any) -> None:
    """Wire all McpTool instances from *registry* into *mcp_instance*.

    For ``_LegacyMcpTool`` entries the underlying mcp_server.py function is
    resolved via ``_get_fn()`` and passed directly to ``mcp_instance.add_tool()``
    so FastMCP can introspect the full parameter-type annotations (which are
    already present on the original functions).

    Note: ``_LegacyMcpTool.handler(args)`` is NOT called here — it is
    available for testing and future full-dispatch.  Production wiring goes
    through ``_get_fn()`` so FastMCP's schema generation is powered by the
    real function signature.
    """
    from exocortex.mcp.tools.base import _LegacyMcpTool

    errors: list[str] = []
    for name, tool in registry.mcp_tools.items():
        if isinstance(tool, _LegacyMcpTool):
            mcp_instance.add_tool(tool._get_fn(), name=name)
        elif hasattr(tool, "register") and callable(tool.register):  # type: ignore[union-attr]
            tool.register(mcp_instance)  # type: ignore[union-attr]
        else:
            errors.append(
                f"Non-legacy McpTool {type(tool).__name__!r} (name={name!r}): "
                "implement register(mcp_instance) or subclass _LegacyMcpTool"
            )
    if errors:
        raise NotImplementedError(
            "setup_from_registry: the following tools could not be registered:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
