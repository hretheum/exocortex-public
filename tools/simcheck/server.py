"""Minimal HTTP service: POST /check {"text": ...} -> {"similar": ..., ...}.

Binds to loopback by default. Request bodies are not logged.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Index, load_approved

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


class ApprovedHolder:
    """Approved paragraph hashes from a file, reloaded when it changes."""

    def __init__(self, path: Path | None):
        self.path = path
        self._stamp = None
        self.hashes: set[str] = set()

    def get(self) -> set[str]:
        if self.path is None:
            return self.hashes
        try:
            stamp = os.stat(self.path).st_mtime_ns
        except FileNotFoundError:
            stamp = None
        if stamp != self._stamp:
            self.hashes = load_approved(self.path) if stamp else set()
            self._stamp = stamp
        return self.hashes


class StoreHolder:
    """Approvals and exclusions from the quarantine database (tools/publisher/quarantine.py).

    The database is opened read-only and reloaded only when another process
    committed to it. While the file is missing nothing is approved and
    nothing is excluded, which only makes the check stricter.
    """

    def __init__(self, path: Path, corpus_root: str | None = "/corpus"):
        self.path = Path(path)
        self.corpus_root = corpus_root
        self.lock = threading.Lock()
        self._store = None
        self._rev = None
        self._hashes: set[str] = set()
        self._entries: list[str] = []
        self._expiry: str | None = None
        self._masks: dict = {}

    def _open(self):
        if self._store is None and self.path.is_file():
            from tools.publisher.quarantine import Store

            self._store = Store(self.path, read_only=True)
        return self._store

    def _reload(self) -> None:
        with self.lock:
            try:
                store = self._open()
                if store is None:
                    self._hashes, self._entries, self._rev, self._expiry = set(), [], None, None
                    return
                rev = store.revision()
                now = store.now()
                if rev != self._rev or (self._expiry and now >= self._expiry):
                    self._hashes = store.approved_hashes()
                    ex = store.exclusions(active_only=True)
                    self._entries = [e["path"] for e in ex]
                    self._expiry = min((e["expires_at"] for e in ex if e["expires_at"]), default=None)
                    self._rev = rev
                    self._masks = {}
            except Exception:  # noqa: BLE001 - a database problem must not open the check; keep what was loaded
                self._store = None

    def get(self) -> set[str]:
        self._reload()
        return self._hashes

    def mask(self, index: Index):
        self._reload()
        key = (id(index), tuple(self._entries))
        if key not in self._masks:
            self._masks = {key: index.exclusion_mask(self._entries, self.corpus_root)}
        return self._masks[key]


def make_handler(index, approved: "ApprovedHolder | StoreHolder | None" = None):
    """``index`` is an Index or an IndexHolder."""
    get = index.refresh if isinstance(index, IndexHolder) else (lambda: index)
    approved = approved or ApprovedHolder(None)
    exclusions = approved.mask if isinstance(approved, StoreHolder) else (lambda _idx: None)

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
                                 "thresholds": idx.thresholds, "approved_paragraphs": len(approved.get()),
                                 "approvals_from": "store" if isinstance(approved, StoreHolder) else "file",
                                 "excluded_paragraphs": int(exclusions(idx).sum()) if exclusions(idx) is not None else 0,
                                 "sources_known": idx.sources is not None})
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
                body = json.loads(self.rfile.read(length))
                idx = get()
                self._send(200, idx.check(body["text"], approved.get(), exclusions(idx),
                                          exhaustive=body.get("exhaustive") is True).to_dict())
            except Exception as exc:  # noqa: BLE001 - report type only
                self._send(400, {"error": type(exc).__name__})

    return Handler


def serve(index_dir: Path, host: str = "127.0.0.1", port: int = 8099) -> None:
    import signal
    import sys

    # Stop cleanly on SIGTERM (systemctl stop / restart), also as PID 1.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    db = os.environ.get("GATE_QUARANTINE_DB", "").strip()
    if db and db.lower() not in ("none", "unset"):
        approved = StoreHolder(Path(db), os.environ.get("GATE_CORPUS_DIR", "/corpus"))
    else:  # no quarantine database configured: the older text file
        approved_path = os.environ.get("SIMCHECK_APPROVED") or str(Path(index_dir).parent / "approved-paragraphs.txt")
        approved = ApprovedHolder(Path(approved_path))
    handler = make_handler(IndexHolder(index_dir), approved)
    ThreadingHTTPServer((host, port), handler).serve_forever()
