# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Isolation check of the Exocortex lab (roadmap task F2.1).

Runs inside a lab container, with the lab's network, mounts and
environment. Passes only when:

1. the lab database answers (positive control: the check itself works);
2. none of the addresses in LAB_PRIVATE_DB_TARGETS accepts a TCP connection
   (the private database is out of reach, before any password is tried);
3. the only part of the vault visible is the published documents folder;
4. the environment points at the lab database only;
5. the source allowlist (F2.2) is configured and loads;
6. direct connections to the outside (internet, the local model server on
   the host) fail: nothing leaves the lab network on its own;
7. if the lab has its gateway to the local model server (LAB_LLM_URL), the
   gateway answers, lists only models from the allowlist and refuses other
   paths, other models and absolute-form targets;
8. if the lab has its gateway for downloads (LAB_FETCH_URL), the gateway
   answers and refuses other domains, plain http, the host loopback, other
   methods and other paths (without downloading anything real).

Prints one JSON line and exits 0 (pass) or 1 (fail). It never prints
secrets: addresses and paths only.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

VAULT = Path(os.environ.get("LAB_VAULT_ROOT", "/vault"))
ALLOWED_VAULT = {Path("_source"), Path("_source/dowody")}
FORBIDDEN_PATHS = ["/corpus", "/var/home", "/home/hretheum", "/vault/wiki", "/vault/_source/work",
                   "/vault/_source/prv", "/vault/_source/dowody-prywatne", "/run/secrets/simcheck_pg_dsn"]
LAB_DB_HOST = os.environ.get("LAB_DB_HOST", "exocortex-lab-db")
# Outside addresses no lab process may reach directly: the internet (by
# address and by name) and the local model server on the host loopback.
EGRESS_PROBES = "1.1.1.1:443,export.arxiv.org:443,host.containers.internal:8080,169.254.1.2:8080"


def _pairs(raw: str) -> list[tuple[str, int]]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            host, _, port = item.rpartition(":")
            out.append((host, int(port)))
    return out


def _targets() -> list[tuple[str, int]]:
    return _pairs(os.environ.get("LAB_PRIVATE_DB_TARGETS", "host.containers.internal:5432,169.254.1.2:5432"))


def reachable(host: str, port: int, timeout: float = 3.0) -> str:
    """'open' if a TCP connection is accepted, else a short reason."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "no-name"
    for family, kind, proto, _canon, addr in infos:
        s = socket.socket(family, kind, proto)
        s.settimeout(timeout)
        try:
            s.connect(addr)
            return "open"
        except (TimeoutError, OSError) as exc:
            reason = type(exc).__name__
        finally:
            s.close()
    return reason


def egress() -> dict[str, str]:
    """Direct connections to the outside, each expected to fail."""
    probes = _pairs(os.environ.get("LAB_EGRESS_PROBES", EGRESS_PROBES))
    return {f"{h}:{p}": reachable(h, p) for h, p in probes}


def _connection(base: str):
    """HTTP connection to ``unix:/path.sock`` or ``http://host:port``."""
    import http.client

    if base.startswith("unix:"):
        path = base.removeprefix("unix:")

        class _Unix(http.client.HTTPConnection):
            def connect(self) -> None:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect(path)

        return _Unix("gateway", timeout=30)
    u = urlparse(base)
    return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=30)


