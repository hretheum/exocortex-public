# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Bundled config + schema resources shipped inside the wheel.

These files are copies of the top-level ``config/`` and ``schema/`` directories
at build time. ``exocortex init`` falls back to this bundle when invoked from a
pip-installed wheel (i.e. when the repo root has no ``config/`` directory).

The copies are kept in sync by ``scripts/sync_bundled.py`` — running it after
edits to ``config/*.example.yaml`` or ``schema/*.sql`` is part of the release
checklist. The unit-test suite calls ``sync_bundled --check`` as a CI guard
so a forgotten sync fails the build before release rather than shipping a
silently stale bundle to PyPI.

Do not edit files in this directory by hand.
"""
