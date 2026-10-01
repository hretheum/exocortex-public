# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for Registry discovery and registration."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from exocortex.core.registry import _ENTRY_POINT_GROUP, Registry
from exocortex.live_sections.base import SectionGenerator
from exocortex.mcp.tools.base import McpTool
from exocortex.processors.base import Processor
from exocortex.synth.perspectives.base import PerspectiveType
from exocortex.wiki.domains.base import DomainCompiler

# ── Concrete stub implementations ─────────────────────────────────────────

class StubPerspective(PerspectiveType):
    name = "stub-perspective"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        return []

    def build_prompt(self, thoughts: list[Any]) -> str:
        return ""

    def parse_response(self, response: str) -> dict[str, Any]:
        return {}


class StubMcpTool(McpTool):
    name = "stub-tool"
    schema = {"type": "object", "properties": {}}

    def handler(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


class StubDomainCompiler(DomainCompiler):
    name = "stub-domain"

    def compile(self, ctx: Any) -> None:
        pass

    def prune_orphans(self, ctx: Any) -> int:
        return 0


class StubProcessor(Processor):
    source_type = "stub-source"

    def process(self, source_id: int) -> dict[str, Any]:
        return {"id": source_id}


class StubSectionGenerator(SectionGenerator):
    name = "stub-section"

    def render(self, ctx: Any) -> str:
        return "# stub"


# ── Registration tests ────────────────────────────────────────────────────

def test_register_perspective():
    r = Registry()
    r.register_perspective(StubPerspective())
    assert "stub-perspective" in r.perspectives


def test_register_mcp_tool():
    r = Registry()
    r.register_mcp_tool(StubMcpTool())
    assert "stub-tool" in r.mcp_tools


def test_register_compile_domain():
    r = Registry()
    r.register_compile_domain(StubDomainCompiler())
    assert "stub-domain" in r.compile_domains


def test_register_capture_processor():
    r = Registry()
    r.register_capture_processor(StubProcessor())
    assert "stub-source" in r.capture_processors


def test_register_live_section():
    r = Registry()
    r.register_live_section(StubSectionGenerator())
    assert "stub-section" in r.live_sections


# ── Entry-point discovery ─────────────────────────────────────────────────

def _make_entry_point(fn):
    ep = MagicMock()
    ep.name = "test-ep"
    ep.load.return_value = fn
    return ep


def test_discover_via_entry_points():
    r = Registry()

    def plugin_setup(registry: Registry) -> None:
        registry.register_perspective(StubPerspective())
        registry.register_mcp_tool(StubMcpTool())

    ep = _make_entry_point(plugin_setup)
    with patch("importlib.metadata.entry_points", return_value=[ep]) as mock_eps:
        count = r._discover_entry_points()

    mock_eps.assert_called_once_with(group=_ENTRY_POINT_GROUP)
    assert count == 1
    assert "stub-perspective" in r.perspectives
    assert "stub-tool" in r.mcp_tools


def test_discover_entry_point_load_error_is_non_fatal():
    r = Registry()
    ep = MagicMock()
    ep.name = "broken-ep"
    ep.load.side_effect = ImportError("missing dep")

    with patch("importlib.metadata.entry_points", return_value=[ep]):
        count = r._discover_entry_points()

    assert count == 0  # error swallowed, no exception raised


def test_discover_returns_total_count():
    r = Registry()

    def setup_a(reg: Registry) -> None:
        reg.register_perspective(StubPerspective())

    ep = _make_entry_point(setup_a)
    with (
        patch("importlib.metadata.entry_points", return_value=[ep]),
        patch.object(r, "_discover_plugins_folder", return_value=0),
    ):
        total = r.discover()

    assert total == 1


# ── Plugins folder discovery ──────────────────────────────────────────────

def test_discover_plugins_folder_skips_missing_dir(tmp_path):
    r = Registry()
    missing = tmp_path / "no-such-dir"

    import exocortex.core.registry as reg_module
    with patch.object(reg_module, "_PLUGINS_DIR", missing):
        count = r._discover_plugins_folder()

    assert count == 0


def test_discover_plugins_folder_loads_setup_fn(tmp_path):
    plugin_dir = tmp_path / "my_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(
        "from exocortex.core.registry import Registry\n"
        "from tests.unit.test_registry import StubPerspective\n\n"
        "def setup(registry: Registry) -> None:\n"
        "    registry.register_perspective(StubPerspective())\n"
    )

    r = Registry()
    import exocortex.core.registry as reg_module
    with patch.object(reg_module, "_PLUGINS_DIR", tmp_path):
        count = r._discover_plugins_folder()

    assert count == 1
    assert "stub-perspective" in r.perspectives


def test_discover_plugins_folder_skips_no_setup(tmp_path):
    plugin_dir = tmp_path / "no_setup_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("# no setup fn\n")

    r = Registry()
    import exocortex.core.registry as reg_module
    with patch.object(reg_module, "_PLUGINS_DIR", tmp_path):
        count = r._discover_plugins_folder()

    assert count == 0


# ── Module-level singleton ────────────────────────────────────────────────

def test_module_singleton_importable():
    from exocortex.core.registry import registry as global_registry
    assert isinstance(global_registry, Registry)
