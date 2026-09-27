# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Backlog promotion opt-in tools (3 tools).

Register via ``setup(registry)`` or include in a plugin's setup function.
These tools write to the vault's backlog ``manual/`` folder — they are
opt-in extras, not part of the 6 MUST-HAVE built-ins.
"""
from __future__ import annotations

from typing import Any

from exocortex.mcp.tools.base import _LegacyMcpTool


class PromoteActionItems(_LegacyMcpTool):
    _legacy_fn_name = "promote_action_items"

    @property
    def name(self) -> str:
        return "promote_action_items"


class Unpromote(_LegacyMcpTool):
    _legacy_fn_name = "unpromote"

    @property
    def name(self) -> str:
        return "unpromote"


class ListPromoted(_LegacyMcpTool):
    _legacy_fn_name = "list_promoted"

    @property
    def name(self) -> str:
        return "list_promoted"


def setup(registry: Any) -> None:
    for tool in (PromoteActionItems(), Unpromote(), ListPromoted()):
        registry.register_mcp_tool(tool)
