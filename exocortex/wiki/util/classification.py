# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Meeting/entity classification and display utilities."""

from __future__ import annotations

import re
from typing import Any

from exocortex.classifier import load_config as _load_projects_cfg
from exocortex.integrations import get_internal_domain
from exocortex.wiki.util.slugs import _slug_component


def _classify_type(tags: list[str], title: str) -> str:
    cfg = _load_projects_cfg()
    for t in tags:
        t_lower = str(t).lower()
        if t_lower in cfg.type_tags:
            return t_lower
    low = (title or "").lower()
    if re.search(r"\b1[:_\-]?on[:_\-]?1\b|\bsync\b", low):
        return "1on1"
    return "unspecified"


def _is_internal(email: str | None) -> bool:
    domain = get_internal_domain()
    if not domain:
        return False
    return bool(email and email.lower().endswith("@" + domain))


def _client_display(slug: str | None) -> str:
    """Resolve client slug → display_name via projects.yaml; fallback to capitalized slug."""
    if not slug:
        return "Other"
    if slug.startswith("_"):
        return slug.lstrip("_").capitalize() or "Other"
    cfg = _load_projects_cfg()
    for c in cfg.clients:
        if c.slug == slug:
            return c.display_name
    return slug.replace("-", " ").title()


def _project_display(slug: str) -> str:
    """Backwards-compat alias used by legacy renderers; routes to client display."""
    return _client_display(slug)


def _meeting_slug(date: str, title: str, thought_id: Any) -> str:
    """YYYY-MM-DD--<title-slug>--<short-id>, max ~80 characters."""
    title_slug = _slug_component(title)[:60]
    base = f"{date}--{title_slug}" if title_slug else f"{date}--meeting"
    short = str(thought_id or "").replace("-", "")[:8] or "noid"
    return f"{base[:70]}--{short}"
