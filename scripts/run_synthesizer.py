#!/usr/bin/env -S python3.12 -u
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Backward-compat shim — real implementation lives in
``exocortex.workers.synth``. Kept so existing cron / systemd / docs that
reference ``scripts/run_synthesizer.py`` keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exocortex.workers.synth import main  # noqa: F401,E402


if __name__ == "__main__":
    sys.exit(main())
