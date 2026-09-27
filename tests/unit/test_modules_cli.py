# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for ``exocortex modules`` CLI (F31-MS-P1.1+P1.2)."""

from __future__ import annotations

import os

os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")
os.environ.setdefault("DATABASE_URL", "postgresql://test@localhost/test")

from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

from exocortex import cli  # noqa: E402
from exocortex.core.registry import Registry  # noqa: E402
from exocortex.live_sections.base import SectionGenerator  # noqa: E402
from exocortex.mcp.tools.base import McpTool  # noqa: E402
from exocortex.processors.base import Processor  # noqa: E402
from exocortex.synth.perspectives.base import PerspectiveType  # noqa: E402
from exocortex.wiki.domains.base import DomainCompiler  # noqa: E402


# --- stubs ------------------------------------------------------------------

class _StubPerspective(PerspectiveType):
    name = "stub-perspective"

    def select_thoughts(self, ctx: Any) -> list[Any]: return []
    def build_prompt(self, thoughts: list[Any]) -> str: return ""
    def parse_response(self, response: str) -> dict[str, Any]: return {}


class _StubMcpTool(McpTool):
    name = "stub-tool"
    schema = {"type": "object", "properties": {}}
    def handler(self, args: dict[str, Any]) -> dict[str, Any]: return {}


class _StubDomain(DomainCompiler):
    name = "stub-domain"
    def compile(self, ctx: Any) -> None: pass
    def prune_orphans(self, ctx: Any) -> int: return 0


class _StubProcessor(Processor):
    source_type = "stub-source"
    def process(self, source_id: int) -> dict[str, Any]: return {}


class _StubSection(SectionGenerator):
    name = "stub-section"
    def render(self, ctx: Any) -> str: return ""


def _stub_registry() -> Registry:
    r = Registry()
    r.register_perspective(_StubPerspective())
    r.register_mcp_tool(_StubMcpTool())
    r.register_compile_domain(_StubDomain())
    r.register_capture_processor(_StubProcessor())
    r.register_live_section(_StubSection())
    return r


@pytest.fixture
def stub_registry(monkeypatch):
    """Replace the discovery helper so each test sees a clean stub registry."""
    r = _stub_registry()
    monkeypatch.setattr(cli, "_discovered_registry", lambda: r)
    return r


# --- list -------------------------------------------------------------------

def test_modules_list_shows_all_extension_points(stub_registry, capsys):
    rc = cli.main(["modules", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "TYPE" in out and "NAME" in out and "SOURCE" in out
    assert "stub-perspective" in out
    assert "stub-tool" in out
    assert "stub-domain" in out
    assert "stub-source" in out
    assert "stub-section" in out
    # The SOURCE column should carry the class path of the stub.
    assert "_StubPerspective" in out


def test_modules_list_empty_registry(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_discovered_registry", lambda: Registry())
    rc = cli.main(["modules", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no modules registered" in out


# --- status -----------------------------------------------------------------

def test_modules_status_prints_counts(stub_registry, capsys):
    rc = cli.main(["modules", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "registry loaded OK" in out
    assert "perspectives" in out
    assert "mcp_tools" in out


# --- disable ----------------------------------------------------------------

def test_modules_disable_missing_config_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_config_yaml_path",
                        lambda: tmp_path / "config" / "exocortex.yaml")
    rc = cli.main(["modules", "disable", "foo"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "config file not found" in out


def test_modules_disable_appends_to_yaml(tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    cfg = tmp_path / "config" / "exocortex.yaml"
    cfg.write_text("tenant_id: default\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_config_yaml_path", lambda: cfg)

    rc = cli.main(["modules", "disable", "news_cluster"])
    out = capsys.readouterr().out
    text = cfg.read_text(encoding="utf-8")
    assert rc == 0
    assert "disabled: news_cluster" in out
    assert "disabled_modules:" in text
    assert "- news_cluster" in text


def test_modules_disable_idempotent(tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    cfg = tmp_path / "config" / "exocortex.yaml"
    cfg.write_text(
        "tenant_id: default\ndisabled_modules:\n  - news_cluster\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_config_yaml_path", lambda: cfg)

    rc = cli.main(["modules", "disable", "news_cluster"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already disabled" in out
    # File should not have grown a duplicate entry.
    assert cfg.read_text(encoding="utf-8").count("- news_cluster") == 1


# --- render-systemd ---------------------------------------------------------

def test_render_systemd_generic_template(stub_registry, capsys):
    rc = cli.main(["modules", "render-systemd"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[Unit]" in out
    assert "[Service]" in out
    assert "ProtectHome=read-only" in out
    assert "User=exocortex" in out
    assert "NoNewPrivileges=yes" in out


def test_render_systemd_named_module(stub_registry, capsys):
    rc = cli.main(["modules", "render-systemd", "stub-perspective"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "stub-perspective" in out
    assert "perspectives" in out
    assert "ProtectHome=read-only" in out
    assert "User=exocortex" in out
    assert "NoNewPrivileges=yes" in out


def test_render_systemd_unknown_module_emits_todo(stub_registry, capsys):
    rc = cli.main(["modules", "render-systemd", "definitely-not-registered"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "TODO" in out
    assert "ProtectHome=read-only" in out


# --- render-compose ---------------------------------------------------------

def test_render_compose_includes_required_env(stub_registry, capsys):
    rc = cli.main(["modules", "render-compose"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "services:" in out
    assert "ghcr.io/hretheum/exocortex:latest" in out
    assert "EXOCORTEX_VAULT_PATH" in out
    assert "DATABASE_URL" in out
    assert "TENANT_ID" in out


def test_render_compose_empty_registry(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_discovered_registry", lambda: Registry())
    rc = cli.main(["modules", "render-compose"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "services:" in out
    assert "exocortex:" in out
    assert "EXOCORTEX_VAULT_PATH" in out
