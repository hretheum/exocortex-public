# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F32 — proves vault_watcher.py works UNCHANGED after the capture_api.py
lifecycle additions (Standard Przeglądu pkt 8, docs/deployment: obsidian
plugin task). Runs a REAL uvicorn server in a background thread — not the
ASGI TestClient — because vault_watcher.post_capture() makes a genuine
urllib.request.urlopen() call to CAPTURE_API_URL; only a real socket proves
the actual code path a real watcher process would take.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('PG_USER', 'exocortex')}:"
    f"{os.environ.get('PG_PASSWORD', 'exocortex')}@"
    f"{os.environ.get('PG_HOST', 'localhost')}:"
    f"{os.environ.get('PG_PORT', '5432')}/"
    f"{os.environ.get('PG_DATABASE', 'exocortex')}",
)
os.environ.setdefault("EXOCORTEX_TENANT_ID", "11111111-1111-1111-1111-111111111111")
os.environ.setdefault("CAPTURE_API_TOKEN", "test-token-f32")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_capture_api():
    import uvicorn

    from exocortex import capture_api

    port = _free_port()
    config = uvicorn.Config(capture_api.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("uvicorn did not start in time")

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


def test_vault_watcher_process_file_unchanged_against_new_api(
    live_capture_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual regression proof: import the REAL vault_watcher module
    (no reimplementation), point it at the live server via its documented
    env vars, and run its REAL process_file() against a REAL temp vault."""
    monkeypatch.setenv("CAPTURE_API_URL", live_capture_api)
    monkeypatch.setenv("CAPTURE_API_TOKEN", os.environ["CAPTURE_API_TOKEN"])
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))

    from exocortex.settings import reset_settings

    reset_settings()  # settings.get_settings() is a module-level singleton —
    # without clearing it, VAULT_PATH stays whatever an earlier test in the
    # same pytest process already cached, regardless of the env var above.

    import importlib

    from exocortex import vault_watcher

    importlib.reload(vault_watcher)  # picks up VAULT_PATH from the patched env

    note = tmp_path / "example.md"
    note.write_text(
        "---\ntitle: F32 compat check\nsource_type: quick-note\n---\n"
        "Body content unaffected by the new lifecycle endpoints.\n",
        encoding="utf-8",
    )

    rule = {"path": ".", "source_type": "quick-note"}
    result = vault_watcher.process_file(note, rule, default_source_type="quick-note")

    assert result["status"] == "created", result
    assert result["source_id"], result
    assert result["source_type"] == "quick-note"

    # Second run of the SAME file: server-side idempotency (ON CONFLICT DO
    # NOTHING, untouched by F32) still gives "unchanged", exactly as before —
    # force=True bypasses the watcher's own in-memory hash cache so this
    # actually re-hits the server instead of short-circuiting locally.
    result2 = vault_watcher.process_file(
        note, rule, default_source_type="quick-note", force=True
    )
    assert result2["status"] == "unchanged", result2
    assert result2["source_id"] == result["source_id"]
