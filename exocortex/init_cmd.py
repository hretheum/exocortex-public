# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Implementation of ``exocortex init``.

Bootstraps a fresh checkout into a runnable state by:

1. Copying ``config/<name>.example.yaml`` → ``config/<name>.yaml`` for every
   user-customisable config file that doesn't yet exist locally.
2. Copying ``config/.env.example`` → ``.env`` at the repo root if missing,
   optionally prompting the operator for the two required values
   (``EXOCORTEX_VAULT_PATH``, ``DATABASE_URL``).
3. Validating the resulting ``.env`` by loading ``Settings`` and reporting
   any missing required vars.

The command is idempotent: re-running it never overwrites a file that
already exists (unless ``--force`` is passed). It is also import-safe in
test contexts — ``yaml`` / ``pydantic-settings`` are only touched when the
relevant step actually runs.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from pathlib import Path
from typing import Callable, Mapping, Optional

from exocortex.config_loader import USER_YAML_FILES

logger = logging.getLogger("exocortex.init")

# Environment variables that force --non-interactive behaviour. CI=1 is the
# de-facto standard set by GitHub Actions/GitLab/CircleCI; EXOCORTEX_NO_INPUT
# is an explicit opt-out for operators running unattended outside CI.
_NON_INTERACTIVE_ENV_VARS: tuple[str, ...] = ("CI", "EXOCORTEX_NO_INPUT")


def _env_forces_non_interactive(env: Mapping[str, str]) -> Optional[str]:
    """Return the first env var whose value is truthy, else None."""
    for name in _NON_INTERACTIVE_ENV_VARS:
        value = env.get(name, "").strip().lower()
        if value and value not in {"0", "false", "no"}:
            return name
    return None

# Two required vars for which we prompt interactively when generating a fresh
# .env. Anything else stays as-shipped in the example (operator edits later).
_PROMPTED_VARS: tuple[tuple[str, str], ...] = (
    (
        "EXOCORTEX_VAULT_PATH",
        "Absolute path to your Obsidian vault (e.g. /Users/you/Documents/my-vault)",
    ),
    (
        "DATABASE_URL",
        "Postgres connection string (e.g. postgresql://user:pass@localhost:5432/exocortex)",
    ),
)


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _config_dir(repo_root: Path) -> Path:
    return repo_root / "config"


def _bundled_config_dir() -> Path:
    """Return the wheel-bundled ``config/`` copy.

    Operators who installed via ``pip install exocortex`` won't have a
    top-level ``config/`` directory next to the wheel — the package data ships
    under ``exocortex/_bundled/config/`` instead. We point ``init`` at this
    fallback when the repo-root layout is absent so the same command works
    for both dev checkouts and pip-installed wheels.
    """
    return Path(__file__).resolve().parent / "_bundled" / "config"


def _resolve_example_source(config_dir: Path) -> Path:
    """Pick the directory holding ``*.example.yaml`` + ``.env.example``.

    Order:
      1. ``config_dir`` (operator's writable config dir — usually CWD/config).
         If the operator already placed ``*.example.yaml`` here we use them.
      2. ``_bundled_config_dir()`` — the wheel-shipped fallback.
    """
    config_dir_present = config_dir.exists()
    has_examples_locally = (
        any(config_dir.glob("*.example.yaml")) if config_dir_present else False
    )
    if has_examples_locally:
        return config_dir
    bundled = _bundled_config_dir()
    if bundled.exists():
        if config_dir_present:
            # The operator created a ``config/`` dir but never populated it
            # with ``*.example.yaml`` (e.g. wiped it during cleanup). Surface
            # that we are silently reaching for the wheel-bundled fallback
            # so the source of the templates is never a mystery.
            logger.info(
                "config/ exists at %s but has no *.example.yaml — using "
                "bundled fallback at %s",
                config_dir,
                bundled,
            )
        return bundled
    return config_dir  # caller will surface the "missing" message


