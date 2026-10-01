# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's gateway to the local model server forwards only what it must."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from exocortex.lab import llm_gateway as gw

ROOT = Path(__file__).resolve().parents[2]


class _Upstream(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def _reply(self, status: int, doc: dict, headers: dict | None = None) -> None:
        data = json.dumps(doc).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.seen.append(("GET", self.path))
        if self.path == "/v1/models":
            self._reply(200, {"object": "list", "data": [{"id": "allowed-a"}, {"id": "secret-model"}]})
        elif self.path == "/redirect":
            self._reply(302, {}, {"Location": "http://example.com/"})
        else:
            self._reply(200, {"admin": True})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.seen.append(("POST", self.path, json.loads(body)))
        self._reply(200, {"choices": [{"message": {"content": "{}"}}],
                          "usage": {"prompt_tokens": 7, "completion_tokens": 3}})

    def log_message(self, *args):
        pass


@pytest.fixture()
def servers():
    _Upstream.seen = []
    up = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    gate = gw.make_server(gw.Gateway(f"http://127.0.0.1:{up.server_port}", {"allowed-a", "allowed-b"}),
                          "127.0.0.1:0", max_body=2048)
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    yield gate.server_port
    gate.shutdown()
    up.shutdown()


def _call(port: int, method: str, target: str, body: dict | bytes | None = None) -> tuple[int, dict]:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    c.request(method, target, body=data, headers={"Content-Type": "application/json"} if data else {})
    r = c.getresponse()
    status, raw = r.status, r.read()
    c.close()
    return status, json.loads(raw) if raw else {}


def test_chat_and_embeddings_for_allowed_models_are_forwarded(servers):
    status, doc = _call(servers, "POST", "/v1/chat/completions", {"model": "allowed-a", "messages": []})
    assert status == 200 and doc["usage"]["prompt_tokens"] == 7
    status, _ = _call(servers, "POST", "/v1/embeddings", {"model": "allowed-b", "input": ["x"]})
    assert status == 200
    assert [s[:2] for s in _Upstream.seen] == [("POST", "/v1/chat/completions"), ("POST", "/v1/embeddings")]


def test_model_list_shows_only_allowed_models(servers):
    status, doc = _call(servers, "GET", "/v1/models")
    assert status == 200
    assert [m["id"] for m in doc["data"]] == ["allowed-a"]


def test_other_models_paths_methods_and_targets_are_refused(servers):
    assert _call(servers, "POST", "/v1/chat/completions", {"model": "secret-model", "messages": []})[0] == 403
    assert _call(servers, "POST", "/v1/chat/completions", {"messages": []})[0] == 403
    for target in ("/running", "/upstream/allowed-a/v1/models", "/v1/models/../running", "/logs", "/unload"):
        assert _call(servers, "GET", target)[0] == 403, target
    assert _call(servers, "GET", "http://example.com/v1/models")[0] == 403
    assert _call(servers, "DELETE", "/v1/models")[0] == 403
    assert _call(servers, "PUT", "/v1/chat/completions", {"model": "allowed-a"})[0] == 403
    # nothing of the above reached the upstream
    assert _Upstream.seen == []


def test_streaming_bad_json_and_large_bodies_are_refused(servers):
    assert _call(servers, "POST", "/v1/chat/completions", {"model": "allowed-a", "stream": True})[0] == 400
    assert _call(servers, "POST", "/v1/chat/completions", b"not json")[0] == 400
    assert _call(servers, "POST", "/v1/chat/completions", b"[1, 2]")[0] == 400
    assert _call(servers, "POST", "/v1/chat/completions", {"model": "allowed-a", "pad": "x" * 4096})[0] == 413
    assert _Upstream.seen == []


def test_health_is_answered_locally(servers):
    status, doc = _call(servers, "GET", "/health")
    assert status == 200 and doc["models"] == ["allowed-a", "allowed-b"]
    assert _Upstream.seen == []


def test_redirects_are_not_followed():
    up = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    try:
        g = gw.Gateway(f"http://127.0.0.1:{up.server_port}", {"allowed-a"})
        status, _ = g._forward("GET", "/redirect", None)
        assert status == 302
    finally:
        up.shutdown()


def test_unreachable_upstream_is_a_502():
    g = gw.Gateway("http://127.0.0.1:9", {"allowed-a"}, timeout=2)
    status, _body, fields = g.handle("POST", "/v1/chat/completions", json.dumps({"model": "allowed-a"}).encode())
    assert status == 502 and fields["model"] == "allowed-a"


def test_the_repository_model_list_is_complete():
    models = gw.load_models(ROOT / "lab" / "models.yaml")
    assert "bge-m3" in models and len(models) >= 2
    for m in models.values():
        assert m["basis"].count("http") >= 1, m["id"]


def test_a_model_entry_without_basis_is_rejected(tmp_path):
    f = tmp_path / "models.yaml"
    f.write_text("models:\n  - {id: m, family: f, weights: w, license: l, added_by: a, reason: r}\n")
    with pytest.raises(ValueError, match="basis"):
        gw.load_models(f)


def test_unix_socket_listener_serves_the_same_policy():
    import socket
    import tempfile

    up = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    # macOS limits socket paths to 104 bytes, so not pytest's long tmp_path
    path = Path(tempfile.mkdtemp(prefix="lab-gw-", dir="/tmp")) / "gw.sock"
    gate = gw.make_server(gw.Gateway(f"http://127.0.0.1:{up.server_port}", {"allowed-a"}), f"unix:{path}")
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    try:
        class _Unix(http.client.HTTPConnection):
            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(str(path))

        for target, expected in (("/health", 200), ("/v1/models", 200), ("/running", 403)):
            c = _Unix("gateway", timeout=10)
            c.request("GET", target)
            assert c.getresponse().status == expected, target
            c.close()
    finally:
        gate.shutdown()
        gate.server_close()
        up.shutdown()
        path.unlink(missing_ok=True)
        path.parent.rmdir()
