# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Tests for the wiki domain registry (F31.7.5).

All domain compiler modules, _LegacyDomainCompiler contract,
setup_builtins, RunContext, and ACME/GLOBEX removal.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from dataclasses import fields
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TENANT_ID", "test-tenant")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry():
    from exocortex.core.registry import Registry
    return Registry()


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

class TestRunContext:
    def test_fields(self):
        from exocortex.wiki.runner import RunContext
        ctx = RunContext(tenant_id="t1")
        assert ctx.tenant_id == "t1"
        assert ctx.since is None

    def test_with_since(self):
        from exocortex.wiki.runner import RunContext
        dt = datetime(2024, 1, 1)  # noqa: DTZ001 — naive on purpose: matches the naive API under test
        ctx = RunContext(tenant_id="t1", since=dt)
        assert ctx.since == dt

    def test_is_dataclass(self):
        from exocortex.wiki.runner import RunContext
        field_names = {f.name for f in fields(RunContext)}
        assert field_names == {"tenant_id", "since"}

    def test_immutable_defaults(self):
        from exocortex.wiki.runner import RunContext
        ctx1 = RunContext(tenant_id="a")
        ctx2 = RunContext(tenant_id="b")
        assert ctx1.tenant_id != ctx2.tenant_id

    def test_frozen(self):
        from exocortex.wiki.runner import RunContext
        ctx = RunContext(tenant_id="t1")
        with pytest.raises((AttributeError, TypeError)):
            ctx.tenant_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _LegacyDomainCompiler contract
# ---------------------------------------------------------------------------

class TestLegacyDomainCompiler:
    def _make_stub_compiler(self, fn_name: str, name: str):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler

        class _Stub(_LegacyDomainCompiler):
            _legacy_fn_name = fn_name

            @property
            def name(self) -> str:
                return name

        return _Stub()

    def test_name_property(self):
        c = self._make_stub_compiler("compile_test", "test")
        assert c.name == "test"

    def test_prune_orphans_returns_zero(self):
        from exocortex.wiki.runner import RunContext
        c = self._make_stub_compiler("compile_test", "test")
        ctx = RunContext(tenant_id="t")
        assert c.prune_orphans(ctx) == 0

    def test_empty_fn_name_raises(self):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler

        class _Bad(_LegacyDomainCompiler):
            _legacy_fn_name = ""

            @property
            def name(self):
                return "bad"

        with pytest.raises(AttributeError, match="_legacy_fn_name is empty"):
            _Bad()._get_fn()

    def test_missing_fn_in_module_raises(self):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler

        class _Missing(_LegacyDomainCompiler):
            _legacy_fn_name = "no_such_function_xyz"

            @property
            def name(self):
                return "missing"

        stub_mod = types.ModuleType("exocortex.wiki_compiler")
        with (
            patch.dict(sys.modules, {"exocortex.wiki_compiler": stub_mod}),
            pytest.raises(AttributeError, match="no_such_function_xyz"),
        ):
            _Missing()._get_fn()

    def test_fn_cache_populated_on_first_call(self):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler

        class _Cached(_LegacyDomainCompiler):
            _legacy_fn_name = "compile_cached"

            @property
            def name(self):
                return "cached"

        stub_fn = MagicMock()
        stub_mod = types.ModuleType("exocortex.wiki_compiler")
        stub_mod.compile_cached = stub_fn  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"exocortex.wiki_compiler": stub_mod}):
            c = _Cached()
            assert c._fn_cache is None
            fn1 = c._get_fn()
            assert fn1 is stub_fn
            assert c._fn_cache is stub_fn
            fn2 = c._get_fn()
            assert fn2 is stub_fn

    def test_compile_calls_legacy_fn_with_tenant_and_since(self):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler
        from exocortex.wiki.runner import RunContext

        class _Testable(_LegacyDomainCompiler):
            _legacy_fn_name = "compile_testable"

            @property
            def name(self):
                return "testable"

        stub_fn = MagicMock()
        stub_mod = types.ModuleType("exocortex.wiki_compiler")
        stub_mod.compile_testable = stub_fn  # type: ignore[attr-defined]
        dt = datetime(2024, 6, 1)  # noqa: DTZ001 — naive on purpose: matches the naive API under test
        with patch.dict(sys.modules, {"exocortex.wiki_compiler": stub_mod}):
            _Testable().compile(RunContext(tenant_id="ten1", since=dt))
        stub_fn.assert_called_once_with("ten1", dt)


# ---------------------------------------------------------------------------
# Domain module setup() functions
# ---------------------------------------------------------------------------

DOMAIN_MODULE_CASES = [
    ("exocortex.wiki.domains.frp", "frp"),
    ("exocortex.wiki.domains.home", "home"),
    ("exocortex.wiki.domains.news", "news"),
    ("exocortex.wiki.domains.work", "work"),
    ("exocortex.wiki.domains.cross_domain", "cross"),
    ("exocortex.wiki.domains.live_sections", "live"),
]


@pytest.mark.parametrize("module_path,expected_name", DOMAIN_MODULE_CASES)
def test_domain_module_setup_registers(module_path, expected_name):
    registry = _make_registry()
    mod = importlib.import_module(module_path)
    mod.setup(registry)
    assert expected_name in registry.compile_domains