def _copy_example_yamls(
    config_dir: Path,
    *,
    force: bool,
    out: Callable[[str], None],
    example_source: Optional[Path] = None,
) -> tuple[list[str], list[str], list[str]]:
    """Copy each ``X.example.yaml`` → ``X.yaml`` when missing (or always under --force).

    ``example_source`` defaults to ``config_dir`` — same-directory scaffold,
    the dev-checkout case. Pass a separate path (e.g. the wheel-bundled
    ``_bundled/config/``) when the source examples live outside the operator's
    writable config dir.

    Returns ``(created, already_present, missing_examples)``. Splitting
    "already present" (operator's existing file we left alone) from
    "missing example" (broken/corrupt checkout — neither source nor target
    present) is what lets the caller print a truthful summary instead of an
    everything-is-fine banner over a half-populated config dir.
    """
    src_dir = example_source if example_source is not None else config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    already_present: list[str] = []
    missing_examples: list[str] = []
    for filename in USER_YAML_FILES:
        stem_parts = filename.rsplit(".", 1)
        if len(stem_parts) != 2:
            continue  # defensive — USER_YAML_FILES is a literal tuple
        stem, ext = stem_parts
        example = src_dir / f"{stem}.example.{ext}"
        target = config_dir / filename
        if target.exists() and not force:
            already_present.append(filename)
            continue
        if not example.exists():
            out(f"  ! {example.name} missing — skipping {filename}")
            missing_examples.append(filename)
            continue
        shutil.copyfile(example, target)
        created.append(filename)
        out(f"  + config/{filename}  (from {example.name})")
    return created, already_present, missing_examples


def _write_env_file(
    env_path: Path,
    example_path: Path,
    *,
    answers: dict[str, str],
    out: Callable[[str], None],
) -> None:
    """Write ``.env`` based on the example, substituting prompted answers.

    For every ``KEY=`` line where ``KEY`` is in ``answers`` and the value
    is non-empty we drop in the provided value. All other lines pass
    through unchanged (including comments and commented-out entries).
    """
    text = example_path.read_text(encoding="utf-8")
    new_lines: list[str] = []
    substituted: set[str] = set()
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key, _ = stripped.split("=", 1)
            key = key.strip()
            if key in answers and answers[key]:
                new_lines.append(f"{key}={answers[key]}")
                substituted.add(key)
                continue
        new_lines.append(line)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # .env contains DATABASE_URL + API tokens — restrict to owner-readable
    # regardless of the process umask (which usually leaves us at 0o644).
    try:
        env_path.chmod(0o600)
    except OSError as e:
        out(f"  ! could not chmod 600 {env_path.name}: {e}")
    out(f"  + {env_path.name}  (from {example_path.name})  [mode 600]")
    for key in sorted(substituted):
        out(f"    · {key} set from prompt")


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _sanitize_answer(raw: str) -> str:
    """Strip whitespace and reject embedded newlines/CR.

    A malicious or pasted-by-accident answer containing ``\\n`` would write
    an extra line to ``.env``, effectively injecting a new env var
    (``/path\\nEVIL_KEY=value``). We drop every ``\\n`` / ``\\r`` from the
    answer rather than escaping them — there is no legitimate use case for
    a literal newline in a vault path or DSN.
    """
    return raw.strip().replace("\n", "").replace("\r", "")


