"""flip_human_validated — F31.3.5.

Edytuje `human_validated:` field w `provenance_metadata:` frontmatter pliku .md.
Idempotent: jeśli wartość już taka jak żądana → noop bez tknięcia mtime.
Atomic write: temp file + os.replace.
F11.4 [x] invariant: count `[x]` post >= pre (drop = ValueError).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_FIELD_RE = re.compile(
    r"^(?P<indent>\s+)human_validated:\s*(?P<value>true|false)\s*$",
    re.MULTILINE,
)
_CHECKBOX_RE = re.compile(r"\[x\]")


def flip_human_validated(path: str | Path, new_value: bool) -> dict:
    p = Path(path)
    content = p.read_text(encoding="utf-8")

    match = _FIELD_RE.search(content)
    if match is None:
        return {"error": "no_field"}

    current = match.group("value") == "true"
    if current == new_value:
        return {"noop": True}

    pre_count = len(_CHECKBOX_RE.findall(content))

    new_line = f"{match.group('indent')}human_validated: {'true' if new_value else 'false'}"
    new_content = content[: match.start()] + new_line + content[match.end():]

    post_count = len(_CHECKBOX_RE.findall(new_content))
    if post_count < pre_count:
        raise ValueError(
            f"[x] invariant violated: pre={pre_count} post={post_count} for {p}"
        )

    dir_ = p.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {"changed": True}
