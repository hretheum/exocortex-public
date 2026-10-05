# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's one path for downloads from public sources (roadmap task F5.2).

Like the model gateway, this service does not join the internal lab
network: it runs in its own network namespace with outbound internet access
only, and serves lab processes over a Unix socket in a volume they mount.
It answers exactly one kind of request:

    GET /fetch?url=<https URL>     the body of that URL, if the URL is allowed
    GET /health                    answered by the gateway itself

A URL is allowed when it is https, has no user name, password or unusual
port, and matches an entry of the lab's source allowlist (lab/sources.yaml,
the same file the Capture API enforces). Redirects are followed only to
allowed URLs, at most three times. Requests to one host keep the interval
the source's terms ask for (``min_interval_s``, default 1 second), and
responses larger than LAB_FETCH_MAX_BYTES are cut off with an error. Every
request is logged as one JSON line with host, status, size and time; never
the content.

    LAB_FETCH_LISTEN=unix:/run/lab-fetch/fetch.sock python -m exocortex.lab.fetch_gateway
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from exocortex.source_allowlist import Allowlist

USER_AGENT = "exocortex-lab/0.1 (research; +https://github.com/hretheum/exocortex-public)"
MAX_REDIRECTS = 3


def _error(message: str) -> bytes:
    return json.dumps({"error": message}).encode()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # redirects are checked and followed by the gateway itself


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


class Fetcher:
    """Policy and downloading, without the HTTP server around it."""

    def __init__(self, allowlist: Allowlist, max_bytes: int = 20 * 1024 * 1024, timeout: float = 60.0,
                 opener: urllib.request.OpenerDirector | None = None, clock=time.monotonic, sleep=time.sleep):
        self.allowlist = allowlist
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.opener = opener or _opener()
        self.clock, self.sleep = clock, sleep
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def refusal(self, url: str) -> str | None:
        """Why ``url`` may not be fetched, or None if it may."""
        try:
            u = urllib.parse.urlsplit(url)
            port = u.port
        except ValueError:
            return "malformed url"
        if u.scheme != "https":
            return "only https"
        if u.username or u.password or (port not in (None, 443)):
            return "no credentials or ports"
        ok, reason = self.allowlist.check_url(url)
        return None if ok else reason

    def _interval(self, host: str) -> float:
        best = 1.0
        for s in self.allowlist.sources:
            interval = getattr(s, "min_interval_s", None)
            if s.matches_uri(f"https://{host}/") and interval:
                best = max(best, float(interval))
        return best

    def _wait(self, host: str) -> None:
        with self._lock:
            now = self.clock()
            ready = self._last.get(host, float("-inf")) + self._interval(host)
            if now < ready:
                self.sleep(ready - now)
            self._last[host] = self.clock()

    def fetch(self, url: str) -> tuple[int, bytes, str, dict]:
        """(status, body, content type, log fields)."""
        for _ in range(MAX_REDIRECTS + 1):
            why = self.refusal(url)
            host = urllib.parse.urlsplit(url).hostname or ""
            fields = {"host": host}
            if why:
                return 403, _error(why), "application/json", fields
            self._wait(host)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        return 502, _error("response too large"), "application/json", fields
                    return resp.status, body, resp.headers.get("Content-Type", "application/octet-stream"), fields
            except urllib.error.HTTPError as exc:
                location = exc.headers.get("Location") if exc.code in (301, 302, 303, 307, 308) else None
                if location:
                    url = urllib.parse.urljoin(url, location)
                    continue
                return exc.code, exc.read()[:4096], "text/plain", fields
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                return 502, _error(f"source unavailable ({type(exc).__name__})"), "application/json", fields
        return 502, _error("too many redirects"), "application/json", {}

    def handle(self, method: str, target: str) -> tuple[int, bytes, str, dict]:
        parts = urllib.parse.urlsplit(target)
        if method == "GET" and parts.path == "/health":
            return 200, json.dumps({"status": "ok", "sources": len(self.allowlist.sources)}).encode(), \
                "application/json", {}
        if method != "GET" or parts.path != "/fetch" or parts.scheme or parts.netloc:
            return 403, _error("not allowed"), "application/json", {}
        url = urllib.parse.parse_qs(parts.query).get("url", [""])[0]
        if not url:
            return 400, _error("url is missing"), "application/json", {}
        return self.fetch(url)


class _Handler(BaseHTTPRequestHandler):
    fetcher: Fetcher
    server_version = "exocortex-lab-fetch"
    sys_version = ""

    def _serve(self, method: str) -> None:
        started = time.monotonic()
        status, body, ctype, fields = self.fetcher.handle(method, self.path)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)
        print(json.dumps({"event": "fetch", "method": method, "status": status, "bytes": len(body),
                          "ms": round((time.monotonic() - started) * 1000), **fields}), flush=True)

    def do_GET(self) -> None:
        self._serve("GET")

    def _deny(self) -> None:
        self._serve(self.command)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_CONNECT = do_TRACE = _deny

    def log_message(self, format: str, *args) -> None:
        pass

    def address_string(self) -> str:
        return "unix" if not self.client_address else str(self.client_address[0])


def make_server(fetcher: Fetcher, listen: str):
    """Same listeners as the model gateway: ``unix:/path.sock`` or ``host:port``."""
    from exocortex.lab import llm_gateway

    handler = type("Handler", (_Handler,), {"fetcher": fetcher})
    if listen.startswith("unix:"):
        return llm_gateway._UnixHTTPServer(listen.removeprefix("unix:"), handler)
    from http.server import ThreadingHTTPServer

    host, _, port = listen.rpartition(":")
    return ThreadingHTTPServer((host or "0.0.0.0", int(port)), handler)


def main() -> int:
    allowlist = Allowlist.load(Path(os.environ.get("EXOCORTEX_SOURCE_ALLOWLIST", "/opt/exocortex/lab/sources.yaml")))
    listen = os.environ.get("LAB_FETCH_LISTEN", "unix:/run/lab-fetch/fetch.sock")
    fetcher = Fetcher(allowlist, max_bytes=int(os.environ.get("LAB_FETCH_MAX_BYTES", str(20 * 1024 * 1024))))
    server = make_server(fetcher, listen)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    print(json.dumps({"event": "fetch_gateway_start", "listen": listen, "sources": len(allowlist.sources)}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
