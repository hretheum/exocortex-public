# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab isolation check must see open ports, extra vault folders and foreign DSNs."""
from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "deploy" / "lab" / "isolation_check.py"
_spec = importlib.util.spec_from_file_location("isolation_check", _PATH)
iso = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iso)


def test_reachable_sees_an_open_port_and_a_closed_one():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert iso.reachable("127.0.0.1", port) == "open"
    finally:
        srv.close()
    assert iso.reachable("127.0.0.1", port, timeout=1) != "open"
    assert iso.reachable("no-such-host.invalid", 5432) == "no-name"


def test_only_the_documents_folder_may_be_visible(tmp_path, monkeypatch):
    (tmp_path / "_source" / "dowody").mkdir(parents=True)
    monkeypatch.setattr(iso, "VAULT", tmp_path)
    assert iso.visible_vault() == []
    (tmp_path / "_source" / "work").mkdir()
    (tmp_path / "wiki").mkdir()
    assert sorted(iso.visible_vault()) == ["_source/work", "wiki"]


def test_foreign_database_url_is_a_leak(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://lab:x@exocortex-lab-db:5432/lab")
    monkeypatch.delenv("SIMCHECK_PG_DSN", raising=False)
    assert iso.env_leaks() == []
    monkeypatch.setenv("SIMCHECK_PG_DSN", "postgresql://u:p@127.0.0.1:5432/exocortex")
    assert iso.env_leaks() == ["SIMCHECK_PG_DSN"]
