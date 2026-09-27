# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""G17: Baseline regression — the home domain did not break after F31.2.4."""
import os

os.environ.setdefault("TENANT_ID", "test-tenant")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/v")


def test_home_section_renderers_not_broken():
    from exocortex.wiki.domains.home import (
        _DEFAULT_HOME_SECTION_ORDER,
        _HOME_SECTION_RENDERERS,
    )

    assert "today" in _HOME_SECTION_RENDERERS
    assert "resurfacing" in _HOME_SECTION_RENDERERS
    assert "news_pulse" in _HOME_SECTION_RENDERERS
    assert "resurfacing" in _DEFAULT_HOME_SECTION_ORDER
    for sid in _DEFAULT_HOME_SECTION_ORDER:
        assert sid in _HOME_SECTION_RENDERERS, f"section {sid!r} missing renderer"


def test_render_resurfacing_empty_path():
    from exocortex.wiki.domains.home import _render_section_resurfacing

    assert _render_section_resurfacing({}) == []


def test_render_resurfacing_missing_file():
    from exocortex.wiki.domains.home import _render_section_resurfacing

    result = _render_section_resurfacing(
        {"_resurfacing_md_path": "/nonexistent/path.md"}
    )
    assert result == []


def test_render_resurfacing_with_links(tmp_path):
    from exocortex.wiki.domains.home import _render_section_resurfacing

    resurfacing_md = tmp_path / "resurfacing.md"
    resurfacing_md.write_text("- [[note/foo|Bar]]\n- [[note/baz|Qux]]\n")
    d = {"_resurfacing_md_path": str(resurfacing_md)}
    result = _render_section_resurfacing(d)
    assert any("Wraca do ciebie" in line for line in result)
    assert any("note/foo" in line for line in result)
    assert any("note/baz" in line for line in result)


def test_render_resurfacing_idempotent(tmp_path):
    from exocortex.wiki.domains.home import _render_section_resurfacing

    resurfacing_md = tmp_path / "resurfacing.md"
    resurfacing_md.write_text("- [[note/foo|Bar]]\n- [[note/baz|Qux]]\n")
    d = {"_resurfacing_md_path": str(resurfacing_md)}
    r1 = _render_section_resurfacing(d)
    r2 = _render_section_resurfacing(d)
    assert r1 == r2


# ── F31.5.4: Gap Radar home section ──────────────────────────────────


def test_gap_radar_registered_in_renderers_and_order():
    from exocortex.wiki.domains.home import (
        _DEFAULT_HOME_SECTION_ORDER,
        _HOME_SECTION_RENDERERS,
    )

    assert "gap_radar" in _HOME_SECTION_RENDERERS
    assert "gap_radar" in _DEFAULT_HOME_SECTION_ORDER
    assert _DEFAULT_HOME_SECTION_ORDER.index(
        "gap_radar"
    ) > _DEFAULT_HOME_SECTION_ORDER.index("resurfacing")
    assert _DEFAULT_HOME_SECTION_ORDER.index(
        "gap_radar"
    ) < _DEFAULT_HOME_SECTION_ORDER.index("pinned")


def test_render_gap_radar_empty():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    result = _render_section_gap_radar({})
    assert any("Gap Radar" in line for line in result)
    assert any("Brak wykrytych luk" in line for line in result)


def test_render_gap_radar_empty_list():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    result = _render_section_gap_radar({"_gap_radar_gaps": []})
    assert any("Brak wykrytych luk" in line for line in result)


def test_render_gap_radar_with_gaps():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    gaps = [
        {
            "type": "cluster-no-synth",
            "title": "AI design patterns",
            "age_days": 12.5,
            "suggested_action": "synthesize cluster",
        },
        {
            "type": "no-decision",
            "title": "Postgres vs SQLite",
            "age_days": 30,
            "suggested_action": "make decision",
        },
        {
            "type": "contradiction-unresolved",
            "title": "scope creep risk",
            "age_days": 5,
            "suggested_action": "resolve",
        },
    ]
    result = _render_section_gap_radar({"_gap_radar_gaps": gaps})
    assert any("🎯 Gap Radar" in line for line in result)
    bullets = [line for line in result if line.startswith("- ")]
    assert len(bullets) == 3
    assert any("📚" in line and "AI design patterns" in line for line in bullets)
    assert any("❓" in line and "Postgres vs SQLite" in line for line in bullets)
    assert any("⚡" in line and "scope creep" in line for line in bullets)
    assert any("(12d)" in line for line in bullets)


def test_render_gap_radar_caps_at_five():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    gaps = [
        {
            "type": "stale-orphan",
            "title": f"orphan #{i}",
            "age_days": float(i),
            "suggested_action": "review",
        }
        for i in range(10)
    ]
    result = _render_section_gap_radar({"_gap_radar_gaps": gaps})
    bullets = [line for line in result if line.startswith("- ")]
    assert len(bullets) == 5


def test_render_gap_radar_unknown_type_fallback_emoji():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    gaps = [
        {
            "type": "totally-new-type",
            "title": "something",
            "age_days": 1,
            "suggested_action": "do it",
        }
    ]
    result = _render_section_gap_radar({"_gap_radar_gaps": gaps})
    assert any("🎯 **something**" in line for line in result)


def test_render_gap_radar_idempotent():
    from exocortex.wiki.domains.home import _render_section_gap_radar

    gaps = [
        {
            "type": "cluster-no-synth",
            "title": "T",
            "age_days": 3,
            "suggested_action": "x",
        },
    ]
    d = {"_gap_radar_gaps": gaps}
    assert _render_section_gap_radar(d) == _render_section_gap_radar(d)


def test_fetch_gap_radar_gaps_empty_tenant():
    from exocortex.wiki.domains.home import _fetch_gap_radar_gaps

    assert _fetch_gap_radar_gaps("") == []


def test_fetch_gap_radar_gaps_exception_returns_empty(monkeypatch):
    """Home page must not crash if gap detectors fail."""
    import exocortex.workers.gap_queries as gq
    from exocortex.wiki.domains.home import _fetch_gap_radar_gaps

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(gq, "run_all_detectors", boom)
    assert _fetch_gap_radar_gaps("test-tenant") == []


def test_fetch_gap_radar_gaps_sorted_by_age_desc(monkeypatch):
    import exocortex.workers.gap_queries as gq
    from exocortex.wiki.domains.home import _fetch_gap_radar_gaps

    fake_gaps = [
        {"type": "x", "title": "young", "age_days": 1.0, "suggested_action": "a"},
        {"type": "x", "title": "old", "age_days": 30.0, "suggested_action": "a"},
        {"type": "x", "title": "mid", "age_days": 10.0, "suggested_action": "a"},
    ]
    monkeypatch.setattr(
        gq, "run_all_detectors", lambda tenant_id, max_results=5: list(fake_gaps)
    )
    result = _fetch_gap_radar_gaps("test-tenant")
    assert [g["title"] for g in result] == ["old", "mid", "young"]
