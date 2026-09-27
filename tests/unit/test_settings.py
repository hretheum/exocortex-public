# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.8.1 — Pydantic Settings + integrations.yaml loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from exocortex.settings import Settings, get_settings, reset_settings


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch, tmp_path):
    """Each test starts with a fresh cache + an isolated CWD so the package
    ``.env`` (if any) is not picked up."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXOCORTEX_VAULT_PATH", raising=False)
    monkeypatch.delenv("EXOCORTEX_VAULT_NAME", raising=False)
    monkeypatch.delenv("EXOCORTEX_TENANT_ID", raising=False)
    reset_settings()
    yield
    reset_settings()


def test_settings_requires_vault_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXOCORTEX_VAULT_PATH", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_reads_vault_path_from_env(monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/some/vault")
    s = Settings()
    assert s.vault_path == Path("/tmp/some/vault")


def test_settings_tenant_id_defaults_to_default(monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/vault")
    s = Settings()
    assert s.tenant_id == "default"


def test_settings_vault_name_optional(monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/vault")
    s = Settings()
    assert s.vault_name is None

    monkeypatch.setenv("EXOCORTEX_VAULT_NAME", "my-vault")
    reset_settings()
    s2 = Settings()
    assert s2.vault_name == "my-vault"


def test_get_settings_caches(monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/cached/vault")
    a = get_settings()
    b = get_settings()
    assert a is b


def test_reset_settings(monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/vault-a")
    a = get_settings()
    reset_settings()
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/vault-b")
    b = get_settings()
    assert a is not b
    assert b.vault_path == Path("/tmp/vault-b")


def test_get_internal_domain_fallback_to_example(monkeypatch):
    """When no user override exists, the loader returns the example value."""
    import sys
    import types

    # Provide a real yaml.safe_load implementation for the loader to use,
    # bypassing the auto-stubbed module in the unit-test sandbox.
    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda text: {  # type: ignore[attr-defined]
        "internal_domain": "example.com"
    }
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)

    from exocortex import integrations
    monkeypatch.setattr(integrations, "_CONFIG_PATH", Path("/does/not/exist"))

    assert integrations.get_internal_domain() == "example.com"


def test_get_internal_domain_returns_none_when_no_files(monkeypatch, tmp_path):
    import sys
    import types

    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda text: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)

    from exocortex import integrations
    monkeypatch.setattr(integrations, "_CONFIG_PATH", tmp_path / "absent.yaml")
    monkeypatch.setattr(integrations, "_EXAMPLE_PATH", tmp_path / "missing.example.yaml")

    assert integrations.get_internal_domain() is None


def test_get_internal_domain_warns_once_when_no_files(monkeypatch, tmp_path, caplog):
    """When neither file exists, the loader emits a single warning."""
    import sys
    import types
    import logging

    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda text: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)

    from exocortex import integrations
    monkeypatch.setattr(integrations, "_CONFIG_PATH", tmp_path / "absent.yaml")
    monkeypatch.setattr(integrations, "_EXAMPLE_PATH", tmp_path / "missing.example.yaml")
    monkeypatch.setattr(integrations, "_warned_missing", False)

    with caplog.at_level(logging.WARNING, logger="exocortex.integrations"):
        integrations.get_internal_domain()
        integrations.get_internal_domain()

    warnings = [r for r in caplog.records if "No integrations config" in r.message]
    assert len(warnings) == 1


def test_module_getattr_raises_attribute_error_without_env(monkeypatch):
    """C2 fix: __getattr__ must surface AttributeError, not ValidationError,
    so `hasattr()` callers behave correctly when EXOCORTEX_VAULT_PATH is unset.
    """
    monkeypatch.delenv("EXOCORTEX_VAULT_PATH", raising=False)
    # journal_publisher reads TENANT_ID at import time but does NOT need
    # EXOCORTEX_VAULT_PATH thanks to F31.8.1 + C1 lazy resolution.
    monkeypatch.setenv("TENANT_ID", "test")
    reset_settings()

    from exocortex import classifier, backlog_adapter, vault_watcher

    cases = [
        (classifier, "VAULT_MEETINGS_DIR"),
        (backlog_adapter, "VAULT_PATH"),
        (backlog_adapter, "BACKLOG_DIR"),
        (backlog_adapter, "VIEWS"),
        (vault_watcher, "VAULT_PATH"),
    ]

    # journal_publisher pulls in exocortex.db at import time, which requires
    # psycopg_pool. Try to import it; skip those cases if the dep is absent in
    # the test sandbox (unit tests stub it normally — but this test uses real
    # modules to exercise __getattr__).
    try:
        from exocortex import journal_publisher
        cases.extend([
            (journal_publisher, "VAULT_PATH"),
            (journal_publisher, "JOURNAL_DIR"),
        ])
    except ModuleNotFoundError:
        pass

    for mod, attr in cases:
        # hasattr() should return False (would raise if ValidationError leaked)
        assert not hasattr(mod, attr), (
            f"{mod.__name__}.{attr} should not be available without env"
        )
        # Direct access should raise AttributeError (not ValidationError)
        with pytest.raises(AttributeError):
            getattr(mod, attr)


def test_get_settings_thread_safe(monkeypatch):
    """W1 fix: concurrent get_settings() calls return the same cached instance."""
    import threading

    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp/thread-vault")
    reset_settings()

    results: list = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(get_settings())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    first = results[0]
    assert all(r is first for r in results)
