# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for ``exocortex init`` (F31.8.4)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

import pytest

from exocortex.config_loader import USER_YAML_FILES, resolve_config_path
from exocortex.init_cmd import (
    _copy_example_yamls,
    _parse_env_file,
    _sanitize_answer,
    _validate_env,
    add_init_subparser,
    cmd_init,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Lay out a minimal fake repo: just config/ with all *.example.yaml + .env.example."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    # Use the real example files so we exercise the actual templates.
    real_cfg = Path(__file__).resolve().parent.parent.parent / "config"
    for filename in USER_YAML_FILES:
        stem, ext = filename.rsplit(".", 1)
        src = real_cfg / f"{stem}.example.{ext}"
        if src.exists():
            (cfg / f"{stem}.example.{ext}").write_bytes(src.read_bytes())
    env_example = real_cfg / ".env.example"
    if env_example.exists():
        (cfg / ".env.example").write_bytes(env_example.read_bytes())
    return tmp_path


def _capture_writer() -> tuple[list[str], Callable[[str], None]]:
    captured: list[str] = []

    def writer(line: str) -> None:
        captured.append(line)

    return captured, writer


def _make_ns(**overrides) -> argparse.Namespace:
    base = {"force": False, "non_interactive": True}
    base.update(overrides)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# Core init behaviour
# ---------------------------------------------------------------------------


def test_init_copies_all_example_yamls_to_real_filenames(fake_repo: Path) -> None:
    captured, writer = _capture_writer()
    rc = cmd_init(_make_ns(), repo_root=fake_repo, out=writer)
    assert rc == 0
    for filename in USER_YAML_FILES:
        target = fake_repo / "config" / filename
        # Only assert for those whose example exists in this repo (defensive).
        stem, ext = filename.rsplit(".", 1)
        example = fake_repo / "config" / f"{stem}.example.{ext}"
        if example.exists():
            assert target.exists(), f"{filename} should have been copied from example"
            # Content must match the example byte-for-byte (we want a true copy,
            # not a re-render that could drift from the template).
            assert target.read_bytes() == example.read_bytes()


def test_init_creates_env_file_at_repo_root(fake_repo: Path) -> None:
    _, writer = _capture_writer()
    rc = cmd_init(_make_ns(), repo_root=fake_repo, out=writer)
    assert rc == 0
    env_path = fake_repo / ".env"
    assert env_path.exists()
    # .env lives at repo root, NOT inside config/
    assert not (fake_repo / "config" / ".env").exists()


def test_init_is_idempotent_no_force(fake_repo: Path) -> None:
    """Second invocation must not touch files that already exist."""
    _, writer = _capture_writer()
    cmd_init(_make_ns(), repo_root=fake_repo, out=writer)

    # Tamper with a generated yaml so we can detect overwrites.
    sentinel = fake_repo / "config" / "projects.yaml"
    sentinel.write_text("# operator-edited content — must not be touched", encoding="utf-8")
    env_path = fake_repo / ".env"
    env_path.write_text("# operator's customised .env", encoding="utf-8")

    captured, writer2 = _capture_writer()
    rc = cmd_init(_make_ns(), repo_root=fake_repo, out=writer2)
    assert rc == 0
    assert sentinel.read_text(encoding="utf-8") == "# operator-edited content — must not be touched"
    assert env_path.read_text(encoding="utf-8") == "# operator's customised .env"
    # The summary should communicate that nothing was created.
    summary = "\n".join(captured)
    assert "already present" in summary or "left untouched" in summary


def test_init_force_overwrites_existing_files(fake_repo: Path) -> None:
    _, writer = _capture_writer()
    cmd_init(_make_ns(), repo_root=fake_repo, out=writer)

    sentinel = fake_repo / "config" / "projects.yaml"
    sentinel.write_text("# tampered", encoding="utf-8")

    _, writer2 = _capture_writer()
    rc = cmd_init(_make_ns(force=True), repo_root=fake_repo, out=writer2)
    assert rc == 0
    assert sentinel.read_text(encoding="utf-8") != "# tampered"


def test_init_aborts_when_config_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-F31.8.5 ``init`` would abort when ``repo_root/config/`` was missing.

    Post-F31.8.5 it falls back to ``exocortex/_bundled/config/`` (the wheel
    bundle), so the only way to actually hit the abort path is when *both*
    sources are missing. We blank out the bundled-source resolver to simulate
    a broken install.
    """
    import exocortex.init_cmd as init_mod

    monkeypatch.setattr(init_mod, "_bundled_config_dir", lambda: tmp_path / "does-not-exist")
    _, writer = _capture_writer()
    rc = cmd_init(_make_ns(), repo_root=tmp_path, out=writer)
    assert rc == 2


# ---------------------------------------------------------------------------
# Prompt / non-interactive behaviour
# ---------------------------------------------------------------------------


def test_init_interactive_prompts_substitute_values(fake_repo: Path) -> None:
    answers = iter(["/path/to/vault", "postgresql://u:p@h/db"])

    def fake_reader(_: str) -> str:
        return next(answers)

    _, writer = _capture_writer()
    rc = cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=fake_reader,
        out=writer,
    )
    assert rc == 0
    env_text = (fake_repo / ".env").read_text(encoding="utf-8")
    assert "EXOCORTEX_VAULT_PATH=/path/to/vault" in env_text
    assert "DATABASE_URL=postgresql://u:p@h/db" in env_text


def test_init_non_interactive_leaves_required_blank(fake_repo: Path) -> None:
    _, writer = _capture_writer()
    cmd_init(_make_ns(non_interactive=True), repo_root=fake_repo, out=writer)
    env_text = (fake_repo / ".env").read_text(encoding="utf-8")
    # Both required keys must still be blank — operator chose --non-interactive.
    for line in env_text.splitlines():
        if line.startswith("EXOCORTEX_VAULT_PATH="):
            assert line == "EXOCORTEX_VAULT_PATH="
        if line.startswith("DATABASE_URL="):
            assert line == "DATABASE_URL="


def test_init_prompt_empty_answer_keeps_key_blank(fake_repo: Path) -> None:
    """Pressing Enter on a prompt must leave the example default in place."""
    answers = iter(["", ""])

    def fake_reader(_: str) -> str:
        return next(answers)

    _, writer = _capture_writer()
    cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=fake_reader,
        out=writer,
    )
    env_text = (fake_repo / ".env").read_text(encoding="utf-8")
    assert "EXOCORTEX_VAULT_PATH=" in env_text
    assert "DATABASE_URL=" in env_text


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def test_parse_env_file_handles_comments_and_blanks(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "FOO=bar",
                "  BAZ = qux  ",  # whitespace around key/value
                "# COMMENTED=value",
                "EMPTY=",
            ]
        ),
        encoding="utf-8",
    )
    parsed = _parse_env_file(env)
    assert parsed == {"FOO": "bar", "BAZ": "qux", "EMPTY": ""}


def test_validate_env_flags_blank_required_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXOCORTEX_VAULT_PATH=\nDATABASE_URL=\n", encoding="utf-8")
    captured, writer = _capture_writer()
    ok = _validate_env(env, writer)
    assert ok is False
    summary = "\n".join(captured)
    assert "EXOCORTEX_VAULT_PATH" in summary
    assert "DATABASE_URL" in summary


def test_validate_env_passes_when_required_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "EXOCORTEX_VAULT_PATH=/tmp/v\nDATABASE_URL=postgresql://x\n", encoding="utf-8"
    )
    captured, writer = _capture_writer()
    ok = _validate_env(env, writer)
    assert ok is True
    assert any("look set" in line for line in captured)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_add_init_subparser_registers_command() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_init_subparser(sub)
    args = parser.parse_args(["init", "--non-interactive", "--force"])
    assert args.command == "init"
    assert args.non_interactive is True
    assert args.force is True
    assert callable(args.func)


def test_cli_main_dispatches_to_init(fake_repo: Path, monkeypatch) -> None:
    """End-to-end: ``exocortex init`` via the real argparse dispatcher."""
    from exocortex import cli, init_cmd as init_module

    # Pin the init implementation to operate on the fake repo and skip prompts.
    real_cmd_init = init_module.cmd_init

    def patched_cmd_init(args, *, repo_root=None, reader=input, out=None, env=None):
        return real_cmd_init(args, repo_root=fake_repo, reader=reader, out=out, env=env)

    monkeypatch.setattr(init_module, "cmd_init", patched_cmd_init)

    rc = cli.main(["init", "--non-interactive"])
    assert rc == 0
    assert (fake_repo / ".env").exists()


# ---------------------------------------------------------------------------
# Env-based non-interactive detection (CI=1 / EXOCORTEX_NO_INPUT=1)
# ---------------------------------------------------------------------------


def _exploding_reader(_prompt: str) -> str:
    raise AssertionError("reader() must not be called in non-interactive mode")


def test_init_skips_prompts_when_ci_env_is_truthy(fake_repo: Path) -> None:
    """``CI=1`` (GitHub Actions et al.) auto-enables --non-interactive."""
    captured, writer = _capture_writer()
    rc = cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=_exploding_reader,
        out=writer,
        env={"CI": "1"},
    )
    assert rc == 0
    assert (fake_repo / ".env").exists()
    joined = "\n".join(captured)
    assert "CI=" in joined and "non-interactively" in joined


def test_init_skips_prompts_when_exocortex_no_input_set(fake_repo: Path) -> None:
    """Explicit ``EXOCORTEX_NO_INPUT=1`` for unattended local runs."""
    captured, writer = _capture_writer()
    rc = cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=_exploding_reader,
        out=writer,
        env={"EXOCORTEX_NO_INPUT": "true"},
    )
    assert rc == 0
    assert (fake_repo / ".env").exists()
    assert any("EXOCORTEX_NO_INPUT" in line for line in captured)


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "  "])
def test_init_treats_falsy_ci_values_as_interactive(fake_repo: Path, falsy: str) -> None:
    """``CI=0`` / ``CI=false`` must not force non-interactive mode.

    We pass a reader that returns empty strings so the prompt path runs to
    completion without blocking on real stdin.
    """
    captured, writer = _capture_writer()
    rc = cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=lambda _prompt: "",
        out=writer,
        env={"CI": falsy},
    )
    assert rc == 0
    # The "running non-interactively" banner must NOT appear.
    assert not any("non-interactively" in line for line in captured), captured


# ---------------------------------------------------------------------------
# Post-review hardening: .env perms, newline-injection guard, broken checkout
# ---------------------------------------------------------------------------


def test_env_file_written_with_0600_perms(fake_repo: Path) -> None:
    """`.env` carries secrets — must be owner-only readable."""

    _, writer = _capture_writer()
    rc = cmd_init(_make_ns(non_interactive=True), repo_root=fake_repo, out=writer)
    assert rc == 0
    env_path = fake_repo / ".env"
    mode = env_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600 perms on .env, got {oct(mode)}"
    # And the banner must surface the chmod so operators see it in logs.
    # (write_env_file appends "[mode 600]" to the creation line.)
    captured, _ = _capture_writer()
    # re-run with force to capture fresh output
    cmd_init(_make_ns(non_interactive=True, force=True), repo_root=fake_repo, out=captured.append)
    assert any("mode 600" in line for line in captured), captured


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/path/to/vault", "/path/to/vault"),
        ("  /padded  ", "/padded"),
        ("/path\nEVIL=injected", "/pathEVIL=injected"),
        ("/path\r\nALSO_EVIL=x", "/pathALSO_EVIL=x"),
        ("postgresql://u:p@h/db\n", "postgresql://u:p@h/db"),
    ],
)
def test_sanitize_answer_strips_newlines(raw: str, expected: str) -> None:
    assert _sanitize_answer(raw) == expected


def test_init_prompt_strips_embedded_newline_so_no_env_var_injection(
    fake_repo: Path,
) -> None:
    """A malicious prompt answer must not split into two env lines."""
    # Two answers: first injects \n + EVIL key, second is benign.
    answers = iter(["/tmp/vault\nEVIL_KEY=pwned", "postgresql://u:p@h/db"])

    def evil_reader(_: str) -> str:
        return next(answers)

    _, writer = _capture_writer()
    rc = cmd_init(
        _make_ns(non_interactive=False),
        repo_root=fake_repo,
        reader=evil_reader,
        out=writer,
    )
    assert rc == 0
    env_text = (fake_repo / ".env").read_text(encoding="utf-8")
    # The line must contain the sanitised value (no newline inside);
    # and EVIL_KEY must NOT appear as its own line.
    assert "EXOCORTEX_VAULT_PATH=/tmp/vaultEVIL_KEY=pwned" in env_text
    assert not any(
        line.startswith("EVIL_KEY=") for line in env_text.splitlines()
    ), env_text


def test_copy_example_yamls_separates_already_present_from_missing(
    fake_repo: Path,
) -> None:
    """C3: 'already present' must not silently absorb 'example missing' cases."""
    cfg = fake_repo / "config"
    # Delete one .example.yaml to simulate corrupt checkout.
    victim_stem = "projects"
    (cfg / f"{victim_stem}.example.yaml").unlink()

    captured, writer = _capture_writer()
    created, already_present, missing = _copy_example_yamls(
        cfg, force=False, out=writer,
    )
    # projects.yaml has neither real nor example → reported as missing.
    assert "projects.yaml" in missing
    assert "projects.yaml" not in already_present
    assert "projects.yaml" not in created
    # The other USER_YAML_FILES with examples were copied (created), not missing.
    for filename in USER_YAML_FILES:
        if filename == "projects.yaml":
            continue
        assert filename in created, f"{filename} should have been created"


def test_init_warns_about_missing_examples_in_summary(fake_repo: Path) -> None:
    """C3 end-to-end: cmd_init prints a 'checkout looks corrupt' warning."""
    (fake_repo / "config" / "projects.example.yaml").unlink()

    captured, writer = _capture_writer()
    rc = cmd_init(_make_ns(non_interactive=True), repo_root=fake_repo, out=writer)
    # Init still exits 0 — we don't block on broken checkout (the operator
    # might want to fix it post-hoc), we just have to be loud about it.
    assert rc == 0
    summary = "\n".join(captured)
    assert "checkout looks corrupt" in summary
    assert "projects.yaml" in summary


def test_resolve_config_path_rejects_path_traversal(tmp_path: Path) -> None:
    """W1: refuse separators in the bare-name argument."""
    for bad in ("../etc/passwd", "/etc/passwd", "sub/file.yaml", "", "..\\file"):
        with pytest.raises(ValueError, match="bare filename"):
            resolve_config_path(bad, config_dir=tmp_path)


def test_resolve_config_path_accepts_plain_filename(tmp_path: Path) -> None:
    """W1 negative case: legitimate bare names still work."""
    (tmp_path / "foo.yaml").write_text("ok\n")
    result = resolve_config_path("foo.yaml", config_dir=tmp_path)
    assert result == (tmp_path / "foo.yaml").resolve()


def test_init_partial_state_only_creates_missing_yamls(fake_repo: Path) -> None:
    """W4: with 3 of 7 user yamls already on disk, init copies the other 4."""
    cfg = fake_repo / "config"
    # Pre-create 3 user yamls with sentinel content; we'll check they survive.
    pre_existing = ("projects.yaml", "sources.yaml", "graph_rag.yaml")
    sentinel = "# operator-edited — do not overwrite\n"
    for name in pre_existing:
        (cfg / name).write_text(sentinel, encoding="utf-8")

    _, writer = _capture_writer()
    rc = cmd_init(_make_ns(non_interactive=True), repo_root=fake_repo, out=writer)
    assert rc == 0

    # Sentinels untouched.
    for name in pre_existing:
        assert (cfg / name).read_text(encoding="utf-8") == sentinel

    # The other 4 yamls were created from their examples.
    expected_created = set(USER_YAML_FILES) - set(pre_existing)
    for name in expected_created:
        stem, ext = name.rsplit(".", 1)
        example = cfg / f"{stem}.example.{ext}"
        target = cfg / name
        assert target.exists(), f"{name} should have been created"
        if example.exists():
            assert target.read_bytes() == example.read_bytes(), (
                f"{name} content must match example after a fresh copy"
            )
