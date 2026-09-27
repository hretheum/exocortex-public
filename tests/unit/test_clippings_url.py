# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/wiki/domains/clippings.py::_clipping_url.

Regression: _write_clipping_page rendered `"url": md.get("uri")` verbatim.
For recipes without a real source URL, `uri` is vault_watcher's file://
fallback (the local vault path) — that should never be surfaced as the
page's `url` attribute. When a processor supplies an explicit `source_url`
(the real origin, e.g. Instagram), that must win over `uri`."""
from __future__ import annotations

from exocortex.wiki.domains.clippings import _clipping_url


def test_clipping_url_prefers_source_url():
    md = {"source_url": "https://www.instagram.com/p/C9fFokcREYE/", "uri": "file:///vault/x.md"}
    assert _clipping_url(md) == "https://www.instagram.com/p/C9fFokcREYE/"


def test_clipping_url_filters_out_file_uri_fallback():
    md = {"uri": "file:///vault/_source/prv/kukbuk/Par%C3%B3wki.md"}
    assert _clipping_url(md) is None


def test_clipping_url_keeps_real_uri_for_articles():
    md = {"uri": "https://example.com/some-article"}
    assert _clipping_url(md) == "https://example.com/some-article"


def test_clipping_url_missing_returns_none():
    assert _clipping_url({}) is None
