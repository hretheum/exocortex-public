# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's one path to the local model server.

The lab network is internal: nothing on it reaches the host, the LAN or the
internet. This gateway is the exception. It does not join the lab network:
it runs with its own network namespace in which only the model server's
port on the host loopback is forwarded, and it serves lab processes over a
Unix socket in a volume they mount. It forwards exactly these calls to one
fixed upstream address (the local llama-swap server):

    GET  /v1/models            the list, filtered to the allowed models
    POST /v1/chat/completions  only for a model on lab/models.yaml
    POST /v1/embeddings        only for a model on lab/models.yaml
    GET  /health               answered by the gateway itself

Everything else gets 403: other paths (the server's admin endpoints too),
other methods, CONNECT, absolute-form targets. The target is never taken
from the request, redirects are not followed, environment proxies are
ignored and streaming is refused. Every request is logged as one JSON line
with path, model, status, sizes, token counts and time; prompts and
answers are never logged.

    LAB_LLM_UPSTREAM=http://127.0.0.1:8080 LAB_LLM_LISTEN=unix:/run/lab-llm/gateway.sock \
        python -m exocortex.lab.llm_gateway
"""

from __future__ import annotations

import json
import os
import signal
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

FORWARDED = {("GET", "/v1/models"), ("POST", "/v1/chat/completions"), ("POST", "/v1/embeddings")}
MODEL_FIELDS = ("id", "family", "weights", "license", "basis", "added_by", "reason")
# A hosted model (provider other than local) also needs these: it may see public texts only,
# and only in the experiments it is listed for.
HOSTED_FIELDS = ("data_class", "experiments")
LOCAL = "local"
DEFAULT_MODELS_FILE = "/opt/exocortex/lab/models.yaml"


class ModelNotAllowed(PermissionError):
    """A model use that lab/models.yaml does not allow."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # the upstream is fixed; a redirect is answered, not followed


def _opener() -> urllib.request.OpenerDirector:
    # ProxyHandler({}) keeps HTTP(S)_PROXY from the environment out of the path
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def load_models(path: Path) -> dict[str, dict]:
    """Allowed models by id. Every entry needs all of MODEL_FIELDS; a hosted one also HOSTED_FIELDS,
    with ``data_class: public`` and at least one experiment."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for i, raw in enumerate(data.get("models") or []):
        missing = [k for k in MODEL_FIELDS if not raw.get(k)]
        if raw.get("provider", LOCAL) != LOCAL:
            missing += [k for k in HOSTED_FIELDS if not raw.get(k)]
            if raw.get("data_class") not in (None, "public"):
                raise ValueError(f"{path}: model #{i} is not local, so it needs data_class: public")
        if missing:
            raise ValueError(f"{path}: model #{i} is missing {', '.join(missing)}")
        out[str(raw["id"])] = raw
    return out


def local_models(models: dict[str, dict]) -> set[str]:
    """Ids the gateway serves: it reaches only the local model server."""
    return {m for m, entry in models.items() if entry.get("provider", LOCAL) == LOCAL}


def authorize(models: dict[str, dict], model: str, data_class: str, experiment: str | None = None) -> dict:
    """The entry of ``model`` if this use is allowed, else ModelNotAllowed.

    A model outside the list is refused. A hosted model is refused for any data other than public,
    and outside the experiments its entry lists.
    """
    entry = models.get(model)
    if entry is None:
        raise ModelNotAllowed(f"model {model!r} is not in lab/models.yaml")
    if entry.get("provider", LOCAL) != LOCAL:
        if data_class != "public" or entry.get("data_class") != "public":
            raise ModelNotAllowed(f"model {model!r} runs outside the lab and takes public data only, not {data_class!r}")
        if experiment not in (entry.get("experiments") or []):
            raise ModelNotAllowed(f"{model!r} may be used only in {', '.join(entry['experiments'])}")
    return entry


def _error(message: str) -> bytes:
    return json.dumps({"error": message}).encode()


class Gateway:
    """Request policy and forwarding, without the HTTP server around it."""

    def __init__(self, upstream: str, models: set[str], timeout: float = 900.0,
                 opener: urllib.request.OpenerDirector | None = None):
        self.upstream = upstream.rstrip("/")
        self.models = set(models)
        self.timeout = timeout
        self.opener = opener or _opener()

    def handle(self, method: str, target: str, body: bytes) -> tuple[int, bytes, dict]:
        """(status, response body, fields for the log line) for one request."""
        route = target.split("?", 1)[0]
        if (method, route) == ("GET", "/health"):
            return 200, json.dumps({"status": "ok", "models": sorted(self.models)}).encode(), {}
        if (method, route) not in FORWARDED:
            return 403, _error("not allowed"), {}
        if method == "GET":
            status, data = self._forward("GET", route, None)
            return status, self._filter_models(data) if status == 200 else data, {}
        try:
            req = json.loads(body or b"null")
        except ValueError:
            return 400, _error("body is not JSON"), {}
        if not isinstance(req, dict):
            return 400, _error("body must be a JSON object"), {}
        model = req.get("model")
        fields = {"model": str(model)[:80]}
        if model not in self.models:
            return 403, _error("model not allowed"), fields
        if req.get("stream"):
            return 400, _error("streaming is not supported"), fields
        status, data = self._forward("POST", route, body)
        fields.update(_usage(data) if status == 200 else {})
        return status, data, fields

    def _filter_models(self, data: bytes) -> bytes:
        try:
            doc = json.loads(data)
            doc["data"] = [m for m in doc.get("data") or [] if m.get("id") in self.models]
            return json.dumps(doc).encode()
        except (ValueError, AttributeError, TypeError):
            return _error("unexpected model list from upstream")

    def _forward(self, method: str, route: str, body: bytes | None) -> tuple[int, bytes]:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = urllib.request.Request(self.upstream + route, data=body, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() or _error(f"upstream answered {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 502, _error(f"upstream unavailable ({type(exc).__name__})")


def _usage(data: bytes) -> dict:
    try:
        usage = json.loads(data).get("usage") or {}
    except (ValueError, AttributeError):
        return {}
    return {k: usage[k] for k in ("prompt_tokens", "completion_tokens") if isinstance(usage.get(k), int)}


class _Handler(BaseHTTPRequestHandler):
    gateway: Gateway
    max_body: int = 4 * 1024 * 1024
    server_version = "exocortex-lab-llm"
    sys_version = ""

    def _serve(self, method: str) -> None:
        started = time.monotonic()
        fields: dict[str, Any]
        length = int(self.headers.get("Content-Length") or 0)
        if length > self.max_body:
            status, data, fields = 413, _error("request too large"), {}
            self.close_connection = True
        else:
            body = self.rfile.read(length) if length else b""
            status, data, fields = self.gateway.handle(method, self.path, body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        line = {"event": "llm_request", "method": method, "path": self.path.split("?", 1)[0][:120],
                "status": status, "ms": round((time.monotonic() - started) * 1000), "in_bytes": length,
                "out_bytes": len(data), **fields}
        print(json.dumps(line), flush=True)

    def do_GET(self) -> None:  # http.server naming
        self._serve("GET")

    def do_POST(self) -> None:
        self._serve("POST")

    def _deny(self) -> None:
        self._serve(self.command)

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_CONNECT = do_TRACE = _deny

    def log_message(self, format: str, *args) -> None:  # replaced by JSON lines
        pass

    def address_string(self) -> str:
        return "unix" if not self.client_address else str(self.client_address[0])


class _UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def server_bind(self) -> None:
        path = Path(cast(str, self.server_address))  # make_server binds it to a str path
        if path.is_socket():
            path.unlink()  # left over from a previous run
        super().server_bind()
        path.chmod(0o660)


def make_server(gateway: Gateway, listen: str, max_body: int | None = None) -> socketserver.BaseServer:
    """HTTP server for ``unix:/path/to.sock`` or ``host:port``."""
    attrs: dict[str, Any] = {"gateway": gateway}
    if max_body is not None:
        attrs["max_body"] = max_body
    handler = type("Handler", (_Handler,), attrs)
    if listen.startswith("unix:"):
        return _UnixHTTPServer(listen.removeprefix("unix:"), handler)
    host, _, port = listen.rpartition(":")
    return ThreadingHTTPServer((host or "0.0.0.0", int(port)), handler)


def main() -> int:
    upstream = os.environ.get("LAB_LLM_UPSTREAM", "").strip()
    if not upstream:
        print("LAB_LLM_UPSTREAM is not set", file=sys.stderr)
        return 2
    models = load_models(Path(os.environ.get("LAB_LLM_MODELS", DEFAULT_MODELS_FILE)))
    listen = os.environ.get("LAB_LLM_LISTEN", "unix:/run/lab-llm/gateway.sock")
    gateway = Gateway(upstream, local_models(models), timeout=float(os.environ.get("LAB_LLM_TIMEOUT", "900")))
    server = make_server(gateway, listen, int(os.environ.get("LAB_LLM_MAX_BODY", "4194304")))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    print(json.dumps({"event": "llm_gateway_start", "listen": listen, "models": sorted(gateway.models)}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
