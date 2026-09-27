# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/wiki/util/slugs.py::_safe_slug.

Regression coverage: a 459-char Instagram-caption "recipe title" (scraped
content, not a real title) crashed wiki_compiler's cook module with
OSError(36, 'File name too long') — _safe_slug() had no length cap, unlike
its sibling _news_slug() (already capped at 60 chars, "mirrors processor
logic"). The cap was never backported to _safe_slug, used by clippings.py
for recipe/3d_model/paper filenames and by wiki/domains/frp for person/
project slugs.
"""
from __future__ import annotations

from exocortex.wiki.util.slugs import _safe_slug, _news_slug


def test_safe_slug_transliterates_polish_diacritics():
    """Regression: 'Parówki z serem i czosnkowym masłem' compiled to
    'par-wki-z-serem-i-czosnkowym-mas-em' — ó/ł were dropped by the
    ASCII-only regex instead of being transliterated, breaking the slug."""
    assert _safe_slug("Parówki z serem i czosnkowym masłem") == (
        "parowki-z-serem-i-czosnkowym-maslem"
    )


def test_news_slug_transliterates_polish_diacritics():
    assert _news_slug("Żółć źrebięcia") == "zolc-zrebiecia"


def test_safe_slug_caps_length():
    title = "a" * 500
    slug = _safe_slug(title)
    assert len(slug) <= 60


def test_safe_slug_caps_realistic_long_title():
    """The actual production title that crashed the cook module (459 chars,
    Instagram caption scraped as a recipe title)."""
    title = (
        'Snejana Andreeva na Instagramie : "😱 Comment "recipe" and I\'ll '
        "send it. Did you know that if you roast or air fry radishes, the "
        "pepperiness goes away completely and they taste like a tangy mild "
        "garlicky potato! This low-calorie, low-carb, high-fiber veggie "
        "side bursts with vitamin C, plant-based nutrients, and heart-"
        "healthy fats. Perfect for vegan, gluten-free, clean eating and "
        "weight loss! Ready in just 15 minutes, it's an easy, quick, "
        "healthy side dish."
    )
    slug = _safe_slug(title)
    assert len(slug) <= 60
    # filename = f"{slug}.md" must stay well under the 255-byte ext4 limit
    assert len(slug) + len(".md") < 255


def test_safe_slug_no_trailing_hyphen_after_truncation():
    title = "word " * 20  # truncation may land right on a "-" boundary
    slug = _safe_slug(title)
    assert not slug.endswith("-")


def test_safe_slug_short_title_unaffected():
    assert _safe_slug("Chicken Soup") == "chicken-soup"


def test_safe_slug_empty_input_returns_empty():
    assert _safe_slug("") == ""
    assert _safe_slug(None) == ""
