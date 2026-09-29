# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Allowlist of sources for a lab deployment (roadmap task F2.2).

Off by default. When EXOCORTEX_SOURCE_ALLOWLIST names a YAML file, the
Capture API accepts only content whose source_type and address are on the
list, and adapters that download from the network call ``require_url``
before fetching. Every refusal is logged as one JSON line (source type,
address, reason; never content).

File format (see lab/sources.yaml)::

    sources:
      - id: arxiv-abstracts
        source_type: arxiv
        domains: [arxiv.org, export.arxiv.org]   # host or its subdomains
        uri_prefixes: []                          # or exact address prefixes
        min_interval_s: 3                         # optional pause between downloads (the lab's fetch gateway)
        basis: "CC0 metadata; checked 2026-..."
        added_by: owner
        reason: "F3 corpus"
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("exocortex.source_allowlist")

REQUIRED_FIELDS = ("id", "source_type", "basis", "added_by", "reason")


class SourceNotAllowed(Exception):
    """Raised when a source is not on the allowlist."""


@dataclass(frozen=True)
class Source:
    id: str
    source_type: str
    basis: str
    added_by: str
    reason: str
    domains: tuple[str, ...] = field(default_factory=tuple)
    uri_prefixes: tuple[str, ...] = field(default_factory=tuple)
    min_interval_s: float | None = None  # pause between downloads the source's terms ask for

    def matches_uri(self, uri: str) -> bool:
        if any(uri.startswith(p) for p in self.uri_prefixes):
            return True
        host = (urlparse(uri).hostname or "").lower()
        return bool(host) and any(host == d or host.endswith("." + d) for d in self.domains)


class Allowlist:
    def __init__(self, sources: list[Source], path: Path | None = None):
        self.sources = sources
        self.path = path

    @classmethod
    def load(cls, path: Path) -> Allowlist:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sources = []
        for i, raw in enumerate(data.get("sources") or []):
            missing = [k for k in REQUIRED_FIELDS if not raw.get(k)]
            if missing:
                raise ValueError(f"{path}: source #{i} is missing {', '.join(missing)}")
            if not raw.get("domains") and not raw.get("uri_prefixes"):
                raise ValueError(f"{path}: source {raw['id']} needs domains or uri_prefixes")
            sources.append(Source(
                id=str(raw["id"]), source_type=str(raw["source_type"]), basis=str(raw["basis"]),
                added_by=str(raw["added_by"]), reason=str(raw["reason"]),
                domains=tuple(str(d).lower() for d in raw.get("domains") or ()),
                uri_prefixes=tuple(str(p) for p in raw.get("uri_prefixes") or ()),
                min_interval_s=float(raw["min_interval_s"]) if raw.get("min_interval_s") else None,
            ))
        return cls(sources, path)

    def check(self, source_type: str, uri: str) -> tuple[bool, str]:
        """(allowed, reason) for content arriving at the Capture API."""
        typed = [s for s in self.sources if s.source_type == source_type]
        if not typed:
            return False, "source_type not on the allowlist"
        if not any(s.matches_uri(uri) for s in typed):
            return False, "address not on the allowlist for this source_type"
        return True, "ok"

    def check_url(self, url: str) -> tuple[bool, str]:
        """(allowed, reason) for a download by an adapter, any source_type."""
        if any(s.matches_uri(url) for s in self.sources):
            return True, "ok"
        return False, "domain not on the allowlist"


_cache: dict[str, tuple[int, Allowlist]] = {}


def active() -> Allowlist | None:
    """The allowlist named by EXOCORTEX_SOURCE_ALLOWLIST, reloaded when the file changes; None if unset."""
    raw = os.environ.get("EXOCORTEX_SOURCE_ALLOWLIST", "").strip()
    if not raw:
        return None
    path = Path(raw)
    stamp = path.stat().st_mtime_ns  # a configured but missing file is an error, not "allow all"
    cached = _cache.get(raw)
    if cached is None or cached[0] != stamp:
        _cache[raw] = (stamp, Allowlist.load(path))
    return _cache[raw][1]


def _log_refusal(kind: str, source_type: str | None, uri: str, reason: str) -> None:
    logger.warning(json.dumps({"event": "source_refused", "kind": kind, "source_type": source_type,
                               "uri": uri, "reason": reason}))


def require_capture(source_type: str, uri: str) -> None:
    """Raise SourceNotAllowed if an allowlist is active and does not allow this capture."""
    allow = active()
    if allow is None:
        return
    ok, reason = allow.check(source_type, uri)
    if not ok:
        _log_refusal("capture", source_type, uri, reason)
        raise SourceNotAllowed(reason)


def require_url(url: str) -> None:
    """Raise SourceNotAllowed if an allowlist is active and does not allow downloading from ``url``."""
    allow = active()
    if allow is None:
        return
    ok, reason = allow.check_url(url)
    if not ok:
        _log_refusal("download", None, url, reason)
        raise SourceNotAllowed(reason)
