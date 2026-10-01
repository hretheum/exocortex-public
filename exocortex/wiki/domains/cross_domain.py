# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Cross-domain compiler — entity profiles spanning multiple domains."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from exocortex.wiki.domains.base import _LegacyDomainCompiler


def compile_cross_domain(tenant_id: str, since: datetime | None) -> None:
    """
    Compile cross-domain wiki pages:
    - Entity profiles (entities present in ≥2 domains)
    - Pattern detection and pattern pages
    """
    raise NotImplementedError


class CrossDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_cross_domain"

    @property
    def name(self) -> str:
        return "cross"


def setup(registry: Any) -> None:
    registry.register_compile_domain(CrossDomain())
