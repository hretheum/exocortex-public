# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Exocortex plugin registry.

All extension points are registered here. Plugins are discovered via Python
entry_points (group 'exocortex.plugins') and, as a dev-time fallback, by
scanning a local ``plugins/`` folder.

Usage::

    from exocortex.core.registry import registry
    registry.discover()              # call once at CLI bootstrap
    registry.perspectives['client']  # retrieve registered perspective
"""
from __future__ import annotations

import importlib
import importlib.metadata
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exocortex.live_sections.base import SectionGenerator
    from exocortex.mcp.tools.base import McpTool
    from exocortex.processors.base import Processor
    from exocortex.sinks.base import Sink
    from exocortex.synth.perspectives.base import PerspectiveType
    from exocortex.wiki.domains.base import DomainCompiler

log = logging.getLogger(__name__)

SetupFn = Callable[["Registry"], None]

_PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"
_ENTRY_POINT_GROUP = "exocortex.plugins"


class Registry:
    """Central registry for all five Exocortex extension points.

    Plugins call ``register_*`` methods inside their ``setup(registry)``
    function.  The engine calls ``discover()`` once at startup before
    dispatching any subcommand.
    """

    def __init__(self) -> None:
        self.perspectives: dict[str, PerspectiveType] = {}
        self.mcp_tools: dict[str, McpTool] = {}
        self.compile_domains: dict[str, DomainCompiler] = {}
        self.capture_processors: dict[str, Processor] = {}
        self.live_sections: dict[str, SectionGenerator] = {}
        self.sinks: dict[str, Sink] = {}

    # ── registration ──────────────────────────────────────────────────────

    def register_perspective(self, handler: PerspectiveType) -> None:
        self.perspectives[handler.name] = handler
        log.debug("perspective registered: %s", handler.name)

    def register_mcp_tool(self, tool: McpTool) -> None:
        self.mcp_tools[tool.name] = tool
        log.debug("mcp_tool registered: %s", tool.name)

    def register_compile_domain(self, compiler: DomainCompiler) -> None:
        self.compile_domains[compiler.name] = compiler
        log.debug("compile_domain registered: %s", compiler.name)

    def register_capture_processor(self, processor: Processor) -> None:
        self.capture_processors[processor.source_type] = processor
        log.debug("capture_processor registered: %s", processor.source_type)

    def register_live_section(self, generator: SectionGenerator) -> None:
        self.live_sections[generator.name] = generator
        log.debug("live_section registered: %s", generator.name)

    def register_sink(self, sink: Sink) -> None:
        self.sinks[sink.name] = sink
        log.debug("sink registered: %s", sink.name)

    # ── discovery ─────────────────────────────────────────────────────────

    def discover(self) -> int:
        """Load all plugins and return the number of setup functions called.

        Not idempotent: calling discover() twice will invoke plugin setup()
        functions twice, potentially duplicating registrations (last-write wins
        for dict keys).  Call once per process at CLI bootstrap.
        """
        loaded = 0
        loaded += self._discover_entry_points()
        loaded += self._discover_plugins_folder()
        log.info("plugin discovery complete: %d setup function(s) called", loaded)
        return loaded

    def _discover_entry_points(self) -> int:
        count = 0
        try:
            eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
        except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            log.warning("entry_points discovery failed: %s", exc)
            return 0
        for ep in eps:
            try:
                setup_fn: SetupFn = ep.load()
                setup_fn(self)
                count += 1
                log.debug("entry_point loaded: %s", ep.name)
            except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
                log.error("failed to load entry_point '%s': %s", ep.name, exc)
        return count

    def _discover_plugins_folder(self) -> int:
        """Scan ``plugins/*/`` for packages exposing a ``setup(registry)`` fn."""
        if not _PLUGINS_DIR.is_dir():
            return 0
        count = 0
        plugins_str = str(_PLUGINS_DIR)
        sys.path.insert(0, plugins_str)
        try:
            for child in sorted(_PLUGINS_DIR.iterdir()):
                if not child.is_dir() or child.name.startswith("_"):
                    continue
                init = child / "__init__.py"
                if not init.exists():
                    continue
                try:
                    mod = importlib.import_module(child.name)
                    setup_fn = getattr(mod, "setup", None)
                    if callable(setup_fn):
                        setup_fn(self)
                        count += 1
                        log.debug("plugins/ folder loaded: %s", child.name)
                    else:
                        log.debug("plugins/%s: no setup() fn, skipping", child.name)
                except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
                    log.error("failed to load plugin '%s': %s", child.name, exc)
        finally:
            try:
                sys.path.remove(plugins_str)
            except ValueError:
                pass  # already removed (e.g. concurrent modification)
        return count


# Module-level singleton — importable as ``from exocortex.core.registry import registry``
registry = Registry()
