# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/processors/recipe.py::_resolve_source_url.

Regression: a recipe note whose frontmatter has no 'url'/'uri' key (only
'source', e.g. an Instagram link, set by a web-clipper variant other than
the one bundled in vault-templates/) fell through to vault_watcher's
file:// fallback, which then leaked into the wiki page's rendered `url`
attribute as the local vault file path instead of the recipe's real
source."""
from __future__ import annotations

from exocortex.processors.recipe import _resolve_source_url


def test_resolve_source_url_prefers_source_field():
    assert _resolve_source_url({"source": "https://www.instagram.com/p/C9fFokcREYE/"}) == (
        "https://www.instagram.com/p/C9fFokcREYE/"
    )


def test_resolve_source_url_accepts_non_url_source():
    """The 'source' field may name a book/offline origin, not a URL — still
    worth surfacing verbatim rather than discarding it."""
    assert _resolve_source_url({"source": "Kuchnia polska, str. 42"}) == (
        "Kuchnia polska, str. 42"
    )


def test_resolve_source_url_missing_returns_none():
    assert _resolve_source_url({}) is None
    assert _resolve_source_url({"source": ""}) is None
    assert _resolve_source_url({"source": "   "}) is None
