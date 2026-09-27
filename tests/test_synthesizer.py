# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.5.2 — tests for `gap_radar` perspective_type wiring in synthesizer."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")


TENANT = "00000000-0000-0000-0000-000000000000"


_FAKE_GAPS = [
    {
        "type": "cluster-no-synth",
        "title": "Klaster 'globex' bez syntezy (8 thoughts)",
        "thought_ids": ["uuid-a", "uuid-b"],
        "age_days": 12.0,
        "suggested_action": "Zsyntetyzuj klaster 'globex'",
        "meta": {"tag": "globex", "thought_count": 8},
    },
    {
        "type": "stale-orphan",
        "title": "Stary thought bez połączeń",
        "thought_ids": ["uuid-c"],
        "age_days": 60.0,
        "suggested_action": "Połącz z innymi myślami lub archiwizuj",
        "meta": {"edge_count": 0},
    },
]


def test_gap_radar_registered_in_perspective_types():
    from exocortex import synthesizer
    assert "gap_radar" in synthesizer.PERSPECTIVE_TYPES
    assert synthesizer.THRESHOLDS.get("gap_radar") == 1
    assert "gap_radar" in synthesizer._SELECTORS


def test_select_gap_radar_returns_thought_like_dicts():
    from exocortex import synthesizer
    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ):
        thoughts = synthesizer._select_gap_radar(TENANT, "weekly")

    assert len(thoughts) == 2
    for t in thoughts:
        # Fields required by the synthesizer pipeline + tests.
        assert "id" in t
        assert "title" in t
        assert "content" in t
        assert "body" in t  # for _thought_body_hash
        assert t["thought_type"] == "gap_finding"
        assert t["provenance"] == "ai_authored"
        assert isinstance(t["tags"], list)
        assert "_gap" in t  # full Gap dict preserved
    # Real underlying thought UUIDs are reachable from _gap["thought_ids"].
    assert thoughts[0]["_gap"]["thought_ids"] == ["uuid-a", "uuid-b"]


def test_build_gap_radar_prompt_includes_gap_titles():
    from exocortex.synthesizer import _build_gap_radar_prompt

    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ):
        from exocortex.synthesizer import _select_gap_radar
        thoughts = _select_gap_radar(TENANT, "weekly")

    prompt = _build_gap_radar_prompt(thoughts, "weekly")

    # Polish task framing.
    assert "luk w wiedzy" in prompt
    # All gap titles surface in the prompt.
    for g in _FAKE_GAPS:
        assert g["title"] in prompt
    # Expected JSON schema fields mentioned.
    assert "narrative_pl" in prompt
    assert "top_gaps" in prompt
    assert "total_gaps_count" in prompt


def test_build_user_prompt_dispatches_to_gap_radar():
    """`build_user_prompt('gap_radar', ...)` must short-circuit to the gap prompt
    (it would otherwise blow up on pseudo-thoughts that lack the legacy
    meeting/news/frp shape).
    """
    from exocortex.synthesizer import build_user_prompt

    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ):
        from exocortex.synthesizer import _select_gap_radar
        thoughts = _select_gap_radar(TENANT, "weekly")

    prompt = build_user_prompt("gap_radar", "weekly", thoughts, edges=[])
    assert "luk w wiedzy" in prompt
    assert _FAKE_GAPS[0]["title"] in prompt
