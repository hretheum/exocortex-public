"""Minimal HTTP service: POST /check {"text": ...} -> {"similar": ..., ...}.

Binds to loopback by default. Request bodies are not logged.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Index

MAX_BODY = 5 * 1024 * 1024


class IndexHolder:
    """Keeps the loaded index and reloads it when the directory behind the
    path changes (the index job swaps a symlink) or its meta.json is rewritten
    (calibration). The check is one stat per request."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._stamp = None
        self.index = None
        self.refresh()

    def _current_stamp(self):
        real = os.path.realpath(self.path)
        try:
            return real, os.stat(os.path.join(real, "meta.json")).st_mtime_ns
        except FileNotFoundError:
            return real, None

    def refresh(self) -> Index:
        stamp = self._current_stamp()
        if stamp != self._stamp or self.index is None:
            with self.lock:
                if stamp != self._stamp or self.index is None:
                    self.index = Index.load(Path(stamp[0]))
                    self._stamp = stamp
        return self.index


def make_handler(index):
    """``index`` is an Index or an IndexHolder."""
    get = index.refresh if isinstance(index, IndexHolder) else (lambda: index)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # never log request content
            return

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                idx = get()
                self._send(200, {"ok": True, "paragraphs": len(idx.sigs), "semantic": idx.vectors is not None,
                                 "thresholds": idx.thresholds})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/check":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                self._send(413, {"error": "too large"})
                return
            try:
                text = json.loads(self.rfile.read(length))["text"]
                self._send(200, get().check(text).to_dict())
            except Exception as exc:  # noqa: BLE001 - report type only
                self._send(400, {"error": type(exc).__name__})

    return Handler


def serve(index_dir: Path, host: str = "127.0.0.1", port: int = 8099) -> None:
    import signal
    import sys

    # Stop cleanly on SIGTERM (systemctl stop / restart), also as PID 1.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    ThreadingHTTPServer((host, port), make_handler(IndexHolder(index_dir))).serve_forever()
