# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Wiki page I/O: atomic writes, frontmatter rendering, user-notes preservation."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from exocortex.settings import get_settings

# ── Constants (re-exported so importers can use exocortex.wiki.core.io.X) ──

SCHEMA_VERSION = "5.0"

SYSTEM_FRONTMATTER_KEYS = {
    "source_ids",
    "schema_version",
    "meeting_id",
    "synced_at",
    "body_hash",
    "transcript_url",
    "input_hash",
    "compile_run_id",
    "generated_at",
    "synthesis_id",
    "synthesis_input_hash",
    "synthesis_generated_at",
    "synthesis_prompt_version",
    "synthesis_model",
    "synthesis_n_meetings",
    "source_id",
}

USER_NOTES_BEGIN = "<!-- USER_NOTES_START -->"
USER_NOTES_END = "<!-- USER_NOTES_END -->"
GENERATED_BEGIN = "<!-- GENERATED_START -->"
GENERATED_END = "<!-- GENERATED_END -->"


# ── Path helpers ─────────────────────────────────────────────────────────────


def _default_wiki_root_str() -> str:
    """Return WIKI_OUTPUT_PATH or `{vault_path}/wiki/` derived from settings."""
    override = os.environ.get("WIKI_OUTPUT_PATH")
    if override:
        return override
    return str(get_settings().vault_path / "wiki") + "/"


def _get_wiki_root() -> Path:
    """Return the root of the wiki directory (parent of all domain folders)."""
    p = Path(_default_wiki_root_str())
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Error-suppressing helper ──────────────────────────────────────────────────


