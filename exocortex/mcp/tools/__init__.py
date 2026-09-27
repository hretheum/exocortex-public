# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Built-in MCP tool modules.

Each module exposes a ``setup(registry)`` function that registers one or more
``McpTool`` instances.  The 6 MUST-HAVE tools are loaded by
``exocortex.mcp.server.setup_builtins(registry)``.  The opt-in extras
(frp, promotion, live_sections) must be loaded explicitly.
"""
