"""Minimal HTTP service: POST /check {"text": ...} -> {"similar": ..., ...}.

Binds to loopback by default. Request bodies are not logged.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Index

MAX_BODY = 5 * 1024 * 1024


def make_handler(index: Index):
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
                self._send(200, {"ok": True, "paragraphs": len(index.sigs), "semantic": index.vectors is not None})
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
                self._send(200, index.check(text).to_dict())
            except Exception as exc:  # noqa: BLE001 - report type only
                self._send(400, {"error": type(exc).__name__})

    return Handler


def serve(index_dir: Path, host: str = "127.0.0.1", port: int = 8099) -> None:
    index = Index.load(index_dir)
    ThreadingHTTPServer((host, port), make_handler(index)).serve_forever()
