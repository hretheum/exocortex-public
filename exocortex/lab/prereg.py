# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Preregistration of hypothesis cards (roadmap task F2.4). Standard library only.

A card is frozen when both of its language versions say
``human_validated: true``. Its checksum is SHA-256 over this text, UTF-8::

    prereg-v1
    --- pl ---
    <canonical Polish file>
    --- en ---
    <canonical English file>

Canonical form of a file: Unicode NFC; line endings as ``\\n``; trailing
spaces and tabs removed from every line; blank lines at the start and end
removed; and in the front matter the top-level lines ``prereg_hash:`` and
``human_validated:`` dropped, because they change when a card is approved,
not when its content changes. Everything else counts: a changed threshold,
a changed sentence, a changed comment in the header.

The registry ``prereg.jsonl`` has one JSON object per line and is only
ever appended to. lab/verify_prereg.py uses this file on a clean clone of
the repository, so it must keep working with nothing but Python.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ALGORITHM = "prereg-v1"
STATE_FIELDS = ("prereg_hash", "human_validated")
_STATE_LINE = re.compile(rf"^({'|'.join(STATE_FIELDS)})\s*:")


def canonical(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    if lines and lines[0] == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            end = 0
        if end:
            header = [ln for ln in lines[1:end] if not _STATE_LINE.match(ln)]
            lines = ["---", *header, "---", *lines[end + 1:]]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def card_hash(pl_text: str, en_text: str) -> str:
    payload = f"{ALGORITHM}\n--- pl ---\n{canonical(pl_text)}\n--- en ---\n{canonical(en_text)}\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_registry(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find(registry: list[dict], slug: str, version: int) -> dict | None:
    for entry in registry:
        if entry.get("slug") == slug and entry.get("version") == version:
            return entry
    return None


def append(path: Path, entry: dict) -> None:
    """Add one entry at the end. A second entry for the same card version is refused."""
    if find(read_registry(path), entry["slug"], entry["version"]) is not None:
        raise ValueError(f"{entry['slug']} v{entry['version']} is already registered")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def is_append_only(old: str, new: str) -> bool:
    """True if ``new`` keeps every line of ``old`` in place and only adds lines at the end."""
    old_lines = [ln for ln in old.splitlines() if ln.strip()]
    new_lines = [ln for ln in new.splitlines() if ln.strip()]
    return new_lines[:len(old_lines)] == old_lines


def verify(root: Path, registry: list[dict]) -> list[dict]:
    """Recompute every registered checksum from the files under ``root``."""
    out = []
    for entry in registry:
        files = entry.get("files") or {}
        paths = {lang: root / files.get(lang, "") for lang in ("pl", "en")}
        missing = [lang for lang, p in paths.items() if not files.get(lang) or not p.is_file()]
        if missing:
            out.append({**entry, "status": "missing", "detail": ", ".join(missing)})
            continue
        actual = card_hash(paths["pl"].read_text(encoding="utf-8"), paths["en"].read_text(encoding="utf-8"))
        out.append({**entry, "status": "ok" if actual == entry.get("sha256") else "changed", "actual": actual})
    return out
