# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/_bootstrap.py — shared bootstrap for standalone scripts.
# Usage: from exocortex._bootstrap import bootstrap; bootstrap()

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


def bootstrap() -> None:
    """Insert repo root into sys.path and load config/.env.

    Idempotent — safe to call multiple times.
    """
    repo_root = Path(__file__).resolve().parent.parent
    str_root = str(repo_root)
    if str_root not in sys.path:
        sys.path.insert(0, str_root)
    env_path = repo_root / 'config' / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
