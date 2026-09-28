# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Isolation check of the Exocortex lab (roadmap task F2.1).

Runs inside a lab container, with the lab's network, mounts and
environment. Passes only when:

1. the lab database answers (positive control: the check itself works);
2. none of the addresses in LAB_PRIVATE_DB_TARGETS accepts a TCP connection
   (the private database is out of reach, before any password is tried);
3. the only part of the vault visible is the published documents folder;
4. the environment points at the lab database only.

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


def _targets() -> list[tuple[str, int]]:
    raw = os.environ.get("LAB_PRIVATE_DB_TARGETS", "host.containers.internal:5432,169.254.1.2:5432")
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.rpartition(":")
        out.append((host, int(port)))
    return out


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


def main() -> int:
    result = {"lab_db": lab_db_answers(), "private_db": {}, "vault_extra": visible_vault(),
              "forbidden_paths": [p for p in FORBIDDEN_PATHS if Path(p).exists()], "env_leaks": env_leaks()}
    for host, port in _targets():
        result["private_db"][f"{host}:{port}"] = reachable(host, port)
    ok = (result["lab_db"] == "ok"
          and all(v != "open" for v in result["private_db"].values())
          and not result["vault_extra"] and not result["forbidden_paths"] and not result["env_leaks"])
    result["status"] = "pass" if ok else "FAIL"
    print(json.dumps(result), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
