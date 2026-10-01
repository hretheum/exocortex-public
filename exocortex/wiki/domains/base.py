# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from exocortex.wiki.core.context import RunContext


class DomainCompiler(ABC):
    """Contract for wiki domain compilers (one per domain / tenant plugin)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Domain slug, e.g. 'work', 'frp', '3d'."""

    @abstractmethod
    def compile(self, ctx: RunContext) -> None:
        """Generate all wiki pages for this domain.

        `ctx` is a `RunContext`-compatible object.
        Must be idempotent — produces the same output given the same DB state.
        """

    def prune_orphans(self, ctx: RunContext) -> int:
        """Delete pages this domain no longer expects; return how many.

        Default is a no-op for domains that have not implemented it — the
        compile pass leaves stale files behind rather than risking a bad
        delete. Overriding is how a domain opts in (see `_ClippingsDomain`).
        """
        return 0


class _LegacyDomainCompiler(DomainCompiler):
    """Thin adapter wrapping an existing wiki_compiler.py compile function.

    Subclasses set ``_legacy_fn_name`` to the compile_X_module function name
    in ``exocortex.wiki_compiler``.  ``runner.compile_all`` sets the required
    global state (DRY_RUN, FULL_REBUILD, current_run_id) before calling
    ``compile(ctx)``, so the wrapped function sees the same environment it
    would in the legacy ``wiki_compiler.compile_all`` call.
    """

    _legacy_fn_name: str = ""

    def __init__(self) -> None:
        self._fn_cache: Any = None

    def compile(self, ctx: RunContext) -> None:
        self._get_fn()(ctx.tenant_id, ctx.since)

    def _get_fn(self) -> Any:
        if self._fn_cache is not None:
            return self._fn_cache
        if not self._legacy_fn_name:
            raise AttributeError(
                f"{type(self).__name__}._legacy_fn_name is empty — "
                "subclass must set it to the function name in exocortex.wiki_compiler"
            )
        import importlib

        mod = importlib.import_module("exocortex.wiki_compiler")
        fn = getattr(mod, self._legacy_fn_name, None)
        if fn is None:
            raise AttributeError(
                f"exocortex.wiki_compiler has no function {self._legacy_fn_name!r}"
            )
        self._fn_cache = fn
        return fn
