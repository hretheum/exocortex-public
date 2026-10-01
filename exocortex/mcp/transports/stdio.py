# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""stdio transport entry-point for the registry-driven MCP server.

Run::

    python -m exocortex.mcp.transports.stdio          # start server
    python -m exocortex.mcp.transports.stdio --list   # list registered tools, exit

Opt-in extras can be loaded before calling ``setup_from_registry``::

    from exocortex.mcp.tools import frp, promotion, live_sections
    frp.setup(registry)
    promotion.setup(registry)
    live_sections.setup(registry)

TENANT_ID must be set in the environment (or in config/.env).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# Only inject repo root for direct `python path/stdio.py` invocations outside
# an installed package — when run as `python -m exocortex.mcp.transports.stdio`
# or installed via pip the package is already importable.
if __package__ is None and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=_REPO_ROOT / "config" / ".env")

from mcp.server.fastmcp import FastMCP  # noqa: E402

from exocortex.core.registry import Registry  # noqa: E402
from exocortex.mcp.server import setup_builtins, setup_from_registry  # noqa: E402


def _build_server(registry: Registry, *, extras: bool = False) -> FastMCP:
    mcp = FastMCP("exocortex")
    setup_builtins(registry)
    if extras:
        from exocortex.mcp.tools import frp, live_sections, promotion
        frp.setup(registry)
        promotion.setup(registry)
        live_sections.setup(registry)
    setup_from_registry(registry, mcp)
    return mcp


def main() -> None:
    args = sys.argv[1:]
    extras = "--extras" in args
    list_only = "--list" in args

    reg = Registry()
    mcp = _build_server(reg, extras=extras)

    if list_only:
        print(f"Registered MCP tools ({len(reg.mcp_tools)}):")
        for name in sorted(reg.mcp_tools):
            print(f"  {name}")
        return

    mcp.run()


if __name__ == "__main__":
    main()
