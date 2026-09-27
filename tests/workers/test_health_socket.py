# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31-MS-P1.3b — tests for the Unix socket JSON-RPC health probe."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time

import pytest

os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")

from exocortex.workers import health_socket


@pytest.fixture
def patched_registry(monkeypatch):
    from exocortex.core import registry as registry_mod

    class _Stub:
        perspectives = {f"p{i}": object() for i in range(3)}
        mcp_tools = {f"t{i}": object() for i in range(15)}
        compile_domains = {f"d{i}": object() for i in range(6)}
        capture_processors = {f"c{i}": object() for i in range(2)}
        live_sections = {f"l{i}": object() for i in range(4)}
        sinks = {"s0": object()}

    monkeypatch.setattr(registry_mod, "registry", _Stub())


class TestHandleRequestPure:
    """handle_request() is a pure function — exercise it directly."""

    def test_health_method(self):
        resp = health_socket.handle_request(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health"})
        )
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["status"] == "ok"
        assert resp["result"]["pid"] == os.getpid()
        assert resp["result"]["uptime_s"] >= 0

    def test_modules_method(self, patched_registry):
        resp = health_socket.handle_request(
            json.dumps({"jsonrpc": "2.0", "id": "abc", "method": "modules"})
        )
        assert resp["id"] == "abc"
        result = resp["result"]
        assert result["status"] == "ok"
        assert result["registry"]["mcp_tools"] == 15
        assert result["total_modules"] == 31

    def test_unknown_method(self):
        resp = health_socket.handle_request(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "wat"})
        )
        assert "error" in resp
        assert resp["error"]["code"] == health_socket.ERR_METHOD_NOT_FOUND

    def test_parse_error(self):
        resp = health_socket.handle_request("{not json")
        assert resp["error"]["code"] == health_socket.ERR_PARSE
        assert resp["id"] is None

    def test_invalid_request_not_object(self):
        resp = health_socket.handle_request("[1, 2, 3]")
        assert resp["error"]["code"] == health_socket.ERR_INVALID_REQUEST

    def test_invalid_request_missing_method(self):
        resp = health_socket.handle_request(json.dumps({"jsonrpc": "2.0", "id": 9}))
        assert resp["error"]["code"] == health_socket.ERR_INVALID_REQUEST
        assert resp["id"] == 9


class TestSocketRoundtrip:
    """End-to-end: spin up serve_forever() in a thread, talk to it via socket."""

    def _start_server(self, path: str) -> threading.Thread:
        t = threading.Thread(
            target=health_socket.serve_forever,
            args=(path,),
            daemon=True,
        )
        t.start()
        # Wait until a real Unix socket is bound (not a leftover regular file)
        import stat
        for _ in range(100):
            try:
                st = os.stat(path)
                if stat.S_ISSOCK(st.st_mode):
                    return t
            except FileNotFoundError:
                pass
            time.sleep(0.02)
        raise RuntimeError(f"server didn't bind {path} in time")

    def _send(self, path: str, payload: dict) -> dict:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(path)
        try:
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0].decode("utf-8")
            return json.loads(line)
        finally:
            s.close()

    def test_roundtrip_health(self, patched_registry):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.sock")
            self._start_server(path)
            try:
                resp = self._send(path, {"jsonrpc": "2.0", "id": 1, "method": "health"})
                assert resp["result"]["status"] == "ok"
                assert resp["result"]["pid"] == os.getpid()

                resp2 = self._send(path, {"jsonrpc": "2.0", "id": 2, "method": "modules"})
                assert resp2["result"]["total_modules"] == 31

                resp3 = self._send(path, {"jsonrpc": "2.0", "id": 3, "method": "ghost"})
                assert resp3["error"]["code"] == health_socket.ERR_METHOD_NOT_FOUND
            finally:
                # SIGINT-style shutdown: close + unlink (mirrors cleanup path)
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    def test_socket_file_cleaned_on_rebind(self):
        """A stale socket file from a previous run shouldn't block bind."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.sock")
            # Plant a stale file
            with open(path, "w") as f:
                f.write("stale")
            assert os.path.exists(path)
            self._start_server(path)
            try:
                resp = self._send(path, {"jsonrpc": "2.0", "id": 1, "method": "health"})
                assert resp["result"]["status"] == "ok"
            finally:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
