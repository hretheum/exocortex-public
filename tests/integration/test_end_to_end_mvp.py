# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.9.5 — full MVP loop smoke test.

Exercises the gating contract of Exocortex: on a freshly migrated database
we can ingest a real fixture, run the synthesizer, compile the wiki and
answer a GraphRAG question with citations.

Two ways to run it:
  - CI, on every push: against ``tests/fakes/fake_llm_server.py`` (no API
    key; checks the data path, not answer quality);
  - nightly on the self-hosted server (``deploy/e2e``): against a real local model.
Both select ``config/llm_routing.selfhosted.yaml`` via EXOCORTEX_LLM_ROUTING and
send embeddings to the same server via OPENAI_BASE_URL.

The test is intentionally permissive on intermediate counts (e.g. "at least
N thoughts") and strict only on the *behavioural* contract — the engine
produces an answer that names the right note.  Tightening the asserts later
is cheap; loosening them after a regression hides bugs.

Skipped automatically when no DB is reachable; see ``conftest.py``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ACME_NOTES = REPO_ROOT / "examples" / "acme-corp" / "notes"
EXPECTED_NOTE_SLUG = "2026-05-01-acme-margin-review"
# 5 min per F31.9.5 AC. A slower local model (nightly run on the self-hosted server)
# raises it with E2E_BUDGET_SECONDS and stretches the per-step subprocess
# timeouts with E2E_TIMEOUT_SCALE.
SMOKE_BUDGET_SECONDS = int(os.environ.get("E2E_BUDGET_SECONDS", "300"))
TIMEOUT_SCALE = float(os.environ.get("E2E_TIMEOUT_SCALE", "1"))


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
        check=False,  # the caller's own `check` flag below decides
        timeout=int(timeout * TIMEOUT_SCALE),
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
    return query_one(sql, *params)


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
    # The meeting-note ingester reads <vault>/_source/work/meeting-notes/*.md.
    notes_dir = root / "_source" / "work" / "meeting-notes"
    notes_dir.mkdir(parents=True)
    for note in sorted(ACME_NOTES.rglob("*.md")):
        shutil.copy(note, notes_dir / note.name)
    return root


@pytest.fixture(scope="module")
def smoke_env(vault_root: Path):
    """Env shared by every CLI invocation in this module.

    Also exported into this process, because the in-process DB checks load
    ``exocortex.settings`` too; the previous values are restored afterwards.
    """
    env = {
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
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    yield env
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# the test
# ---------------------------------------------------------------------------


def test_full_mvp_loop(vault_root: Path, smoke_env: dict[str, str]) -> None:
    """Gating contract for v0.1.0: ingest → synth → compile → query."""
    started = time.monotonic()

    # ── 1. migrate ─────────────────────────────────────────────────────────
    _run([sys.executable, "-m", "exocortex.cli", "migrate", "up"], env=smoke_env)

    # ── 2. ingest the acme-corp notes ────────────────────────────────────
    # NB: bulk_ingest_vault.py reads VAULT_PATH from env, hence smoke_env above.
    _run(
        [sys.executable, "-m", "exocortex.cli", "ingest", "--from", str(vault_root)],
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

    # ── 3. synthesize the "acme" tag perspective (every fixture note carries
    #       the tag in front matter, so discovery does not depend on the LLM) ─
    _run(
        [sys.executable, "-m", "exocortex.cli", "synth",
         "--perspective", "tag", "--key", "acme"],
        env=smoke_env,
        timeout=240,
    )
    n_syn = _query_one(
        "SELECT count(*) AS n FROM syntheses "
        "WHERE tenant_id = %s AND superseded_by IS NULL",
        (smoke_env["TENANT_ID"],),
    )
    assert n_syn and n_syn["n"] >= 1, (
        "expected ≥1 active synthesis after running the tag:acme perspective"
    )

    # ── 4. compile the work wiki (meeting notes + the synthesis above) ─────
    _run(
        [sys.executable, "-m", "exocortex.cli", "compile", "--domain", "work"],
        env=smoke_env,
        timeout=120,
    )
    n_md = _count_md_files(vault_root / "wiki")
    assert n_md >= 3, (
        f"expected ≥3 .md files under wiki/ after compile, got {n_md}"
    )

    # ── 5. ad-hoc GraphRAG query ───────────────────────────────────────────
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
    # The answer is requested in Polish, so a real model may say "marża".
    assert "margin" in response or "marż" in response, (
        f"expected 'margin'/'marża' in the answer body, got: {response[:200]!r}"
    )

    # ── 6. budget guard ────────────────────────────────────────────────────
    elapsed = time.monotonic() - started
    assert elapsed < SMOKE_BUDGET_SECONDS, (
        f"smoke loop took {elapsed:.0f}s — over the {SMOKE_BUDGET_SECONDS}s budget"
    )
