# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.9.5 — full MVP loop smoke test.

Exercises the gating contract of Exocortex v0.1.0: on a freshly migrated
database we can ingest a real fixture, run the synthesizer, compile the
wiki and answer a GraphRAG question with citations.  CI runs this on every
PR; failure = merge blocked.

The test is intentionally permissive on intermediate counts (e.g. "at least
N thoughts") and strict only on the *behavioural* contract — the engine
produces an answer that names the right note.  Tightening the asserts later
is cheap; loosening them after a regression hides bugs.

Skipped automatically when no DB is reachable; see ``conftest.py``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ACME_NOTES = REPO_ROOT / "examples" / "acme-corp" / "notes"
EXPECTED_NOTE_SLUG = "2026-05-01-acme-margin-review"
SMOKE_BUDGET_SECONDS = 300  # 5 min, per F31.9.5 AC


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, env: dict[str, str] | None = None,
         cwd: Path | None = None, check: bool = True,
         timeout: int = 180) -> subprocess.CompletedProcess:
    """Run a subprocess and stream stdout+stderr for CI log readability."""
    merged_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        cmd,
        env=merged_env,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed (rc={proc.returncode}): {' '.join(cmd)}"
        )
    return proc


def _query_one(sql: str, params: tuple = ()) -> dict | None:
    from exocortex.db import query_one
    return query_one(sql, params)


def _count_md_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("*.md"))


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vault_root(tmp_path_factory) -> Path:
    """Fresh vault for the run — wiki output lands under <vault>/wiki/."""
    root = tmp_path_factory.mktemp("exocortex-smoke-vault")
    (root / "wiki").mkdir()
    return root


@pytest.fixture(scope="module")
def smoke_env(vault_root: Path) -> dict[str, str]:
    """Env shared by every CLI invocation in this module."""
    return {
        "VAULT_PATH": str(vault_root),
        "SECOND_BRAIN_VAULT_PATH": str(vault_root),
        "WIKI_OUTPUT_PATH": str(vault_root / "wiki"),
        "EXOCORTEX_VAULT_PATH": str(vault_root),
        # Force deterministic single-tenant runs on the smoke DB.
        "TENANT_ID": os.environ.get(
            "TENANT_ID", "00000000-0000-0000-0000-000000000001"
        ),
        # The capture API doesn't run during the smoke; ingest writes
        # directly to PG, but VARIOUS modules still read this var.
        "CAPTURE_API_TOKEN": "smoke-token",
    }


# ---------------------------------------------------------------------------
# the test
# ---------------------------------------------------------------------------


def test_full_mvp_loop(vault_root: Path, smoke_env: dict[str, str]) -> None:
    """Gating contract for v0.1.0: ingest → synth → compile → query."""
    started = time.monotonic()

    # ── 1. migrate ─────────────────────────────────────────────────────────
    _run([sys.executable, "-m", "exocortex.cli", "migrate", "up"], env=smoke_env)

    # ── 2. install acme plugin (idempotent: pip is happy with a re-install) ─
    plugin_dir = REPO_ROOT / "examples" / "acme-corp" / "plugin"
    _run(
        [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(plugin_dir)],
        env=smoke_env,
        timeout=240,
    )

    # ── 3. ingest the 7 acme-corp notes ────────────────────────────────────
    # NB: bulk_ingest_vault.py reads VAULT_PATH from env, hence smoke_env above.
    _run(
        [sys.executable, "-m", "exocortex.cli", "ingest", "--from", str(ACME_NOTES)],
        env=smoke_env,
        timeout=240,
    )
    n_thoughts = _query_one(
        "SELECT count(*) AS n FROM thoughts WHERE tenant_id = %s",
        (smoke_env["TENANT_ID"],),
    )
    assert n_thoughts and n_thoughts["n"] >= 5, (
        f"expected ≥5 thoughts after ingesting {ACME_NOTES}, got {n_thoughts}"
    )

    # ── 4. synthesize (acme perspective registered by the plugin) ──────────
    _run(
        [sys.executable, "-m", "exocortex.cli", "synth",
         "--perspective", "acme_client_review", "--limit", "3"],
        env=smoke_env,
        timeout=240,
    )
    n_syn = _query_one(
        "SELECT count(*) AS n FROM syntheses "
        "WHERE tenant_id = %s AND superseded_by IS NULL",
        (smoke_env["TENANT_ID"],),
    )
    assert n_syn and n_syn["n"] >= 1, (
        "expected ≥1 active synthesis after running acme_client_review perspective"
    )

    # ── 5. compile wiki for the acme domain ────────────────────────────────
    _run(
        [sys.executable, "-m", "exocortex.cli", "compile", "--domain", "acme"],
        env=smoke_env,
        timeout=120,
    )
    n_md = _count_md_files(vault_root / "wiki" / "acme")
    assert n_md >= 3, (
        f"expected ≥3 .md files under wiki/acme/ after compile, got {n_md}"
    )

    # ── 6. ad-hoc GraphRAG query ───────────────────────────────────────────
    query_proc = _run(
        [sys.executable, "-m", "exocortex.cli", "query", "--json",
         "what does ACME say about Q3 margin pressure"],
        env=smoke_env,
        timeout=120,
    )
    import json
    payload = json.loads(query_proc.stdout.split("\n", 1)[-1] if not query_proc.stdout.lstrip().startswith("{") else query_proc.stdout)
    response = (payload.get("response") or "").lower()
    sources = payload.get("sources") or []

    assert sources, "expected ≥1 citation from GraphRAG query"
    titles_blob = " ".join(
        f"{s.get('title') or ''} {s.get('thought_id') or ''}" for s in sources
    ).lower()
    assert EXPECTED_NOTE_SLUG in titles_blob or any(
        "margin" in (s.get("title") or "").lower() for s in sources
    ), (
        f"expected '{EXPECTED_NOTE_SLUG}' (or a margin-titled source) in "
        f"citations, got: {[s.get('title') for s in sources]}"
    )
    assert "margin" in response, (
        f"expected 'margin' in the answer body, got: {response[:200]!r}"
    )

    # ── 7. budget guard ────────────────────────────────────────────────────
    elapsed = time.monotonic() - started
    assert elapsed < SMOKE_BUDGET_SECONDS, (
        f"smoke loop took {elapsed:.0f}s — over the {SMOKE_BUDGET_SECONDS}s budget"
    )
