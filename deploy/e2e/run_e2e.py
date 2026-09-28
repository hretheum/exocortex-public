# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Entry point of the e2e image: run the end-to-end smoke test once.

Exit code is pytest's. On failure, and when TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID are set, the tail of the output goes to Telegram.
Extra arguments are passed to pytest.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

TEST = "tests/integration/test_end_to_end_mvp.py"
TAIL_LINES = 25


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return None if value.lower() in ("", "none", "unset") else value


def notify(text: str) -> None:
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    body = json.dumps({"chat_id": chat, "text": text[:3900]}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as exc:  # noqa: BLE001 — a failed alert must not hide the result
        print(f"e2e: telegram notification failed: {exc}", file=sys.stderr)


def main(argv: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=",
           "-v", "--color=no", TEST, *argv]
    started = time.monotonic()
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          check=False)
    elapsed = time.monotonic() - started
    sys.stdout.write(proc.stdout)
    status = "passed" if proc.returncode == 0 else f"FAILED (rc={proc.returncode})"
    print(f"e2e: {status} in {elapsed:.0f}s", flush=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.strip().splitlines()[-TAIL_LINES:])
        notify(f"Exocortex nightly e2e {status} after {elapsed:.0f}s\n\n{tail}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