def _gather_env_answers(
    *,
    non_interactive: bool,
    reader: Callable[[str], str] = input,
    out: Callable[[str], None],
) -> dict[str, str]:
    if non_interactive:
        out("  (--non-interactive: leaving required vars blank for manual edit)")
        return {}
    answers: dict[str, str] = {}
    out("")
    out("Two values are required before workers can run.")
    out("Press Enter to skip a prompt and fill it in later by editing .env.")
    out("")
    for key, hint in _PROMPTED_VARS:
        out(f"{key}")
        out(f"  {hint}")
        try:
            value = _sanitize_answer(reader("> "))
        except EOFError:
            value = ""
        if value:
            answers[key] = value
        out("")
    return answers


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_REQUIRED_ENV_KEYS: tuple[str, ...] = ("EXOCORTEX_VAULT_PATH", "DATABASE_URL")


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser — good enough to flag blank required vars.

    We deliberately don't use python-dotenv here: this runs *before* the
    operator has filled the file in, so we shouldn't fail on syntax that
    dotenv would otherwise tolerate (and we want zero extra deps for
    ``init``).
    """
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _validate_env(env_path: Path, out: Callable[[str], None]) -> bool:
    """Inspect the freshly-written .env for blank REQUIRED keys.

    Pydantic-settings happily accepts ``EXOCORTEX_VAULT_PATH=`` as
    ``Path(".")``, so we can't lean on it for "is the operator done?".
    Instead we parse the file ourselves and warn about anything in
    :data:`_REQUIRED_ENV_KEYS` that is missing or blank. We still return
    True on warning — ``init`` is about scaffolding, not enforcement.
    """
    if not env_path.exists():
        return False
    parsed = _parse_env_file(env_path)
    blanks = [k for k in _REQUIRED_ENV_KEYS if not parsed.get(k)]
    if blanks:
        out("  ! REQUIRED variables still blank: " + ", ".join(blanks))
        out(f"    Edit {env_path.name} before running `exocortex migrate up`.")
        return False
    out("  ✓ REQUIRED variables look set (" + ", ".join(_REQUIRED_ENV_KEYS) + ")")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def cmd_init(
    args: argparse.Namespace,
    *,
    repo_root: Optional[Path] = None,
    reader: Callable[[str], str] = input,
    out: Optional[Callable[[str], None]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Implementation of ``exocortex init``. Returns a CLI exit code."""
    root = (repo_root or _repo_root()).resolve()
    cfg_dir = _config_dir(root)
    env_path = root / ".env"
    env_map = env if env is not None else os.environ

    def _out(line: str) -> None:
        if out is not None:
            out(line)
        else:
            print(line)

    _out(f"Initialising Exocortex in {root}")
    _out("")

    non_interactive = bool(args.non_interactive)
    forcing_env = _env_forces_non_interactive(env_map)
    if forcing_env and not non_interactive:
        non_interactive = True
        _out(f"  (env {forcing_env}=… detected — running non-interactively)")
        _out("")

    # Source of truth for .example.* files: prefer the writable config dir
    # (dev checkout) and fall back to the wheel-shipped bundle (pip install).
    example_source = _resolve_example_source(cfg_dir)
    using_bundled = example_source != cfg_dir
    if using_bundled:
        _out(f"  (using bundled examples from {example_source})")
        _out("")
    elif not cfg_dir.exists() and not example_source.exists():
        _out(f"  ! config/ directory missing at {cfg_dir} — aborting")
        return 2
    env_example = example_source / ".env.example"

    # 1. yaml configs
    _out("Configuration files:")
    created, already_present, missing_examples = _copy_example_yamls(
        cfg_dir,
        force=args.force,
        out=_out,
        example_source=example_source,
    )
    if already_present and not created:
        _out(
            f"  (all {len(already_present)} user yaml configs already present "
            f"— pass --force to regenerate)"
        )
    elif already_present and not args.force:
        _out(
            f"  ({len(already_present)} file(s) left untouched; "
            f"pass --force to overwrite)"
        )
    if missing_examples:
        _out(
            f"  ! {len(missing_examples)} *.example.yaml file(s) missing from "
            f"config/ — checkout looks corrupt: {', '.join(missing_examples)}"
        )
    _out("")

    # 2. .env
    _out("Environment file:")
    if env_path.exists() and not args.force:
        _out(f"  · {env_path.name} already exists — leaving as-is")
        _out("    (pass --force to regenerate from the example)")
    else:
        if not env_example.exists():
            _out(f"  ! {env_example} missing — cannot create .env")
            return 2
        answers = _gather_env_answers(
            non_interactive=non_interactive,
            reader=reader,
            out=_out,
        )
        _write_env_file(env_path, env_example, answers=answers, out=_out)
    _out("")

    # 3. validation (best effort)
    _out("Validation:")
    _validate_env(env_path, out=_out)
    _out("")

    _out("Done. Next steps:")
    _out("  1. Edit config/*.yaml to taste (clients, sources, taxonomies).")
    _out("  2. Make sure .env points at a running Postgres with pgvector + AGE.")
    _out("  3. Run `exocortex migrate up` to apply the schema.")
    return 0


def add_init_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``init`` subcommand on the top-level CLI parser."""
    init = subparsers.add_parser(
        "init",
        help="Scaffold a fresh checkout — copy *.example.yaml + .env.example.",
        description=(
            "Initialise a fresh Exocortex checkout: copy bundled "
            "config/*.example.yaml files to their non-example names, "
            "create a .env from config/.env.example (optionally prompting "
            "for the two required vars), and validate the result against "
            "exocortex.settings.Settings."
        ),
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files instead of leaving them alone.",
    )
    init.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            "Skip prompts; create .env with empty REQUIRED values for later "
            "editing. Also auto-enabled when CI=1 or EXOCORTEX_NO_INPUT=1 is set."
        ),
    )
    init.set_defaults(func=cmd_init)
