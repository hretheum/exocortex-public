# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31-MS-P1.3a — tests for /health/modules endpoint."""

from __future__ import annotations

import os

os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from exocortex.capture_api import app

    return TestClient(app)


@pytest.fixture
def patched_registry(monkeypatch):
    """Replace the module-level registry with a stub holding known counts."""
    from exocortex.core import registry as registry_mod

    class _Stub:
        perspectives = {f"p{i}": object() for i in range(3)}
        mcp_tools = {f"t{i}": object() for i in range(15)}
        compile_domains = {f"d{i}": object() for i in range(6)}
        capture_processors = {f"c{i}": object() for i in range(2)}
        live_sections = {f"l{i}": object() for i in range(4)}
        sinks = {"s0": object()}

    stub = _Stub()
    monkeypatch.setattr(registry_mod, "registry", stub)
    return stub


def test_health_modules_ok_no_auth(client, patched_registry):
    """Endpoint requires no auth and reports counts from the registry."""
    resp = client.get("/health/modules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["registry"] == {
        "perspectives": 3,
        "mcp_tools": 15,
        "compile_domains": 6,
        "capture_processors": 2,
        "live_sections": 4,
        "sinks": 1,
    }
    assert body["total_modules"] == 31


def test_health_modules_degraded_on_registry_failure(client, monkeypatch):
    """If the registry attribute access blows up, return 503 + degraded."""
    from exocortex.core import registry as registry_mod

    class _Broken:
        @property
        def perspectives(self):
            raise RuntimeError("registry exploded")

    monkeypatch.setattr(registry_mod, "registry", _Broken())
    resp = client.get("/health/modules")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert "registry exploded" in body["error"]


def test_health_modules_empty_registry(client, monkeypatch):
    """Empty registry should still return ok with total_modules=0."""
    from exocortex.core import registry as registry_mod

    class _Empty:
        perspectives: dict = {}
        mcp_tools: dict = {}
        compile_domains: dict = {}
        capture_processors: dict = {}
        live_sections: dict = {}
        sinks: dict = {}

    monkeypatch.setattr(registry_mod, "registry", _Empty())
    resp = client.get("/health/modules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["total_modules"] == 0
