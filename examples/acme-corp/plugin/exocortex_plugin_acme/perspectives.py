# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""ACME-specific synthesis perspective.

A perspective is a recipe for asking the LLM to produce one synthesis row
from a group of thoughts. `AcmeClientReview` groups thoughts tagged ``acme``
by quarter and asks for a short executive summary.

Real plugins typically delegate to ``exocortex.synthesizer`` helpers; this
example keeps everything inline so the contract is obvious.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from exocortex.synth.perspectives.base import PerspectiveType


class AcmeClientReview(PerspectiveType):
    """One synthesis per (client=acme, quarter) — executive review."""

    @property
    def name(self) -> str:
        return "acme_client_review"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        """Return ACME-tagged thoughts for the perspective key.

        ``ctx.perspective_key`` is expected to be a quarter slug
        (e.g. ``"2026-q2"``). The synth runner will hand us a context
        object with ``tenant_id`` + ``perspective_key`` — we keep both
        for ``build_prompt``.
        """
        # ordering: select_thoughts stores ctx; parse_response reads it — caller must call select_thoughts first
        self._ctx = ctx
        # Lazy import so plugin discovery never touches the DB.
        from exocortex.db import query_all
        rows = query_all(
            """
            SELECT id, body_md, metadata, created_at
              FROM thoughts
             WHERE tenant_id = %s
               AND metadata->>'client' = 'acme'
               AND metadata->>'quarter' = %s
             ORDER BY created_at
            """,
            (ctx.tenant_id, ctx.perspective_key),
        )
        return list(rows or [])

    def build_prompt(self, thoughts: list[Any]) -> str:
        bullets = "\n".join(
            f"- {(t.get('metadata') or {}).get('title') or t.get('id')}: "
            f"{(t.get('body_md') or '')[:160]}"
            for t in thoughts
        ) or "(no thoughts available — produce an empty summary)"

        return (
            "You are a strategic assistant for an external consultant working "
            "with ACME Corp. Summarize the quarter in 4 short paragraphs:\n"
            "1. What we shipped / decided\n"
            "2. What slipped or went wrong\n"
            "3. Open risks (margin, stakeholder sentiment, timeline)\n"
            "4. Recommended focus for next quarter\n\n"
            "Source thoughts:\n"
            f"{bullets}\n"
        )

    def parse_response(self, response: str) -> dict[str, Any]:
        """Return a dict matching the syntheses table contract."""
        return {
            "perspective_type": self.name,
            "perspective_key": getattr(self._ctx, "perspective_key", "unknown"),
            "body_md": response.strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
