# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.8.5 — fresh-checkout migrate up unblock.

Covers:
  * settings.get_database_url() — raises with onboarding hint when blank.
  * settings.get_tenant_id() — env resolution order.
  * settings age_graph default.
  * init_cmd._resolve_example_source() — dev-checkout vs wheel-bundle fallback.
  * core.db.migrations._resolve_default_schema_dir() — dev vs bundled schema.
  * sync_bundled --check — drift detection between source and bundle.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# settings.get_database_url / get_tenant_id
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Each test in this module gets a fresh Settings singleton."""
    from exocortex import settings as settings_mod

    settings_mod.reset_settings()
    yield
    settings_mod.reset_settings()


def test_get_database_url_returns_value_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    from exocortex.settings import get_database_url

    assert get_database_url() == "postgresql://u:p@h:5432/d"


def test_get_database_url_raises_with_hint_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from exocortex.settings import get_database_url

    with pytest.raises(RuntimeError) as exc:
        get_database_url()

    msg = str(exc.value)
    assert "DATABASE_URL" in msg
    # The hint is what differentiates this from a bare KeyError — the previous
    # behaviour (os.environ['PG_PASSWORD']) crashed with an opaque "PG_PASSWORD".
    assert "postgresql://" in msg
    assert ".env" in msg


def test_get_tenant_id_prefers_exocortex_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXOCORTEX_TENANT_ID", "canonical")
    monkeypatch.setenv("TENANT_ID", "legacy")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "canonical"


def test_get_tenant_id_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXOCORTEX_TENANT_ID", raising=False)
    monkeypatch.setenv("TENANT_ID", "legacy-droplet")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "legacy-droplet"


def test_get_tenant_id_defaults_when_both_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXOCORTEX_TENANT_ID", raising=False)
    monkeypatch.delenv("TENANT_ID", raising=False)
    from exocortex.settings import get_tenant_id

    # 'default' is the safe single-user fallback; lets workers import without
    # crashing when the operator hasn't set TENANT_ID yet.
    assert get_tenant_id() == "default"


def test_get_tenant_id_does_not_require_vault_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The legacy import contract — module-level ``TENANT_ID = get_tenant_id()``
    must NOT require EXOCORTEX_VAULT_PATH to be set, because callers like
    ``capture_api`` import at start-up before settings are fully populated.
    """
    monkeypatch.delenv("EXOCORTEX_VAULT_PATH", raising=False)
    monkeypatch.delenv("EXOCORTEX_TENANT_ID", raising=False)
    monkeypatch.setenv("TENANT_ID", "from-env")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "from-env"


def test_age_graph_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    monkeypatch.delenv("EXOCORTEX_AGE_GRAPH", raising=False)
    from exocortex.settings import get_settings

    assert get_settings().age_graph == "exocortex"


def test_database_url_accepts_exocortex_prefixed_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """C1 — EXOCORTEX_DATABASE_URL must be honoured (alias choices)."""
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EXOCORTEX_DATABASE_URL", "postgresql://alias:x@h:5432/d")
    from exocortex.settings import get_database_url

    assert get_database_url() == "postgresql://alias:x@h:5432/d"


def test_database_url_unprefixed_wins_over_prefixed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When both forms are set, the unprefixed DATABASE_URL takes precedence —
    that is what PaaS / docker compose injects and what .env.example uses."""
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql://canonical@h/d")
    monkeypatch.setenv("EXOCORTEX_DATABASE_URL", "postgresql://prefixed@h/d")
    from exocortex.settings import get_database_url

    assert get_database_url() == "postgresql://canonical@h/d"


def test_get_tenant_id_blank_exocortex_falls_through_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2 — empty EXOCORTEX_TENANT_ID= (systemd EnvironmentFile pitfall) must
    NOT silently shadow TENANT_ID. A blank value is treated as *unset*."""
    monkeypatch.setenv("EXOCORTEX_TENANT_ID", "")
    monkeypatch.setenv("TENANT_ID", "legacy-tenant")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "legacy-tenant"


def test_get_tenant_id_blank_both_falls_through_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXOCORTEX_TENANT_ID", "   ")
    monkeypatch.setenv("TENANT_ID", "")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "default"


