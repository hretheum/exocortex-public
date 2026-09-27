# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Live sections opt-in tools (2 tools).

Register via ``setup(registry)`` or include in a plugin's setup function.
These tools interact with the live section registry — they are opt-in extras,
not part of the 6 MUST-HAVE built-ins.
"""
from __future__ import annotations

from typing import Any

from exocortex.mcp.tools.base import _LegacyMcpTool


class ListLiveSections(_LegacyMcpTool):
    _legacy_fn_name = "list_live_sections"

    @property
    def name(self) -> str:
        return "list_live_sections"


class TriggerLiveSection(_LegacyMcpTool):
    _legacy_fn_name = "trigger_live_section"

    @property
    def name(self) -> str:
        return "trigger_live_section"


def setup(registry: Any) -> None:
    registry.register_mcp_tool(ListLiveSections())
    registry.register_mcp_tool(TriggerLiveSection())
