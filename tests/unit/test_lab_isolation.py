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


def test_egress_probes_report_each_address(monkeypatch):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        monkeypatch.setenv("LAB_EGRESS_PROBES", f"127.0.0.1:{port},no-such-host.invalid:443")
        assert iso.egress() == {f"127.0.0.1:{port}": "open", "no-such-host.invalid:443": "no-name"}
    finally:
        srv.close()


def test_llm_channel_is_optional_and_judged_strictly(monkeypatch):
    monkeypatch.delenv("LAB_LLM_URL", raising=False)
    assert iso.llm_channel() == {} and iso.llm_channel_ok({})
    good = {"health": 200, "models": ["a"], "models_off_list": [], "admin_path": 403, "other_model": 403,
            "absolute_target": 403}
    assert iso.llm_channel_ok(good)
    for key, bad in (("health", 0), ("models_off_list", ["x"]), ("admin_path", 200), ("other_model", 200),
                     ("absolute_target", 200)):
        assert not iso.llm_channel_ok({**good, key: bad}), key


def test_llm_channel_against_a_running_gateway(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from exocortex.lab import llm_gateway as gw

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b'{"data": [{"id": "qwen3.6-35b-a3b"}, {"id": "off-list"}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    models = gw.load_models(Path(__file__).resolve().parents[2] / "lab" / "models.yaml")
    gate = gw.make_server(gw.Gateway(f"http://127.0.0.1:{up.server_port}", set(models)), "127.0.0.1:0")
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("LAB_LLM_URL", f"http://127.0.0.1:{gate.server_port}")
        monkeypatch.setenv("LAB_LLM_MODELS", str(Path(__file__).resolve().parents[2] / "lab" / "models.yaml"))
        state = iso.llm_channel()
        assert state["models"] == ["qwen3.6-35b-a3b"] and iso.llm_channel_ok(state), state
    finally:
        gate.shutdown()
        up.shutdown()


def test_fetch_channel_against_a_running_gateway(monkeypatch):
    import threading

    from exocortex.lab.fetch_gateway import Fetcher, make_server
    from exocortex.source_allowlist import Allowlist

    allow = Allowlist.load(Path(__file__).resolve().parents[2] / "lab" / "sources.yaml")
    server = make_server(Fetcher(allow), "127.0.0.1:0")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("LAB_FETCH_URL", f"http://127.0.0.1:{server.server_address[1]}")
        state = iso.fetch_channel()
        assert iso.fetch_channel_ok(state), state
        assert not iso.fetch_channel_ok({**state, "other_domain": 200})
    finally:
        server.shutdown()
    monkeypatch.delenv("LAB_FETCH_URL")
    assert iso.fetch_channel() == {} and iso.fetch_channel_ok({})
