# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.mcp.tools.base import _LegacyMcpTool


class FindContradictions(_LegacyMcpTool):
    _legacy_fn_name = "find_contradictions"

    @property
    def name(self) -> str:
        return "find_contradictions"


def setup(registry: Any) -> None:
    registry.register_mcp_tool(FindContradictions())
