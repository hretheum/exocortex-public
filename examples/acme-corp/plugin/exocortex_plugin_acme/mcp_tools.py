# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""ACME-specific MCP tool.

``AcmeQuarterlyStatus`` is a read-only DB peek that an MCP client (Claude
Desktop, the CLI ``exocortex query``, …) can invoke to get a quick rollup
of the latest ACME activity.

A real plugin's tool would usually run a domain query and synthesise the
result via the LLM; for the example we keep it pure-SQL so it exercises
the registry contract without needing API keys.
"""
from __future__ import annotations

from typing import Any

from exocortex.mcp.tools.base import McpTool


class AcmeQuarterlyStatus(McpTool):
    """Return ACME activity counts for the current and previous quarter."""

    @property
    def name(self) -> str:
        return "acme_quarterly_status"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "quarter": {
                    "type": "string",
                    "description": "Quarter slug, e.g. '2026-q2'. "
                                   "Defaults to the most recent populated quarter.",
                },
            },
            "additionalProperties": False,
        }

    def handler(self, args: dict[str, Any]) -> dict[str, Any]:
        from exocortex.db import query_all

        quarter = args.get("quarter")
        if quarter:
            where = "metadata->>'client' = 'acme' AND metadata->>'quarter' = %s"
            params: tuple = (quarter,)
        else:
            where = "metadata->>'client' = 'acme'"
            params = ()

        # `where` is a hardcoded literal — user input flows only through %s params
        rows = query_all(
            f"""
            SELECT metadata->>'project'  AS project,
                   metadata->>'type'     AS type,
                   COUNT(*)              AS n
              FROM thoughts
             WHERE {where}
             GROUP BY 1, 2
             ORDER BY 1, 2
            """,
            params,
        ) or []

        return {
            "quarter": quarter or "all",
            "by_project_and_type": [dict(r) for r in rows],
            "total": sum(int(r["n"]) for r in rows),
        }
