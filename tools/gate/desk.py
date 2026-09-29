"""Review desk for the quarantine database: a small web page for the owner (standard library only).

Screens: the queue of held units, focus mode (one finding at a time, the
public paragraph next to its three nearest protected ones), standing rules
and switched-off sources, and the history.

Everything comes from the configuration (environment variables, see
``DeskConfig.from_env``); nothing site-specific is in the code. Security:

- listens on the loopback interface unless configured otherwise;
- an access token from a file named in the configuration; without it the
  desk refuses to start (``ConfigError``);
- a browser session is a cookie (HttpOnly, SameSite=Strict) and every
  change needs the CSRF token the page carries, a JSON content type and a
  matching Origin; the Host header must be one of the configured names;
- ``Cache-Control: no-store`` on every response, a content security policy
  that allows nothing from another origin, no external resources at all;
- request bodies and paragraph text are never logged, and protected text is
  read from the index only while a response is being built.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tools.publisher import approvals, ratings
from tools.publisher.quarantine import (
    HardListUnavailable, HardListViolation, InvalidInput, InvalidState, LiteralNotApprovable, NotFound,
    QuarantineError, StaleConfirmation, Store, clean_path, is_literal_rule, paragraph_key,
)

STATIC = Path(__file__).parent / "desk_static"
MAX_BODY = 64 * 1024
MAX_PUBLIC_FILE = 2 * 1024 * 1024
MIN_TOKEN = 16
LOGIN_LIMIT = (10, 300)  # failures, seconds
LOOPBACK = ("127.0.0.1", "::1", "localhost")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class ConfigError(Exception):
    pass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return None if v is None or v.strip().lower() in ("", "none", "unset") else v.strip()


class DeskConfig:
    def __init__(self, db: Path, token: str, host: str = "127.0.0.1", port: int = 8770, user: str = "owner",
                 docs: Path | None = None, index_link: Path | None = None, corpus_root: str = "/corpus",
                 never_exclude_file: Path | None = None, allowed_hosts: tuple[str, ...] = (),
                 secure_cookie: bool = False, state: Path | None = None, lab: Path | None = None,
                 drafts: Path | None = None, rater: str | None = None):
        self.db, self.token, self.host, self.port, self.user = db, token, host, port, user
        self.docs, self.index_link, self.corpus_root = docs, index_link, corpus_root
        self.never_exclude_file, self.secure_cookie = never_exclude_file, secure_cookie
        self.allowed_hosts = allowed_hosts
        self.state = state  # holds the publish request and the publisher's run log
        self.lab = lab      # the lab's output folder: generated pages, data and blind rating pages are read from here
        self.drafts = drafts  # the lab's drafts folder (applications sections waiting for the owner), read-only
        self.rater = rater or user  # the pseudonym written on rated pages

    @classmethod
    def from_env(cls) -> "DeskConfig":
        token_file = _env("GATE_DESK_TOKEN_FILE")
        if not token_file:
            raise ConfigError("GATE_DESK_TOKEN_FILE is not set; the desk does not start without a token")
        token = load_token(Path(token_file))
        state = Path(_env("GATE_STATE", "/state"))
        host = _env("GATE_DESK_HOST", "127.0.0.1")
        port = int(_env("GATE_DESK_PORT", "8770"))
        extra = tuple(x.strip() for x in (_env("GATE_DESK_ALLOWED_HOSTS") or "").split(",") if x.strip())
        return cls(db=Path(_env("GATE_QUARANTINE_DB") or state / "quarantine.sqlite3"), token=token, host=host, port=port,
                   user=_env("GATE_DESK_USER", "owner"), docs=Path(_env("GATE_SOURCE", "/source")),
                   index_link=Path(_env("GATE_INDEX", "/index")) / "current", corpus_root=_env("GATE_CORPUS_DIR", "/corpus"),
                   never_exclude_file=Path(p) if (p := _env("GATE_NEVER_EXCLUDE_FILE")) else None, allowed_hosts=extra,
                   secure_cookie=_env("GATE_DESK_SECURE_COOKIE", "0") == "1", state=state,
                   lab=Path(p) if (p := _env("GATE_LAB_SOURCE")) else None,
                   drafts=Path(p) if (p := _env("GATE_DRAFTS")) else None,
                   rater=_env("GATE_BLIND_RATER") or _env("GATE_DESK_USER", "owner"))


def load_token(path: Path) -> str:
    """The access token from a secret file; a missing, unreadable, empty or short one is a ConfigError."""
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError("the token file cannot be read; the desk does not start without a token") from exc
    if len(token) < MIN_TOKEN:
        raise ConfigError(f"the token must have at least {MIN_TOKEN} characters")
    return token


# -- publish on request -----------------------------------------------------------------------
# The desk only writes a request file into the state volume. A path unit on the server watches that file
# and starts the publisher (deploy/gate/systemd); the desk never starts anything itself. The publisher
# still applies every gate, so the button releases nothing that is held.

REQUEST_FILE = "publish-request"


def last_run(state: Path | None) -> dict | None:
    """The newest publisher run from the run log, cut down to counts and status (never paths or text)."""
    if state is None:
        return None
    try:
        with (state / "runs.jsonl").open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 262144))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and "status" in d:
            return {"time": d.get("time"), "status": d.get("status"), "published": len(d.get("published") or []),
                    "held": len(d.get("held") or {}), "pushed": bool(d.get("pushed"))}
    return None


def request_publish(state: Path, who: str) -> bool:
    """Write the request file; False when a request is already waiting."""
    try:
        fd = os.open(state / REQUEST_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "who": who}, fh)
    return True


# -- protected text: read only while a response is built ------------------------------------

class IndexProvider:
    """Builds the focus card of a finding from the public source and the index.

    The index holds the protected paragraphs; they are returned in the response
    and kept nowhere else. ``store`` supplies the exclusion list so switched-off
    sources do not show up as neighbours.
    """

    def __init__(self, holder, docs: Path, corpus_root: str, store: Store, lab: Path | None = None):
        self.holder, self.docs, self.corpus_root, self.store = holder, Path(docs), corpus_root.rstrip("/"), store
        self.lab = Path(lab) if lab else None

    def _read(self, rel: str) -> str | None:
        for base in (self.docs, self.lab):  # the vault first, then the lab's output (generated pages, data)
            if base is None:
                continue
            try:
                root = base.resolve()
                p = (root / clean_path(rel)).resolve()
                if root not in p.parents or not p.is_file() or p.stat().st_size > MAX_PUBLIC_FILE:
                    continue
                return p.read_text(encoding="utf-8", errors="ignore")
            except (OSError, InvalidInput):
                continue
        return None

    def _rel(self, source: str | None) -> str | None:
        if source and source.startswith(self.corpus_root + "/"):
            return source[len(self.corpus_root) + 1:]
        return None

    def paragraph(self, finding: dict) -> str | None:
        from tools.simcheck.core import paragraphs

        text = self._read(finding["path"])
        if text is None or not finding["para_hash"]:
            return None
        return next((p for p in paragraphs(text) if paragraph_key(p) == finding["para_hash"]), None)

    def card(self, finding: dict) -> dict:
        index = self.holder.refresh() if hasattr(self.holder, "refresh") else self.holder
        para = self.paragraph(finding)
        near: list[dict] = []
        if para is not None:
            mask = index.exclusion_mask(self.store.active_exclusion_paths(), self.corpus_root)
            if index.texts is not None:
                if not finding["literal"] and index.vectors is not None:
                    q = index._embed_queries([para])
                    _raw, ids = index.semantic_neighbours([para], 3, q=q, mask=mask)
                    pairs = [(float(q[0] @ index.vectors[j]), j) for j in ids[0] if mask is None or not mask[j]]
                else:
                    pairs = index.literal_neighbours(para, 3, mask)
                for score, j in pairs:
                    src = index.sources[j] if index.sources else None
                    rel = self._rel(src)
                    near.append({"score": float(score), "text": index.texts[j], "source": rel or ("database" if src else None),
                                 "note_path": rel, "folder_path": (rel.rsplit("/", 1)[0] + "/") if rel and "/" in rel else None})
        return {"finding_id": finding["id"], "public": para, "neighbours": near,
                "hint": hint(finding, index.thresholds)}


def hint(finding: dict, thresholds: dict) -> str:
    if finding["literal"] or is_literal_rule(finding["rule"]):
        return "Literal finding (a name, personal data or a near copy). It cannot be kept; edit the paragraph."
    if finding["score"] >= thresholds.get("semantic", 0.9) + 0.05:
        return "Very close to a protected paragraph. Check whether it repeats a specific fact, figure, name or decision."
    return "Close in meaning. If only the topic or a general method is shared, keep it; if a specific detail repeats, edit it."


# -- HTTP -------------------------------------------------------------------------------------

def _digest(token: str, label: bytes) -> str:
    return hmac.new(token.encode(), label, hashlib.sha256).hexdigest()


class Desk:
    """State shared by the request handlers."""

    def __init__(self, cfg: DeskConfig, store: Store, provider):
        self.cfg, self.store, self.provider = cfg, store, provider
        self.session = _digest(cfg.token, b"desk-session")
        self.csrf = _digest(self.session, b"desk-csrf")
        self.fail_lock = threading.Lock()
        self.failures: dict[str, list[float]] = {}
        bound = f"{cfg.host}:{cfg.port}"
        names = {bound, *cfg.allowed_hosts}
        if cfg.host in LOOPBACK or cfg.host.startswith("127."):
            names |= {f"{n}:{cfg.port}" for n in ("127.0.0.1", "localhost", "[::1]")}
        self.hosts = {n.lower() for n in names}

    def throttled(self, ip: str) -> bool:
        with self.fail_lock:
            now = time.time()
            recent = [t for t in self.failures.get(ip, []) if now - t < LOGIN_LIMIT[1]]
            self.failures[ip] = recent
            return len(recent) >= LOGIN_LIMIT[0]

    def failed(self, ip: str) -> None:
        with self.fail_lock:
            self.failures.setdefault(ip, []).append(time.time())


ERRORS = {NotFound: 404, InvalidInput: 400, InvalidState: 409, StaleConfirmation: 409, LiteralNotApprovable: 409,
          HardListUnavailable: 503, HardListViolation: 403}


def _status(exc: QuarantineError) -> int:
    for cls, code in ERRORS.items():
        if isinstance(exc, cls):
            return code
    return 400


def unit_view(store: Store, uid: int) -> dict:
    unit = store.get_unit(uid)
    findings = store.findings(uid, ("open", "kept", "to_edit"))
    folders = sorted({f["path"].rsplit("/", 1)[0] + "/" for f in findings if "/" in f["path"]})
    strip = lambda p: {k: v for k, v in p.items() if k != "ids"}  # noqa: E731
    return {"unit": unit, "progress": store.progress(uid), "findings": findings,
            "bulk": {"unit": strip(store.bulk_preview(uid)), "folders": {f: strip(store.bulk_preview(uid, f)) for f in folders}}}


def make_handler(desk: Desk):
    cfg, store = desk.cfg, desk.store

    class Handler(BaseHTTPRequestHandler):
        server_version = "desk"
        sys_version = ""

        def log_message(self, fmt, *args):  # never log requests
            return

        # -- plumbing
        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict, extra: dict | None = None) -> None:
            self._send(code, json.dumps(payload).encode(), "application/json", extra)

        def _error(self, code: int, error: str, message: str = "") -> None:
            self._json(code, {"error": error, "message": message or error})

        def _cookie(self) -> str:
            for part in self.headers.get("Cookie", "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "desk":
                    return v
            return ""

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "").lower() in desk.hosts

        def _auth(self) -> str | None:
            """'bearer', 'cookie' or None."""
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip().encode(), cfg.token.encode()):
                return "bearer"
            if hmac.compare_digest(self._cookie().encode(), desk.session.encode()):
                return "cookie"
            return None

        def _same_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None and origin.split("://", 1)[-1].lower() not in desk.hosts:
                return False
            return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")

        def _body(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if length > MAX_BODY or length < 0:
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                return None
            return data if isinstance(data, dict) else None

        # -- dispatch
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method: str) -> None:
            try:
                self._route(method)
            except QuarantineError as exc:
                self._error(_status(exc), type(exc).__name__, str(exc))
            except Exception as exc:  # noqa: BLE001 - report the type only, never content
                self._error(500, type(exc).__name__)

        def _route(self, method: str) -> None:
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            if not self._host_ok():
                return self._error(421, "bad host")
            if path.startswith("/static/") and method == "GET":
                return self._static(path[len("/static/"):])
            if path == "/login" and method == "POST":
                return self._login()
            mode = self._auth()
            if mode is None:
                if method == "GET" and path == "/":
                    return self._send(401, (STATIC / "login.html").read_bytes(), "text/html; charset=utf-8")
                return self._error(401, "unauthorised")
            if method == "POST":
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    return self._error(415, "json only")
                if mode == "cookie" and not (
                        self._same_origin() and hmac.compare_digest((self.headers.get("X-CSRF-Token") or "").encode(),
                                                                    desk.csrf.encode())):
                    return self._error(403, "csrf")
            if method == "GET" and path == "/":
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{CSRF}}", desk.csrf)
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            body = self._body() if method == "POST" else {}
            if body is None:
                return self._error(400, "bad body")
            self._api(method, path, query, body)

        def _static(self, name: str) -> None:
            files = {"desk.js": "text/javascript; charset=utf-8", "logic.js": "text/javascript; charset=utf-8", "blind.js": "text/javascript; charset=utf-8", "md.js": "text/javascript; charset=utf-8",
                     "desk.css": "text/css; charset=utf-8",
                     "vendor/marked.umd.js": "text/javascript; charset=utf-8",
                     "vendor/purify.min.js": "text/javascript; charset=utf-8"}
            if name not in files:
                return self._error(404, "not found")
            self._send(200, (STATIC / name).read_bytes(), files[name])

        def _login(self) -> None:
            ip = self.client_address[0]
            if desk.throttled(ip):
                return self._error(429, "too many attempts")
            if not self._same_origin() or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._error(403, "csrf")
            body = self._body()
            token = body.get("token") if body else None
            if not isinstance(token, str) or not hmac.compare_digest(token.encode(), cfg.token.encode()):
                desk.failed(ip)
                return self._error(401, "unauthorised")
            flags = "HttpOnly; SameSite=Strict; Path=/" + ("; Secure" if cfg.secure_cookie else "")
            self._json(200, {"ok": True}, {"Set-Cookie": f"desk={desk.session}; {flags}"})

        # -- API
        def _api(self, method: str, path: str, query: dict, body: dict) -> None:
            who = cfg.user
            parts = [p for p in path.split("/") if p]
            if parts[:1] != ["api"]:
                return self._error(404, "not found")
            parts = parts[1:]

            def num(i: int) -> int:
                try:
                    return int(parts[i])
                except (IndexError, ValueError):
                    raise NotFound("not found") from None

            def one(name: str) -> str | None:
                return (query.get(name) or [None])[0]

            if method == "GET":
                if parts == ["units"]:
                    store.expire()
                    return self._json(200, {"units": store.list_units()})
                if len(parts) == 2 and parts[0] == "units":
                    return self._json(200, unit_view(store, num(1)))
                if len(parts) == 3 and parts[0] == "units" and parts[2] == "bulk":
                    pv = store.bulk_preview(num(1), one("folder"))
                    return self._json(200, {k: v for k, v in pv.items() if k != "ids"})
                if len(parts) == 3 and parts[0] == "findings" and parts[2] == "card":
                    return self._json(200, desk.provider.card(store.finding(num(1))))
                if parts == ["rules"]:
                    return self._json(200, {"standing": store.standing_rules(), "exclusions": store.exclusions(),
                                            "hard_list": store.hard_list_status()})
                if parts == ["publish"]:
                    return self._json(200, {"configured": cfg.state is not None,
                                            "pending": cfg.state is not None and (cfg.state / REQUEST_FILE).exists(),
                                            "last": last_run(cfg.state)})
                if parts == ["drafts"]:
                    if cfg.docs is None:
                        return self._json(200, {"configured": False, "drafts": []})
                    return self._json(200, {"configured": True, "drafts": approvals.list_drafts(cfg.docs, cfg.state, cfg.drafts)})
                if parts == ["history"]:
                    return self._json(200, {"history": store.history(int(one("limit") or 200))})
                # Blind rating: the page's items and the owner's own ratings, never a configuration or a result
                if parts == ["blind"]:
                    return self._json(200, {"configured": cfg.lab is not None and cfg.state is not None,
                                            "samples": ratings.list_samples(cfg.lab, cfg.state)})
                if len(parts) == 3 and parts[0] == "blind":
                    if cfg.lab is None:
                        return self._error(503, "not configured", "the desk has no lab folder")
                    try:
                        return self._json(200, ratings.view(cfg.lab, cfg.state, parts[1], parts[2]))
                    except ratings.RatingError as exc:
                        return self._error(404, "RatingError", str(exc))
                return self._error(404, "not found")

            # POST
            if len(parts) == 3 and parts[0] == "findings" and parts[2] == "decide":
                f = store.decide(num(1), str(body.get("decision")), who, body.get("note"))
                return self._json(200, {"finding": f, "progress": store.progress(f["unit_id"])})
            if len(parts) == 3 and parts[0] == "findings" and parts[2] == "reopen":
                f = store.reopen(num(1), who)
                return self._json(200, {"finding": f, "progress": store.progress(f["unit_id"])})
            if parts == ["publish"]:
                if cfg.state is None:
                    return self._error(503, "not configured", "the desk has no state folder for publish requests")
                created = request_publish(cfg.state, who)
                return self._json(200, {"requested": True, "already": not created})
            if len(parts) == 3 and parts[0] == "drafts" and parts[2] in ("approve", "withdraw"):
                if cfg.docs is None or cfg.state is None:
                    return self._error(503, "not configured", "the desk has no documents or state folder for approvals")
                try:
                    if parts[2] == "approve":
                        rec = approvals.approve(cfg.docs, cfg.state, parts[1], body.get("sha"), who,
                                                origin=body.get("origin"), drafts=cfg.drafts)
                        return self._json(200, {"approved": True, "at": rec["at"]})
                    return self._json(200, {"withdrawn": approvals.withdraw(cfg.state, parts[1], body.get("origin"))})
                except approvals.ApprovalError as exc:
                    return self._error(409, "ApprovalError", str(exc))
            if len(parts) == 4 and parts[0] == "blind" and parts[3] in ("rate", "finish"):
                if cfg.lab is None or cfg.state is None:
                    return self._error(503, "not configured", "the desk has no lab or state folder for ratings")
                try:
                    if parts[3] == "rate":
                        return self._json(200, ratings.rate(cfg.lab, cfg.state, parts[1], parts[2], body.get("position"),
                                                            body.get("verdicts"), body.get("source_mode"),
                                                            body.get("comment"), body.get("page_sha"), who))
                    return self._json(200, ratings.finish(cfg.lab, cfg.state, parts[1], parts[2], body.get("page_sha"),
                                                          cfg.rater))
                except ratings.RatingError as exc:
                    return self._error(400, "RatingError", str(exc))
            if parts == ["undo"]:
                return self._json(200, {"undone": store.undo_last(who)})
            if len(parts) == 3 and parts[0] == "units" and parts[2] == "bulk":
                if body.get("confirm") is not True:
                    return self._error(400, "confirmation required", "the summary must be confirmed")
                return self._json(200, store.bulk_keep(num(1), body.get("folder"), str(body.get("digest")), who))
            if parts == ["rules", "standing"]:
                return self._json(200, store.add_standing_rule(str(body.get("folder", "")), body.get("reason"), who, body.get("days")))
            if len(parts) == 4 and parts[:2] == ["rules", "standing"] and parts[3] == "revoke":
                store.revoke_standing_rule(num(2), who)
                return self._json(200, {"ok": True})
            if parts == ["exclusions"]:
                scope = body.get("scope")
                if scope not in ("note", "folder"):
                    raise InvalidInput("scope must be note or folder")
                return self._json(200, store.add_exclusion(str(body.get("path", "")), body.get("reason"), who,
                                                           body.get("days"), folder=scope == "folder"))
            if len(parts) == 3 and parts[0] == "exclusions" and parts[2] == "revoke":
                store.revoke_exclusion(num(1), who)
                return self._json(200, {"ok": True})
            return self._error(404, "not found")

    return Handler


def make_server(cfg: DeskConfig, store: Store, provider) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((cfg.host, cfg.port), make_handler(Desk(cfg, store, provider)))


def serve(cfg: DeskConfig | None = None) -> int:
    import signal

    try:
        cfg = cfg or DeskConfig.from_env()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    from tools.simcheck.server import IndexHolder

    store = Store(cfg.db, never_exclude_file=cfg.never_exclude_file)
    provider = IndexProvider(IndexHolder(cfg.index_link), cfg.docs, cfg.corpus_root, store, cfg.lab) if cfg.index_link and cfg.index_link.exists() \
        else NoIndexProvider()
    if not (cfg.host in LOOPBACK or cfg.host.startswith("127.")):
        print("warning: the desk listens on a non-loopback address", file=sys.stderr)
    make_server(cfg, store, provider).serve_forever()
    return 0


class NoIndexProvider:
    """Used when there is no index: the queue and the history work, cards show no protected text."""

    def card(self, finding: dict) -> dict:
        return {"finding_id": finding["id"], "public": None, "neighbours": [],
                "hint": "No index is available, so no protected paragraphs can be shown."}
