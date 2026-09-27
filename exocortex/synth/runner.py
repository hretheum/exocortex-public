# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Registry-driven synthesis runner.

Usage::

    from exocortex.core.registry import registry
    from exocortex.synth.runner import run, setup_builtins

    setup_builtins(registry)          # register all 10 built-in perspectives
    result = run(registry, "meeting_summary", "design-review", dry_run=True)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SynthContext:
    """Context passed to PerspectiveType methods during a synthesis run."""

    tenant_id: str
    perspective_key: str
    edges: list[dict] = field(default_factory=list)
    dry_run: bool = False
    force: bool = False


def setup_builtins(registry: Any) -> None:
    """Register all 14 built-in perspectives into *registry*."""
    from exocortex.synth.perspectives import (
        action_items_thread,
        area_digest,
        backlog_health,
        client_review,
        decision_log,
        frp_perspective,
        frp_session,
        gap_radar,
        meeting_summary,
        monthly_review,
        news_cluster,
        night_shift,
        person_profile,
        weekly_review,
    )
    for mod in (
        client_review,
        weekly_review,
        person_profile,
        monthly_review,
        decision_log,
        meeting_summary,
        action_items_thread,
        news_cluster,
        frp_perspective,
        frp_session,
        night_shift,
        gap_radar,
        area_digest,
        backlog_health,
    ):
        mod.setup(registry)


def run(
    registry: Any,
    perspective_name: str,
    perspective_key: str,
    *,
    tenant_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    source_thoughts: list[dict] | None = None,
) -> Any:
    """Run synthesis for a registered perspective.

    Resolves *perspective_name* from the registry for validation, then maps it
    to the ``_legacy_type`` key and delegates to ``synthesizer.synthesize()``
    so idempotency, persistence and cost telemetry work unchanged.

    Note: ``PerspectiveType.select_thoughts`` / ``build_prompt`` / ``parse_response``
    are NOT called here — the legacy synthesizer handles that internally.  The
    registry layer is wired up now so plugins can register perspectives; full
    polymorphic dispatch (calling the perspective interface) is a future step.
    """
    if perspective_name not in registry.perspectives:
        from exocortex.synthesizer import SynthesisResult
        return SynthesisResult(
            perspective_name, perspective_key, "error",
            reason=f"unknown perspective: {perspective_name!r}",
        )

    perspective = registry.perspectives[perspective_name]
    legacy_type = getattr(perspective, "_legacy_type", None) or perspective_name

    from exocortex.synthesizer import synthesize
    return synthesize(
        legacy_type,
        perspective_key,
        source_thoughts=source_thoughts,
        tenant_id=tenant_id,
        dry_run=dry_run,
        force=force,
    )
