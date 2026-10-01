# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31-MS-P1.3b — Unix domain socket health probe.

Serves newline-delimited JSON-RPC 2.0 on a Unix domain socket
(default: ``/tmp/exocortex-health.sock``, override via
``EXOCORTEX_HEALTH_SOCKET``). Methods:

* ``health``  → ``{"status": "ok", "pid": <pid>, "uptime_s": <float>}``
* ``modules`` → registry counts (same shape as ``GET /health/modules``)

Pure stdlib, no LLM imports. One connection at a time is fine — this is
a diagnostic probe, not a production server. Run as a module::

    python -m exocortex.workers.health_socket
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import time
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = "/tmp/exocortex-health.sock"
JSONRPC_VERSION = "2.0"
ERR_METHOD_NOT_FOUND = -32601
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_INTERNAL = -32603

_started_at = time.monotonic()


def _registry_counts() -> dict[str, Any]:
    from exocortex.core.registry import registry as _reg

    counts = {
        "perspectives": len(_reg.perspectives),
        "mcp_tools": len(_reg.mcp_tools),
        "compile_domains": len(_reg.compile_domains),
        "capture_processors": len(_reg.capture_processors),
        "live_sections": len(_reg.live_sections),
        "sinks": len(_reg.sinks),
    }
    return {
        "status": "ok",
        "registry": counts,
        "total_modules": sum(counts.values()),
    }


def _handle_method(method: str, params: Any) -> dict[str, Any]:
    if method == "health":
        return {
            "status": "ok",
            "pid": os.getpid(),
            "uptime_s": round(time.monotonic() - _started_at, 3),
        }
    if method == "modules":
        return _registry_counts()
    raise LookupError(method)


def _make_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _make_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}


def handle_request(line: str) -> dict[str, Any]:
    """Parse a single JSON-RPC line and return the response dict.

    Exposed for unit tests — pure function, no socket I/O.
    """
    try:
        req = json.loads(line)
    except json.JSONDecodeError as exc:
        return _make_error(None, ERR_PARSE, f"Parse error: {exc}")

    if not isinstance(req, dict):
        return _make_error(None, ERR_INVALID_REQUEST, "Request must be a JSON object")

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params")

    if not isinstance(method, str):
        return _make_error(req_id, ERR_INVALID_REQUEST, "Missing or non-string 'method'")

    try:
        result = _handle_method(method, params)
    except LookupError:
        return _make_error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
    except Exception as exc:  # pragma: no cover — defensive  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return _make_error(req_id, ERR_INTERNAL, f"{type(exc).__name__}: {exc}")

    return _make_result(req_id, result)


def _cleanup_socket(path: str) -> None:
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError as exc:
        log.warning("failed to unlink socket %s: %s", path, exc)


def serve_forever(socket_path: str = DEFAULT_SOCKET_PATH) -> None:
    """Bind to *socket_path* and accept connections until SIGTERM/SIGINT.

    One connection handled at a time. Each connection may send multiple
    newline-delimited JSON-RPC requests; responses are also newline-delimited.
    """
    _cleanup_socket(socket_path)

    parent = os.path.dirname(socket_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(socket_path)
    try:
        os.chmod(socket_path, 0o600)
    except OSError as exc:
        log.warning("chmod 0600 on %s failed: %s", socket_path, exc)
    srv.listen(8)
    log.info("health_socket listening on %s (pid=%d)", socket_path, os.getpid())

    shutting_down = {"flag": False}

    def _on_signal(signum: int, _frame: Any) -> None:
        log.info("health_socket received signal %d, shutting down", signum)
        shutting_down["flag"] = True
        try:
            srv.close()
        except OSError:
            pass

    # Signal handlers only work when serve_forever() runs in the main thread.
    # In tests we run it from a worker thread — that's fine, shutdown happens
    # via socket close from the test cleanup path.
    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except ValueError:
        log.debug("signal handlers not installed (not main thread)")

    try:
        while not shutting_down["flag"]:
            try:
                conn, _addr = srv.accept()
            except OSError:
                if shutting_down["flag"]:
                    break
                raise
            with conn:
                _serve_connection(conn)
    finally:
        _cleanup_socket(socket_path)
        log.info("health_socket stopped, socket %s removed", socket_path)


def _serve_connection(conn: socket.socket) -> None:
    buf = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line_bytes, buf = buf.split(b"\n", 1)
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            response = handle_request(line)
            payload = (json.dumps(response) + "\n").encode("utf-8")
            try:
                conn.sendall(payload)
            except OSError:
                return


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("EXOCORTEX_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    path = os.environ.get("EXOCORTEX_HEALTH_SOCKET", DEFAULT_SOCKET_PATH)
    serve_forever(path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