def _safe(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        logging.warning("[wiki_compiler] %s failed: %r", fn.__name__, exc)


# ── Idempotency helpers ───────────────────────────────────────────────────────


def _hash_input(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_unchanged(path: Path, new_hash: str) -> bool:
    if not path.exists():
        return False
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return False
    # Match both legacy `input_hash:` and F4.3.5 `_input_hash:` so re-runs against
    # files written before the frontmatter rename still detect unchanged pages.
    m = re.search(r"^_?input_hash:\s*([a-f0-9]+)\s*$", txt, re.MULTILINE)
    return bool(m and m.group(1) == new_hash)


# ── User-notes extraction ─────────────────────────────────────────────────────


def _extract_user_notes(path: Path) -> str:
    """Return content between USER_NOTES markers, or empty string."""
    if not path.exists():
        return ""
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(
        re.escape(USER_NOTES_BEGIN) + r"(.*?)" + re.escape(USER_NOTES_END),
        txt,
        re.DOTALL,
    )
    return m.group(1).strip() if m else ""


# ── Frontmatter rendering ─────────────────────────────────────────────────────


def render_frontmatter(data: dict) -> str:
    """Render YAML frontmatter block (legacy — used by FRP module).
    Work module v2 uses render_frontmatter_v2 with pyyaml + wikilink support."""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---\n\n")
    return "\n".join(lines)


def render_frontmatter_v2(data: dict) -> str:
    """YAML frontmatter that double-quotes wikilink strings.

    Strings like ``[[acme]]`` become ``"[[acme]]"`` so Obsidian renders them
    as inline wikilinks (and pyyaml round-trips cleanly).
    """

    class _Dumper(yaml.SafeDumper):
        pass

    def _repr_str(dumper, value):
        if value.startswith("[[") and value.endswith("]]"):
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"')
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    _Dumper.add_representer(str, _repr_str)

    body = yaml.dump(
        data,
        Dumper=_Dumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=10_000,
    )
    return f"---\n{body}---\n\n"


def _partition_frontmatter(fm: dict) -> dict:
    """Split frontmatter into user-facing (top) + system (`_*` prefixed, bottom).

    Rules:
      - Keys already prefixed with `_` stay as-is.
      - Keys in SYSTEM_FRONTMATTER_KEYS get a `_` prefix.
      - Everything else stays user-facing (top of YAML block).
    User-facing block keeps insertion order; system block is appended after,
    sorted alphabetically — that way Obsidian Properties panel shows clean fields
    first and the user can collapse `_*` ones via "Properties to ignore".
    """
    user_fields: dict = {}
    system_fields: dict = {}
    for k, v in fm.items():
        if v is None:
            continue
        # Provenance source-id lists run into the hundreds (MOC pages ~450) and
        # bury the Obsidian Properties panel; nothing reads them back, so keep
        # only a count.
        if k in ("source_ids", "_source_ids"):
            system_fields["_source_count"] = (
                len(v) if isinstance(v, (list, tuple)) else v
            )
            continue
        if k.startswith("_"):
            system_fields[k] = v
        elif k in SYSTEM_FRONTMATTER_KEYS:
            system_fields[f"_{k}"] = v
        else:
            user_fields[k] = v
    out: dict = {}
    out.update(user_fields)
    for k in sorted(system_fields):
        out[k] = system_fields[k]
    return out


def _parse_yaml_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from an existing wiki page. Returns {} on any error."""
    if not path.exists():
        return {}
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---", txt, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


# ── Atomic write with frontmatter + user notes ────────────────────────────────


def _write_with_frontmatter(
    path: str,
    fm: dict,
    body_generated: str,
    source_ids: list[str],
) -> bool:
    """Write a wiki page atomically. Returns True if file was written, False if
    skipped (input_hash unchanged). Preserves USER_NOTES block across re-runs.

    F4.3.5: system metadata is rendered with `_` prefix at the end of the YAML
    block — see `_partition_frontmatter` and SYSTEM_FRONTMATTER_KEYS.

    Globals DRY_RUN, current_run_id, _pages_written are accessed lazily from
    exocortex.wiki_compiler to avoid circular imports (they will move to
    RunContext in F31.6.3).
    """
    from exocortex.wiki.core import _state as _wc

    p = Path(path)
    new_hash = fm.get("input_hash") or fm.get("_input_hash")
    if new_hash and _is_unchanged(p, new_hash):
        return False

    # F4.6.6.5 — dry-run: report would-write but skip I/O.
    if _wc.DRY_RUN:
        return True

    fm_full = dict(fm)
    fm_full.setdefault(
        "compile_run_id", str(_wc.current_run_id) if _wc.current_run_id else None
    )
    fm_full.setdefault("generated_at", datetime.now().isoformat())  # noqa: DTZ005 — naive local timestamp; an aware one would change the output
    fm_full.setdefault("schema_version", SCHEMA_VERSION)
    fm_full.setdefault("source_ids", list(source_ids or []))

    # F22.6 — auto-detect title: if body starts with H1, move to frontmatter title
    # and strip from body. Prevents Obsidian inline title doubling.
    if body_generated.startswith("# "):
        newline = (
            body_generated.index("\n")
            if "\n" in body_generated
            else len(body_generated)
        )
        h1_title = body_generated[2:newline].strip()
        fm_full.setdefault("title", h1_title)
        body_generated = body_generated[newline:].lstrip("\n")

    fm_full = _partition_frontmatter(fm_full)

    user_notes = _extract_user_notes(p)
    user_block = (
        f"\n\n{USER_NOTES_BEGIN}\n{user_notes}\n{USER_NOTES_END}\n"
        if user_notes
        else f"\n\n{USER_NOTES_BEGIN}\n\n{USER_NOTES_END}\n"
    )

    full = (
        render_frontmatter_v2(fm_full)
        + GENERATED_BEGIN
        + "\n"
        + body_generated.rstrip()
        + "\n"
        + GENERATED_END
        + user_block
    )

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(full, encoding="utf-8")
    tmp.rename(p)
    return True


def write_wiki(path: str, content: str, source_ids: list | None = None) -> None:
    """Atomic write: tmp → rename. Adds frontmatter."""
    from exocortex.wiki.core import _state as _wc

    if _wc.DRY_RUN:
        return
    frontmatter = {
        "compile_run_id": _wc.current_run_id,
        "source_ids": source_ids or [],
        "generated_at": datetime.now().isoformat(),  # noqa: DTZ005 — naive local timestamp; an aware one would change the output
        "schema_version": SCHEMA_VERSION,
    }
    full_content = render_frontmatter(frontmatter) + content
    tmp = f"{path}.tmp"
    Path(tmp).write_text(full_content, encoding="utf-8")
    Path(tmp).rename(path)