def _http(method: str, base: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    """Status and body of one request; ``path`` goes into the request line as is."""
    c = _connection(base)
    try:
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        r = c.getresponse()
        return r.status, r.read()
    except OSError as exc:
        return 0, type(exc).__name__.encode()
    finally:
        c.close()


def llm_channel() -> dict:
    """State of the gateway to the local model server; {} if the lab has none."""
    base = os.environ.get("LAB_LLM_URL", "").strip().rstrip("/")
    if not base:
        return {}
    allowed_file = Path(os.environ.get("LAB_LLM_MODELS", "/opt/exocortex/lab/models.yaml"))
    try:
        import yaml

        allowed = {str(m["id"]) for m in (yaml.safe_load(allowed_file.read_text(encoding="utf-8")) or {})["models"]}
    except Exception as exc:  # noqa: BLE001 - report the type only
        return {"allowlist": type(exc).__name__}
    out: dict = {"health": _http("GET", base, "/health")[0]}
    status, data = _http("GET", base, "/v1/models")
    try:
        listed = sorted(m["id"] for m in json.loads(data).get("data", [])) if status == 200 else []
    except (ValueError, KeyError, TypeError, AttributeError):
        listed = []
    out["models"] = listed
    out["models_off_list"] = sorted(set(listed) - allowed)
    out["admin_path"] = _http("GET", base, "/running")[0]
    out["other_model"] = _http("POST", base, "/v1/chat/completions",
                               {"model": "not-on-the-allowlist", "messages": [{"role": "user", "content": "x"}]})[0]
    out["absolute_target"] = _http("GET", base, "http://example.com/")[0]
    return out


def llm_channel_ok(state: dict) -> bool:
    if not state:
        return True
    return (state.get("health") == 200 and not state.get("models_off_list") and "allowlist" not in state
            and state.get("admin_path") == 403 and state.get("other_model") == 403
            and state.get("absolute_target") == 403)


def fetch_channel() -> dict:
    """State of the gateway for downloads; {} if the lab has none. Never downloads anything real."""
    base = os.environ.get("LAB_FETCH_URL", "").strip().rstrip("/")
    if not base:
        return {}
    from urllib.parse import quote

    return {"health": _http("GET", base, "/health")[0],
            "other_domain": _http("GET", base, "/fetch?url=" + quote("https://example.com/", safe=""))[0],
            "plain_http": _http("GET", base, "/fetch?url=" + quote("http://arxiv.org/", safe=""))[0],
            "host_loopback": _http("GET", base, "/fetch?url=" + quote("https://127.0.0.1:8080/", safe=""))[0],
            "post": _http("POST", base, "/fetch?url=" + quote("https://arxiv.org/", safe=""), {})[0],
            "other_path": _http("GET", base, "/running")[0]}


def fetch_channel_ok(state: dict) -> bool:
    if not state:
        return True
    return state.get("health") == 200 and all(state.get(k) == 403 for k in
                                              ("other_domain", "plain_http", "host_loopback", "post", "other_path"))


def lab_db_answers() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if urlparse(url).hostname != LAB_DB_HOST:
        return "DATABASE_URL does not point at the lab database"
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception as exc:  # noqa: BLE001 - report the type only
        return type(exc).__name__


def visible_vault() -> list[str]:
    """Vault paths visible beyond the allowed ones (first two levels)."""
    extra = []
    if not VAULT.exists():
        return extra
    for p in VAULT.iterdir():
        rel = p.relative_to(VAULT)
        if rel not in ALLOWED_VAULT:
            extra.append(str(rel))
        elif p.is_dir():
            for q in p.iterdir():
                if q.relative_to(VAULT) not in ALLOWED_VAULT:
                    extra.append(str(q.relative_to(VAULT)))
    return extra


def env_leaks() -> list[str]:
    """Environment variables that look like access to something other than the lab."""
    leaks = []
    for key, value in os.environ.items():
        if key in ("DATABASE_URL", "EXOCORTEX_DATABASE_URL", "SIMCHECK_PG_DSN") and value:
            host = urlparse(value).hostname
            if host != LAB_DB_HOST:
                leaks.append(key)
        if key in ("PG_HOST", "POSTGRES_HOST") and value and value != LAB_DB_HOST:
            leaks.append(key)
    return leaks


def allowlist_state() -> str:
    path = os.environ.get("EXOCORTEX_SOURCE_ALLOWLIST", "").strip()
    if not path:
        return "not configured"
    try:
        from exocortex.source_allowlist import Allowlist

        return f"ok:{len(Allowlist.load(Path(path)).sources)}"
    except Exception as exc:  # noqa: BLE001 - report the type only
        return type(exc).__name__


def main() -> int:
    result = {"lab_db": lab_db_answers(), "allowlist": allowlist_state(), "private_db": {}, "vault_extra": visible_vault(),
              "forbidden_paths": [p for p in FORBIDDEN_PATHS if Path(p).exists()], "env_leaks": env_leaks(),
              "egress": egress(), "llm_channel": llm_channel(), "fetch_channel": fetch_channel()}
    for host, port in _targets():
        result["private_db"][f"{host}:{port}"] = reachable(host, port)
    ok = (result["lab_db"] == "ok" and result["allowlist"].startswith("ok:")
          and all(v != "open" for v in result["private_db"].values())
          and all(v != "open" for v in result["egress"].values())
          and llm_channel_ok(result["llm_channel"]) and fetch_channel_ok(result["fetch_channel"])
          and not result["vault_extra"] and not result["forbidden_paths"] and not result["env_leaks"])
    result["status"] = "pass" if ok else "FAIL"
    print(json.dumps(result), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
