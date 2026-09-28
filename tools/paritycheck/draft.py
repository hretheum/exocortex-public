"""Draft translation of a document that has no pair yet.

The draft goes next to where the pair should be, with ``translation:
machine`` and ``human_validated: false`` in the front matter. The publisher
holds files marked this way until a person reviews them and removes the
marker.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .core import FRONT

PROMPT = """Translate the Markdown document below from {src} to {dst}.
Keep the Markdown structure exactly: the same headings, lists, tables, links
(do not change link targets), code and numbers. Use these term translations:
{glossary}
Write plain, direct prose. Return only the translated document body."""


def read_glossary(path: Path) -> list[dict]:
    """Rows of the first Markdown table in glossary.md whose header starts
    with the columns PL and EN."""
    rows, header = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            if header:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            if [c.lower() for c in cells[:2]] == ["pl", "en"]:
                header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append({"pl": cells[0], "en": cells[1]})
    return rows


def _pair_path(path: Path) -> tuple[Path, str, str]:
    parts = list(path.parts)
    idx = max(i for i, p in enumerate(parts) if p in ("pl", "en"))
    src = parts[idx]
    dst = "en" if src == "pl" else "pl"
    parts[idx] = dst
    return Path(*parts), src, dst


def draft(path: Path, llm_url: str, model: str, glossary_path: Path | None = None) -> Path:
    import httpx

    target, src, dst = _pair_path(path)
    root = path
    while root.name not in ("pl", "en"):
        root = root.parent
    root = root.parent
    glossary_path = glossary_path or root / "glossary.md"
    terms = read_glossary(glossary_path) if glossary_path.exists() else []
    gl = "\n".join(f"- {t[src]} = {t[dst]}" for t in terms)

    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    front = yaml.safe_load(m.group(1)) if m else {}
    body = text[m.end():] if m else text
    resp = httpx.post(
        llm_url.rstrip("/") + "/chat/completions",
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": PROMPT.format(src=src, dst=dst, glossary=gl or "(none)")},
                {"role": "user", "content": body},
            ],
        },
        timeout=600,
    )
    resp.raise_for_status()
    out_body = resp.json()["choices"][0]["message"]["content"].strip() + "\n"
    front = dict(front or {})
    front["lang"] = dst
    rel_depth = len(path.relative_to(root / src).parts) - 1
    front["counterpart"] = "../" * (rel_depth + 1) + f"{src}/" + path.relative_to(root / src).as_posix()
    front["translation"] = "machine"
    meta = dict(front.get("provenance_metadata") or {})
    meta["human_validated"] = False
    front["provenance_metadata"] = meta
    target.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
    target.write_text(f"---\n{fm}---\n\n{re.sub(r'^\s+', '', out_body)}", encoding="utf-8")
    return target