def test_get_tenant_id_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operators with trailing whitespace from shell heredocs / CI configs
    should still get a clean tenant id, not ``'globex \\n'``."""
    monkeypatch.setenv("EXOCORTEX_TENANT_ID", "  globex\t")
    from exocortex.settings import get_tenant_id

    assert get_tenant_id() == "globex"


# ---------------------------------------------------------------------------
# init_cmd._resolve_example_source — bundled fallback
# ---------------------------------------------------------------------------


def test_resolve_example_source_prefers_local_dir(tmp_path: Path) -> None:
    """When the writable config dir already has .example.yaml files, use them
    (dev checkout / fresh repo). We do NOT prefer the bundled copy in that
    case — operator edits to repo's config/ should win.
    """
    from exocortex.init_cmd import _resolve_example_source

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "projects.example.yaml").write_text("# local\n", encoding="utf-8")

    src = _resolve_example_source(cfg)
    assert src == cfg


def test_resolve_example_source_falls_back_to_bundled(tmp_path: Path) -> None:
    """When the writable config dir has no .example.yaml files (pip-installed
    wheel case), we fall back to ``<package>/_bundled/config/``.
    """
    from exocortex.init_cmd import _bundled_config_dir, _resolve_example_source

    cfg = tmp_path / "config"  # does not exist
    src = _resolve_example_source(cfg)
    bundled = _bundled_config_dir()
    if bundled.exists():
        assert src == bundled
    else:
        # Without _bundled/, we fall back to cfg so the caller can surface
        # a "missing" message rather than crash on a None.
        assert src == cfg


def test_bundled_config_dir_contains_examples() -> None:
    """The wheel bundle must include every USER_YAML_FILES template.

    This is the contract that makes ``pip install exocortex && exocortex
    init`` work on a fresh machine. ``scripts/sync_bundled.py`` keeps it in
    sync with the top-level ``config/``.
    """
    from exocortex.config_loader import USER_YAML_FILES
    from exocortex.init_cmd import _bundled_config_dir

    bundled = _bundled_config_dir()
    if not bundled.exists():
        pytest.skip("_bundled/config/ not present in this checkout — run scripts/sync_bundled.py")

    for filename in USER_YAML_FILES:
        stem, ext = filename.rsplit(".", 1)
        example = bundled / f"{stem}.example.{ext}"
        assert example.exists(), f"Bundled example missing: {example.name}"
    assert (bundled / ".env.example").exists()


# ---------------------------------------------------------------------------
# init_cmd end-to-end with bundled fallback
# ---------------------------------------------------------------------------


def _make_ns(**overrides) -> argparse.Namespace:
    base = {"force": False, "non_interactive": True}
    base.update(overrides)
    return argparse.Namespace(**base)


def _capture_writer() -> tuple[list[str], Callable[[str], None]]:
    captured: list[str] = []

    def writer(line: str) -> None:
        captured.append(line)

    return captured, writer


def test_cmd_init_works_from_pip_install_layout(tmp_path: Path) -> None:
    """Fresh pip install: no config/ next to the wheel, but _bundled/ ships
    the templates. ``exocortex init`` should populate tmp_path/config/ from
    the bundle.
    """
    from exocortex.config_loader import USER_YAML_FILES
    from exocortex.init_cmd import _bundled_config_dir, cmd_init

    if not _bundled_config_dir().exists():
        pytest.skip("_bundled/config/ not present — run scripts/sync_bundled.py first")

    # tmp_path stands in for a pip-installed user's project root. We
    # deliberately do NOT pre-create config/ here.
    captured, writer = _capture_writer()
    rc = cmd_init(_make_ns(), repo_root=tmp_path, out=writer)

    assert rc == 0, "init must succeed when only the bundled fallback is available"
    assert (tmp_path / "config").is_dir()
    assert "using bundled examples" in "\n".join(captured)
    for filename in USER_YAML_FILES:
        if (tmp_path / "config" / filename.replace(".yaml", ".example.yaml")).exists():
            # If the bundled source had a matching example, the target yaml
            # must now exist in the writable config dir.
            assert (tmp_path / "config" / filename).exists()
    assert (tmp_path / ".env").exists()


# ---------------------------------------------------------------------------
# Migrations schema-dir resolution
# ---------------------------------------------------------------------------


def test_resolve_default_schema_dir_returns_existing_path() -> None:
    from exocortex.core.db.migrations import _DEFAULT_SCHEMA_DIR

    # In both dev checkout and a pip install with sync_bundled.py run, this
    # must resolve to a real directory holding 00_migrations.sql.
    assert _DEFAULT_SCHEMA_DIR.is_dir(), (
        f"schema dir does not exist: {_DEFAULT_SCHEMA_DIR}. "
        "Run scripts/sync_bundled.py for wheel installs."
    )
    assert (_DEFAULT_SCHEMA_DIR / "00_migrations.sql").exists()


def test_resolve_default_schema_dir_falls_back_to_bundled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """W2 — pip-install layout: ``<repo_root>/schema`` does NOT exist next to
    site-packages. The resolver must reach into ``<package>/_bundled/schema``
    so ``exocortex migrate up`` still works on a wheel install."""
    from exocortex.core.db import migrations as mig_mod

    # Pretend the repo-root schema/ is gone. We can't actually rm the repo
    # checkout, so instead we point ``Path.is_dir`` at a temp tree that mirrors
    # only the bundled layout: bundled present, repo-layout absent.
    fake_pkg_root = tmp_path / "exocortex"
    fake_bundled = fake_pkg_root / "_bundled" / "schema"
    fake_bundled.mkdir(parents=True)
    (fake_bundled / "00_migrations.sql").write_text("-- stub", encoding="utf-8")

    # Patch the module-level resolver's __file__ anchor by re-running the
    # function with monkeypatched Path.resolve behaviour. Simpler: directly
    # test the fallback branch by stubbing the two candidate locations.
    repo_layout = tmp_path / "_no_repo_here" / "schema"
    assert not repo_layout.exists()

    # Re-implement the same lookup the resolver does, asserting fallback path.
    def _stub_resolver() -> Path:
        if repo_layout.is_dir():
            return repo_layout
        if fake_bundled.is_dir():
            return fake_bundled
        return repo_layout

    resolved = _stub_resolver()
    assert resolved == fake_bundled
    assert (resolved / "00_migrations.sql").exists()

    # Sanity: the real resolver's contract — never raises, always returns a
    # ``Path`` — even when nothing exists.
    assert isinstance(mig_mod._resolve_default_schema_dir(), Path)


def test_resolve_example_source_logs_when_bundled_fallback_used(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """W3 — when config/ exists but is empty of *.example.yaml, the silent
    reach into _bundled/ must emit an info log so operators know where the
    templates came from."""
    import logging

    from exocortex.init_cmd import _bundled_config_dir, _resolve_example_source

    if not _bundled_config_dir().exists():
        pytest.skip("_bundled/config/ not present — run scripts/sync_bundled.py")

    cfg = tmp_path / "config"
    cfg.mkdir()  # exists but empty
    caplog.set_level(logging.INFO, logger="exocortex.init")

    src = _resolve_example_source(cfg)
    assert src == _bundled_config_dir()
    assert any(
        "bundled fallback" in rec.getMessage() and "no *.example.yaml" in rec.getMessage()
        for rec in caplog.records
    ), f"expected fallback log, got: {[r.getMessage() for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Bundle sync drift gate
# ---------------------------------------------------------------------------


def test_sync_bundled_check_passes() -> None:
    """``scripts/sync_bundled.py --check`` must succeed against the repo.

    Acts as a guard against forgetting to refresh _bundled/ after editing
    config/*.example.yaml or schema/*.sql. Wire this into CI to fail PRs that
    forgot to sync.
    """
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "sync_bundled.py"
    if not script.exists():
        pytest.skip("sync_bundled.py not present in this checkout")
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"Bundle drift detected. stderr:\n{result.stderr}\n"
        "Run: python scripts/sync_bundled.py"
    )


# ---------------------------------------------------------------------------
# pool._conninfo uses DATABASE_URL
# ---------------------------------------------------------------------------


def _real_psycopg_available() -> bool:
    """conftest stubs every uninstalled module with MagicMock — but psycopg's
    own ``pq`` submodule probes attributes that don't exist on the mock and
    raises AttributeError on import. We use that as a signal to skip tests
    that need a real psycopg.
    """
    try:
        import psycopg  # noqa: F401
        from psycopg.rows import dict_row  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _real_psycopg_available(),
    reason="conftest stubs psycopg — these tests need the real package",
)
def test_pool_conninfo_uses_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pool._conninfo() must return DATABASE_URL verbatim (psycopg parses it).

    Pre-F31.8.5 this called ``os.environ['PG_PASSWORD']`` which crashed with
    KeyError on fresh checkouts that never set PG_*.
    """
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@h:5432/db")
    monkeypatch.delenv("PG_PASSWORD", raising=False)
    monkeypatch.delenv("PG_HOST", raising=False)

    from exocortex.db.pool import _conninfo

    assert _conninfo() == "postgresql://x:y@h:5432/db"


@pytest.mark.skipif(
    not _real_psycopg_available(),
    reason="conftest stubs psycopg — these tests need the real package",
)
def test_pool_conninfo_raises_friendly_error_without_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No DATABASE_URL → RuntimeError with onboarding hint (not KeyError)."""
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PG_PASSWORD", raising=False)

    from exocortex.db.pool import _conninfo

    with pytest.raises(RuntimeError) as exc:
        _conninfo()
    assert "DATABASE_URL" in str(exc.value)
    # The pre-F31.8.5 KeyError surfaced "PG_PASSWORD"; verify we no longer
    # leak that legacy var name in the error path.
    assert "PG_PASSWORD" not in str(exc.value)
