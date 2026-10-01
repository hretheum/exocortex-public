# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Mutable compile-run state shared between wiki_compiler.py and core/io.py.

Extracted to break the cyclic dependency wiki_compiler ↔ core/io.
wiki_compiler.py sets these before each compile run; core/io.py reads them.
"""

from __future__ import annotations

DRY_RUN: bool = False
FULL_REBUILD: bool = False
current_run_id: str | None = None
_pages_written: list = []
_llm_tokens_used: int | None = None
