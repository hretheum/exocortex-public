# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""FRP workflow opt-in tools (6 tools).

Register via ``setup(registry)`` or include in a plugin's setup function.
These tools are NOT part of the 6 MUST-HAVE built-ins — they are opt-in
extras for users who use the Futures Reading Protocol workflow.
"""
from __future__ import annotations

from typing import Any

from exocortex.mcp.tools.base import _LegacyMcpTool


class QueryContentQueue(_LegacyMcpTool):
    _legacy_fn_name = "query_content_queue"

    @property
    def name(self) -> str:
        return "query_content_queue"


class CreateFrpSession(_LegacyMcpTool):
    _legacy_fn_name = "create_frp_session"

    @property
    def name(self) -> str:
        return "create_frp_session"


class AppendSessionThought(_LegacyMcpTool):
    _legacy_fn_name = "append_session_thought"

    @property
    def name(self) -> str:
        return "append_session_thought"


class CompleteSession(_LegacyMcpTool):
    _legacy_fn_name = "complete_session"

    @property
    def name(self) -> str:
        return "complete_session"


class EnqueueGeneratedFrpStory(_LegacyMcpTool):
    _legacy_fn_name = "enqueue_generated_frp_story"

    @property
    def name(self) -> str:
        return "enqueue_generated_frp_story"


class AddRevisit(_LegacyMcpTool):
    _legacy_fn_name = "add_revisit"

    @property
    def name(self) -> str:
        return "add_revisit"


def setup(registry: Any) -> None:
    for tool in (
        QueryContentQueue(),
        CreateFrpSession(),
        AppendSessionThought(),
        CompleteSession(),
        EnqueueGeneratedFrpStory(),
        AddRevisit(),
    ):
        registry.register_mcp_tool(tool)
