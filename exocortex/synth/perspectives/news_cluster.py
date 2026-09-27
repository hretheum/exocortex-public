# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class NewsCluster(_LegacyWrapper):
    """Synthesis perspective: newsletter/feed articles grouped by topic cluster."""

    _legacy_type = "news_cluster"

    @property
    def name(self) -> str:
        return "news_cluster"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_news_cluster
        self._ctx = ctx
        return _select_thoughts_for_news_cluster(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(NewsCluster())
