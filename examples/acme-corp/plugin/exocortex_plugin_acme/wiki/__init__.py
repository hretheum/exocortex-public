# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""ACME wiki domain compiler.

Produces a small wiki tree under ``$WIKI_OUTPUT_PATH/acme/``:

    acme/_index.md                  ← landing page with project links + stats
    acme/by-project/<project>.md    ← one page per sub-project (acme-platform,
                                      acme-revamp), listing its notes
    acme/by-type/<type>.md          ← grouped by note type (meeting_note,
                                      decision, problem_note, …)

The implementation deliberately uses only ``exocortex.db`` and the standard
library so it is trivial to read end-to-end.
"""
from __future__ import annotations

import os
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

from exocortex.wiki.domains.base import DomainCompiler


def _output_root(ctx: Any) -> Path:
    # VAULT_PATH intentionally NOT in this chain — it points at the vault root
    # and would pollute it with $VAULT/acme/.  Wiki output must land under a
    # dedicated wiki dir (`$WIKI_OUTPUT_PATH`, ctx override, or local default).
    base = (
        getattr(ctx, "output_path", None)
        or os.environ.get("WIKI_OUTPUT_PATH")
        or "./output/wiki"
    )
    return Path(base) / "acme"


def _slugify(value: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in (value or ""))
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "untitled"


class AcmeDomainCompiler(DomainCompiler):
    """Minimal end-to-end domain compiler for the ACME example plugin."""

    @property
    def name(self) -> str:
        return "acme"

    def compile(self, ctx: Any) -> None:
        from exocortex.db import query_all

        rows = query_all(
            """
            SELECT id,
                   metadata->>'title'   AS title,
                   metadata->>'project' AS project,
                   metadata->>'type'    AS type,
                   metadata->>'date'    AS date,
                   body_md
              FROM thoughts
             WHERE tenant_id = %s
               AND metadata->>'client' = 'acme'
             ORDER BY metadata->>'date' DESC NULLS LAST
            """,
            (ctx.tenant_id,),
        ) or []

        root = _output_root(ctx)
        (root / "by-project").mkdir(parents=True, exist_ok=True)
        (root / "by-type").mkdir(parents=True, exist_ok=True)

        # _index.md
        index_lines = [
            "---",
            "title: ACME Corp — overview",
            "provenance: ai_authored",
            "---",
            "",
            "# ACME Corp",
            "",
            f"Total notes: **{len(rows)}**",
            "",
            "## Sub-projects",
            "",
        ]
        by_project: dict[str, list[dict]] = defaultdict(list)
        by_type: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_project[(r.get("project") or "_unscoped")].append(r)
            by_type[(r.get("type") or "_untyped")].append(r)

        for project, items in sorted(by_project.items()):
            index_lines.append(f"- [[by-project/{_slugify(project)}|{project}]] "
                               f"({len(items)} notes)")
        index_lines.append("")
        index_lines.append("## Note types")
        index_lines.append("")
        for typ, items in sorted(by_type.items()):
            index_lines.append(f"- [[by-type/{_slugify(typ)}|{typ}]] "
                               f"({len(items)} notes)")

        (root / "_index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        for project, items in by_project.items():
            self._write_grouping_page(root / "by-project" / f"{_slugify(project)}.md",
                                      heading=f"ACME — {project}",
                                      items=items)
        for typ, items in by_type.items():
            self._write_grouping_page(root / "by-type" / f"{_slugify(typ)}.md",
                                      heading=f"ACME — {typ}",
                                      items=items)

    def _write_grouping_page(self, path: Path, heading: str, items: list[dict]) -> None:
        body = [
            "---",
            f"title: {heading}",
            "provenance: ai_authored",
            "---",
            "",
            f"# {heading}",
            "",
            f"{len(items)} notes.",
            "",
        ]
        for r in items:
            title = (r.get("title") or r.get("id"))
            date = (r.get("date") or "")
            excerpt = textwrap.shorten((r.get("body_md") or "").strip(),
                                       width=180, placeholder="…")
            body.append(f"## {title}")
            if date:
                body.append(f"_{date}_")
            body.append("")
            body.append(excerpt or "_(no body)_")
            body.append("")
        path.write_text("\n".join(body) + "\n", encoding="utf-8")

    def prune_orphans(self, ctx: Any) -> int:
        """Remove pages whose underlying thought no longer exists.

        This example regenerates the directory from scratch on every compile,
        so prune is a no-op. A real domain compiler would diff filesystem
        against the DB and delete stale files here.
        """
        return 0
