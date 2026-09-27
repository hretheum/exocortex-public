# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Backward-compat shim — real implementation lives in
``exocortex.workers.ingest``. Kept so existing cron / systemd / docs that
reference ``scripts/bulk_ingest_vault.py`` keep working.

Re-exports all public helpers (``ingest_file``, ``normalize_participants``,
``parse_frontmatter``, …) so older test imports keep resolving.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exocortex.workers.ingest import (  # noqa: F401,E402
    DATE_PREFIX_RE,
    EXTRACTED_SECTIONS,
    FRONTMATTER_RE,
    H1_RE,
    INGEST_ANOMALIES_TSV,
    THOUGHT_TYPE,
    _body_hash,
    _emit_edges,
    _run_llm_extraction,
    build_body,
    extract_section,
    find_existing,
    ingest_file,
    main as _module_main,
    normalize_participants,
    parse_frontmatter,
    parse_sections,
    resolve_title,
    run_bulk_ingest,
)


def main(dry_run: bool = False, force: bool = False, skip_llm_tags: bool = False) -> None:
    """Legacy kwargs-style entry — kept for any direct importers."""
    run_bulk_ingest(dry_run=dry_run, force=force, skip_llm_tags=skip_llm_tags)


if __name__ == "__main__":
    sys.exit(_module_main())
