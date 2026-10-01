# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""GraphRAG system-prompt loader (F31.8.2).

Reads ``config/graph_rag.yaml`` (with fallback to ``graph_rag.example.yaml``),
renders ``exocortex/prompts/graph_rag/system_prompt.md.j2`` with the user
config, and returns a plain string ready to be passed as the ``system`` block
to the LLM router.

``clients: "auto"`` is resolved against the live graph via a top-N most-
connected query. On any DB/connectivity error, ``auto`` collapses to an
empty list so the prompt still renders.

Trust model: the config file (``config/graph_rag.yaml``) is treated as
trusted operator-supplied input. In particular, ``extra_instructions`` is
rendered verbatim into the system prompt — do NOT wire untrusted end-user
text into this field.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_TEMPLATE_DIR = _PACKAGE_ROOT / "prompts" / "graph_rag"
_TEMPLATE_NAME = "system_prompt.md.j2"

_CONFIG_PATH = _REPO_ROOT / "config" / "graph_rag.yaml"
_EXAMPLE_PATH = _REPO_ROOT / "config" / "graph_rag.example.yaml"

_DEFAULTS: dict[str, Any] = {
    "user_role": "engineer",
    "clients": [],
    "clients_auto_top_n": 8,
    "language": "English",
    "citation_style": "Obsidian wikilinks `[[slug]]`",
    "extra_instructions": "",
}

_warned_missing_config = False
_warned_missing_template_dep = False

_render_lock = threading.Lock()
_cached_prompt: str | None = None


def _load_config() -> dict[str, Any]:
    """Return the user/example config merged on top of defaults."""
    import yaml  # local import keeps test stubs working when PyYAML is absent

    global _warned_missing_config

    if _CONFIG_PATH.exists():
        data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    elif _EXAMPLE_PATH.exists():
        data = yaml.safe_load(_EXAMPLE_PATH.read_text(encoding="utf-8")) or {}
        if not _warned_missing_config:
            logger.info(
                "config/graph_rag.yaml not found — falling back to the bundled example. "
                "Copy graph_rag.example.yaml to graph_rag.yaml and edit to customise."
            )
            _warned_missing_config = True
    else:
        if not _warned_missing_config:
            logger.warning(
                "Neither %s nor %s found — using built-in defaults.",
                _CONFIG_PATH,
                _EXAMPLE_PATH,
            )
            _warned_missing_config = True
        data = {}

    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if v is not None}}
    return merged


def _resolve_clients_auto(top_n: int) -> list[str]:
    """Return the top-N most-connected client names from the live graph.

    Errors (no DB, missing tables, empty graph) are swallowed — the prompt is
    perfectly usable without a client list.
    """
    try:
        from exocortex.db import query  # local import: tests stub exocortex.db
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("graph_rag prompt: db import failed (%s) — clients=[]", exc)
        return []

    sql = (
        "SELECT metadata->>'name' AS name, count(*) AS n "
        "FROM thoughts "
        "WHERE thought_type = 'entity' "
        "  AND metadata->>'entity_type' = 'client' "
        "  AND metadata ? 'name' "
        "GROUP BY 1 "
        "ORDER BY n DESC "
        "LIMIT %s"
    )
    try:
        rows = query(sql, top_n)
    except Exception as exc:
        logger.info(
            "graph_rag prompt: 'auto' client resolution failed (%s) — "
            "rendering prompt with empty client list.",
            exc,
        )
        return []

    return [r["name"] for r in rows if r.get("name")]


def _clients_for_prompt(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("clients", [])
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        top_n = int(cfg.get("clients_auto_top_n") or _DEFAULTS["clients_auto_top_n"])
        return _resolve_clients_auto(top_n)
    if isinstance(raw, list):
        return [str(c).strip() for c in raw if str(c).strip()]
    logger.warning(
        "graph_rag prompt: unexpected 'clients' value %r — coercing to []", raw
    )
    return []


def _render(cfg: dict[str, Any], clients_list: list[str]) -> str:
    global _warned_missing_template_dep
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ImportError:
        if not _warned_missing_template_dep:
            logger.warning(
                "jinja2 is not installed — returning a static fallback prompt. "
                "Add 'jinja2' to your environment to render the configured template."
            )
            _warned_missing_template_dep = True
        return _static_fallback(cfg, clients_list)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    template = env.get_template(_TEMPLATE_NAME)
    ctx = {**cfg, "clients_list": clients_list}
    return template.render(**ctx).strip()


def _static_fallback(cfg: dict[str, Any], clients_list: list[str]) -> str:
    """Minimal hand-rolled rendering used when jinja2 is unavailable."""
    clients_clause = (
        f" — clients: {', '.join(clients_list)}" if clients_list else ""
    )
    extra = cfg.get("extra_instructions") or ""
    suffix = f"\n\n{extra}" if extra.strip() else ""
    return (
        f"You are an assistant analysing the work context of the operator "
        f"({cfg.get('user_role', 'engineer')}{clients_clause}).\n\n"
        f"Answer using ONLY the supplied sources. Write in "
        f"{cfg.get('language', 'English')}. Cite sources as "
        f"{cfg.get('citation_style', '[[slug]]')}. If sources are "
        f"insufficient, say so explicitly.{suffix}"
    )


def build_system_prompt() -> str:
    """Return the rendered system prompt as plain text.

    The result is cached process-wide; call :func:`reset` to force a re-read
    (used by tests).
    """
    global _cached_prompt
    if _cached_prompt is not None:
        return _cached_prompt
    with _render_lock:
        if _cached_prompt is not None:
            return _cached_prompt
        cfg = _load_config()
        clients_list = _clients_for_prompt(cfg)
        _cached_prompt = _render(cfg, clients_list)
        return _cached_prompt


def reset() -> None:
    """Clear cached prompt + warning flags (test helper)."""
    global _cached_prompt, _warned_missing_config, _warned_missing_template_dep
    with _render_lock:
        _cached_prompt = None
        _warned_missing_config = False
        _warned_missing_template_dep = False
