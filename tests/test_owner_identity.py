# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Regression: the wiki 'Moje TODO' (+ home dashboard action items, live
sections 'my open') rendered EMPTY because owner filters matched only the
anonymized placeholder slugs ('vault-owner'/'exocortex_user'), while meeting
notes carry the real name 'Eryk Orłowski' → slug 'eryk-orlowski'. The real
identity is injected via EXOCORTEX_OWNER_NAMES; me_owner_slugs() must fold it
into the 'me' set so filters recognize the owner's items."""
from __future__ import annotations

from exocortex.action_items import (
    _ME_PLACEHOLDER_SLUGS,
    _me_identity,
    parse_action_items,
)


def test_configured_owner_folds_into_me_slugs():
    slugs, names = _me_identity("Eryk Orłowski,Eryk")
    # real name slugified exactly as parse_action_items would slugify the header
    assert "eryk-orlowski" in slugs
    assert "eryk" in slugs
    # placeholders preserved (public-repo default still matches)
    assert set(_ME_PLACEHOLDER_SLUGS) <= slugs
    assert "Eryk Orłowski" in names


def test_empty_config_is_placeholders_only():
    slugs, _ = _me_identity("")
    assert slugs == frozenset(_ME_PLACEHOLDER_SLUGS)


def test_owner_filter_matches_real_name_header():
    md = (
        "### Eryk Orłowski\n\n"
        "- [ ] Zrobić X (01:00)\n"
        "- [ ] Zrobić Y\n"
        "### Iga Sowa\n\n"
        "- [ ] Coś jej (02:00)\n"
    )
    items = parse_action_items(md, source_thought_id="t1")
    me = _me_identity("Eryk Orłowski")[0]
    mine = [i for i in items if i.status == "open" and i.owner_slug in me]
    assert len(mine) == 2
    assert {i.content for i in mine} == {"Zrobić X", "Zrobić Y"}


def test_whitespace_and_blanks_in_config_ignored():
    slugs, _ = _me_identity("  Eryk Orłowski , ,  ")
    assert "eryk-orlowski" in slugs
    # no empty-string slug leaked in
    assert "" not in slugs
    assert "unknown" not in slugs
