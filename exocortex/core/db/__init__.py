# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Core DB utilities (schema migrations).

This sub-package is intentionally minimal — runtime DB helpers (pool, query
helpers, AGE graph wrappers, embeddings) live in :mod:`exocortex.db`. Code
here is concerned with *schema lifecycle* operations that can run before the
main pool is ready (e.g. on a brand-new database).
"""