CLIPPINGS_CASES = [
    ("3d", "compile_3d_module"),
    ("tc", "compile_tc_module"),
    ("cook", "compile_cook_module"),
    ("priv", "compile_priv_module"),
    ("sb", "compile_sb_module"),
    ("papers", "compile_papers_module"),
]


@pytest.mark.parametrize("domain_name,fn_name", CLIPPINGS_CASES)
def test_clippings_setup_registers(domain_name, fn_name):
    from exocortex.wiki.domains import clippings
    registry = _make_registry()
    clippings.setup(registry)
    assert domain_name in registry.compile_domains
    compiler = registry.compile_domains[domain_name]
    assert compiler._legacy_fn_name == fn_name


def test_clippings_setup_registers_all_six():
    from exocortex.wiki.domains import clippings
    registry = _make_registry()
    clippings.setup(registry)
    assert len(registry.compile_domains) == 6


# ---------------------------------------------------------------------------
# setup_builtins
# ---------------------------------------------------------------------------

BUILTIN_DOMAINS = {"work", "frp", "news", "home", "cross", "live",
                   "3d", "tc", "cook", "priv", "sb", "papers"}


class TestSetupBuiltins:
    def test_all_builtins_registered(self):
        from exocortex.wiki.runner import setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        assert set(registry.compile_domains.keys()) == BUILTIN_DOMAINS

    def test_idempotent(self):
        from exocortex.wiki.runner import setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        count_first = len(registry.compile_domains)
        # Re-calling setup_builtins should NOT double-register
        # (Registry.register_compile_domain should overwrite or skip)
        setup_builtins(registry)
        assert len(registry.compile_domains) == count_first

    def test_each_compiler_has_name(self):
        from exocortex.wiki.runner import setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        for name, compiler in registry.compile_domains.items():
            assert compiler.name == name

    def test_each_compiler_has_legacy_fn_name(self):
        from exocortex.wiki.domains.base import _LegacyDomainCompiler
        from exocortex.wiki.runner import setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        for name, compiler in registry.compile_domains.items():
            assert isinstance(compiler, _LegacyDomainCompiler)
            assert compiler._legacy_fn_name, f"{name}: _legacy_fn_name is empty"

    def test_count(self):
        from exocortex.wiki.runner import setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        assert len(registry.compile_domains) == 12

    def test_all_builtins_prune_orphans_return_int(self):
        from exocortex.wiki.runner import RunContext, setup_builtins
        registry = _make_registry()
        setup_builtins(registry)
        ctx = RunContext(tenant_id="t")
        for name, compiler in registry.compile_domains.items():
            result = compiler.prune_orphans(ctx)
            assert isinstance(result, int), f"{name}.prune_orphans() returned {type(result)}"


# ---------------------------------------------------------------------------
# wiki __init__ public facade
# ---------------------------------------------------------------------------

def test_wiki_init_exports():
    import exocortex.wiki as wk
    assert hasattr(wk, "RunContext")
    assert hasattr(wk, "compile_all")
    assert hasattr(wk, "setup_builtins")
    assert hasattr(wk, "DomainCompiler")


# ---------------------------------------------------------------------------
# ACME/GLOBEX removal from wiki_compiler.py
# ---------------------------------------------------------------------------

def _read_wiki_compiler_source() -> str:
    import pathlib
    p = pathlib.Path(__file__).parent.parent.parent / "exocortex" / "wiki_compiler.py"
    return p.read_text(encoding="utf-8")


def test_no_compile_acme_module_in_wiki_compiler():
    src = _read_wiki_compiler_source()
    assert "compile_acme_module" not in src, \
        "compile_acme_module still present in wiki_compiler.py after F31.7.5 cleanup"


def test_no_compile_acme_dashboard_in_wiki_compiler():
    src = _read_wiki_compiler_source()
    assert "compile_acme_dashboard" not in src


def test_no_acme_constants_in_wiki_compiler():
    src = _read_wiki_compiler_source()
    for sym in ("_ACME_PILLARS", "_ACME_CONCEPT_RULES", "_ACME_VIEW_DIRS",
                "_ACME_SEVERITY_GLYPH", "_ACME_TOPICS_YAML_CACHE",
                "_ACME_DEFAULT_STATUS_GROUPS"):
        assert sym not in src, f"ACME constant {sym} still present in wiki_compiler.py"


def test_no_project_acme_cli_arg():
    src = _read_wiki_compiler_source()
    assert "--project" not in src, \
        "--project CLI argument still present in wiki_compiler.py"


def test_acme_call_removed_from_compile_work_module():
    src = _read_wiki_compiler_source()
    assert "_safe(compile_acme_module" not in src


# ---------------------------------------------------------------------------
# DomainCompiler ABC
# ---------------------------------------------------------------------------

def test_domain_compiler_abc_requires_name():
    from exocortex.wiki.domains.base import DomainCompiler

    class _NoName(DomainCompiler):
        def compile(self, ctx):
            pass
        def prune_orphans(self, ctx):
            return 0

    with pytest.raises(TypeError):
        _NoName()  # type: ignore[abstract]


def test_domain_compiler_abc_requires_compile():
    from exocortex.wiki.domains.base import DomainCompiler

    class _NoCompile(DomainCompiler):
        @property
        def name(self):
            return "x"
        def prune_orphans(self, ctx):
            return 0

    with pytest.raises(TypeError):
        _NoCompile()  # type: ignore[abstract]
