# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Centralised environment configuration via pydantic-settings.

User-specific settings (vault path, vault name, tenant id, database URL) are
read via two env-var naming conventions:

* ``EXOCORTEX_*``  — canonical, validated through pydantic-settings.
* ``DATABASE_URL`` — unprefixed, conventional psycopg/SQLAlchemy connection
  string. Loaded explicitly because it is the standard variable name every
  PaaS (Heroku, Fly, Railway, Docker compose, ...) sets out-of-the-box and
  forcing operators to alias it would harm the onboarding story.

Note on env_file: pydantic-settings resolves ``.env`` relative to the current
working directory, not the package directory. CLI entry points that rely on
the dotfile should run from the repo root, or set env vars explicitly via
their process manager (systemd, docker compose, etc.).
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EXOCORTEX_",
        env_file=".env",  # resolved relative to CWD — see module docstring
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    vault_path: Path = Field(
        ...,
        description="Absolute path to Obsidian vault root",
        validation_alias=AliasChoices(
            "EXOCORTEX_VAULT_PATH",
            "VAULT_PATH",
            "SECOND_BRAIN_VAULT_PATH",
        ),
    )
    vault_name: str | None = Field(
        None, description="Obsidian vault name (for obsidian:// links)"
    )
    tenant_id: str = Field(
        "default", description="Tenant identifier for multi-tenant setups"
    )
    owner_names: str = Field(
        "",
        description=(
            "Comma-separated real display-names/aliases of the vault owner — "
            "the 'me' in action-item owner filters (Moje TODO, home dashboard, "
            "live sections). Empty = only the anonymized built-in placeholders "
            "match. Kept OUT of the public repo; set via EXOCORTEX_OWNER_NAMES "
            "in the deployment env."
        ),
    )
    # ``DATABASE_URL`` is the conventional unprefixed name every PaaS sets
    # out-of-the-box; ``EXOCORTEX_DATABASE_URL`` is accepted too for symmetry
    # with the rest of Settings (operators who lean on the prefixed
    # convention won't trip a silent miss). When both are set the unprefixed
    # form wins — that is what PaaS / docker compose / systemd inject and
    # what we recommend in ``.env.example``.
    database_url: str | None = Field(
        None,
        validation_alias=AliasChoices("DATABASE_URL", "EXOCORTEX_DATABASE_URL"),
        description="psycopg-compatible Postgres connection URL",
    )
    age_graph: str = Field(
        "exocortex",
        description="Apache AGE graph name (default: 'exocortex')",
    )

    # F31.0.3 — Telegram bot worker. All three optional so the bot module is
    # importable on hosts where Telegram is not configured (CI, unit tests,
    # local dev). The worker entry point validates `tg_bot_token` at startup.
    tg_bot_token: str | None = Field(
        None,
        validation_alias=AliasChoices("TG_BOT_TOKEN", "EXOCORTEX_TG_BOT_TOKEN"),
        description="Telegram bot HTTP API token (BotFather).",
    )
    tg_allowed_user_ids: str = Field(
        "",
        validation_alias=AliasChoices(
            "TG_ALLOWED_USER_IDS", "EXOCORTEX_TG_ALLOWED_USER_IDS"
        ),
        description=(
            "Comma-separated numeric Telegram user IDs allowed to talk to the bot. "
            "Empty string = no one allowed (deny-by-default)."
        ),
    )
    tg_chat_id: int | None = Field(
        None,
        validation_alias=AliasChoices("TG_CHAT_ID", "EXOCORTEX_TG_CHAT_ID"),
        description="Default chat id for unsolicited push messages (digest, alerts).",
    )
    capture_api_url: str = Field(
        "http://localhost:8000",
        validation_alias=AliasChoices(
            "CAPTURE_API_URL", "EXOCORTEX_CAPTURE_API_URL"
        ),
        description="Capture API base URL (no trailing slash).",
    )
    capture_api_token: str | None = Field(
        None,
        validation_alias=AliasChoices(
            "CAPTURE_API_TOKEN", "EXOCORTEX_CAPTURE_API_TOKEN"
        ),
        description="Bearer token for Capture API.",
    )


_settings: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    # Double-checked locking: fast path avoids the lock once cached; the
    # locked path makes concurrent first-time initialisation safe.
    global _settings
    if _settings is None:
        with _settings_lock:
            if _settings is None:
                _settings = Settings()
    return _settings


def reset_settings() -> None:
    """For testing: clear cached settings."""
    global _settings
    with _settings_lock:
        _settings = None


def get_database_url() -> str:
    """Return ``DATABASE_URL`` or raise with an onboarding-friendly hint.

    psycopg accepts both URL strings (``postgresql://user:pass@host:port/db``)
    and key/value conninfo (``host=… dbname=… user=… password=…``). The URL
    form is what we recommend in ``.env.example`` and is what every PaaS
    injects by default, so that is what we surface here.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in your .env file, e.g. "
            "DATABASE_URL=postgresql://exocortex:secret@localhost:5432/exocortex "
            "(see config/.env.example). Required by exocortex migrate up and "
            "every worker that talks to Postgres."
        )
    return settings.database_url


def get_tenant_id() -> str:
    """Return the configured tenant id (defaults to ``'default'``).

    Read directly from the environment instead of through ``get_settings()``
    because ``Settings.vault_path`` is required — and module-level callers
    (``capture_api``, ``scorer``, …) historically imported ``TENANT_ID`` at
    import time, before the vault path was even relevant. Keeping this lookup
    env-only preserves that import contract.

    Resolution order:
      1. ``EXOCORTEX_TENANT_ID``  — canonical pydantic-style name
      2. ``TENANT_ID``            — legacy (pre-F31.8.5 deployments)
      3. ``'default'``            — single-user installs

    A blank ``EXOCORTEX_TENANT_ID=`` (common pitfall in systemd
    ``EnvironmentFile`` where an unset value is rendered as empty) is treated
    as *unset* — without this, ``or`` would fall through to ``TENANT_ID`` and
    silently route writes to the wrong tenant in a multi-tenant deployment.
    """
    import os

    primary = os.environ.get("EXOCORTEX_TENANT_ID")
    if primary is not None and primary.strip():
        return primary.strip()
    legacy = os.environ.get("TENANT_ID")
    if legacy is not None and legacy.strip():
        return legacy.strip()
    return "default"
