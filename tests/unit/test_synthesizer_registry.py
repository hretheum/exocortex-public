# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for the synth perspectives registry layer (F31.7.3)."""
from __future__ import annotations

import os

# synthesizer.py calls get_tenant_id() at import time; set before any import
# that could trigger it.
os.environ.setdefault("TENANT_ID", "test-tenant")

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from exocortex.core.registry import Registry
from exocortex.synth.perspectives.base import PerspectiveType, _LegacyWrapper
from exocortex.synth.runner import SynthContext, setup_builtins


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(key: str = "test-key", tenant: str = "t1") -> SynthContext:
    return SynthContext(tenant_id=tenant, perspective_key=key)


def _fake_thoughts(n: int = 3) -> list[dict]:
    return [
        {
            "id": f"00000000-0000-0000-0000-00000000000{i}",
            "thought_type": "work_meeting_note",
            "body": f"Body of thought {i}",
            "created_at": f"2026-01-0{i}T10:00:00",
            "metadata": {"date": f"2026-01-0{i}", "title": f"Meeting {i}"},
            "extracted_tags": {},
        }
        for i in range(1, n + 1)
    ]


# ── SynthContext defaults ─────────────────────────────────────────────────────

def test_synth_context_defaults():
    ctx = SynthContext(tenant_id="t1", perspective_key="key")
    assert ctx.edges == []
    assert ctx.dry_run is False
    assert ctx.force is False


def test_synth_context_optional_fields_can_be_set():
    ctx = SynthContext(tenant_id="t1", perspective_key="key",
                      edges=[{"type": "test"}], dry_run=True, force=True)
    assert len(ctx.edges) == 1
    assert ctx.dry_run is True
    assert ctx.force is True


# ── _LegacyWrapper contract ───────────────────────────────────────────────────

class _Stub(_LegacyWrapper):
    _legacy_type = "stub"

    @property
    def name(self) -> str:
        return "stub"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        self._ctx = ctx
        return []


def test_legacy_wrapper_is_perspective_type():
    assert issubclass(_Stub, PerspectiveType)


def test_legacy_wrapper_build_prompt_before_select_thoughts_raises():
    stub = _Stub()
    with pytest.raises(RuntimeError, match="select_thoughts"):
        stub.build_prompt(_fake_thoughts(1))


def test_legacy_wrapper_parse_response_delegates():
    stub = _Stub()
    raw = {"current_state": "hello", "recent_decisions": [], "open_problems": [],
           "ownership": [], "next_steps": []}
    with patch("exocortex.synthesizer._coerce_synthesis", return_value=raw) as mock_fn:
        result = stub.parse_response(raw)
    mock_fn.assert_called_once_with(raw)
    assert result == raw


def test_legacy_wrapper_build_prompt_delegates():
    stub = _Stub()
    ctx = _make_ctx()
    stub._ctx = ctx
    thoughts = _fake_thoughts(2)
    sentinel = "generated prompt"
    with patch("exocortex.synthesizer.build_user_prompt", return_value=sentinel) as mock_fn:
        result = stub.build_prompt(thoughts)
    mock_fn.assert_called_once_with(
        "stub", ctx.perspective_key, thoughts, [], tenant_id=ctx.tenant_id
    )
    assert result == sentinel


def test_legacy_wrapper_build_prompt_passes_edges_from_ctx():
    stub = _Stub()
    edges = [{"type": "attended_meeting", "dst_id": "abc"}]
    ctx = SynthContext(tenant_id="t1", perspective_key="k", edges=edges)
    stub._ctx = ctx
    with patch("exocortex.synthesizer.build_user_prompt", return_value="") as mock_fn:
        stub.build_prompt(_fake_thoughts(1))
    _, _, _, actual_edges = mock_fn.call_args[0]
    assert actual_edges is edges


# ── setup_builtins registers all 10 named perspectives ───────────────────────

EXPECTED_PERSPECTIVES = {
    "client_review",
    "weekly_review",
    "person_profile",
    "monthly_review",
    "decision_log",
    "meeting_summary",
    "action_items_thread",
    "news_cluster",
    "frp_per_frame",
    "frp_per_domain",
    "frp_evolution_timeline",
    "frp_per_resonance",
    "frp_session",
}


def test_setup_builtins_registers_all_perspectives():
    reg = Registry()
    setup_builtins(reg)
    assert EXPECTED_PERSPECTIVES.issubset(set(reg.perspectives.keys()))


def test_setup_builtins_all_are_perspective_type_instances():
    reg = Registry()
    setup_builtins(reg)
    for name, p in reg.perspectives.items():
        assert isinstance(p, PerspectiveType), f"{name!r} is not a PerspectiveType"


def test_setup_builtins_all_have_legacy_type():
    reg = Registry()
    setup_builtins(reg)
    for name, p in reg.perspectives.items():
        if isinstance(p, _LegacyWrapper):
            assert p._legacy_type, f"{name!r}: _legacy_type is empty"


def test_setup_builtins_idempotent_keys():
    """Calling setup_builtins twice should just overwrite — no crash."""
    reg = Registry()
    setup_builtins(reg)
    count1 = len(reg.perspectives)
    setup_builtins(reg)
    assert len(reg.perspectives) == count1


# ── Individual perspective files expose setup(registry) ─────────────────────

@pytest.mark.parametrize("module_name,expected_names", [
    ("exocortex.synth.perspectives.client_review", ["client_review"]),
    ("exocortex.synth.perspectives.weekly_review", ["weekly_review"]),
    ("exocortex.synth.perspectives.person_profile", ["person_profile"]),
    ("exocortex.synth.perspectives.monthly_review", ["monthly_review"]),
    ("exocortex.synth.perspectives.decision_log", ["decision_log"]),
    ("exocortex.synth.perspectives.meeting_summary", ["meeting_summary"]),
    ("exocortex.synth.perspectives.action_items_thread", ["action_items_thread"]),
    ("exocortex.synth.perspectives.news_cluster", ["news_cluster"]),
    (
        "exocortex.synth.perspectives.frp_perspective",
        ["frp_per_frame", "frp_per_domain", "frp_evolution_timeline", "frp_per_resonance"],
    ),
    ("exocortex.synth.perspectives.frp_session", ["frp_session"]),
])
def test_perspective_module_setup(module_name, expected_names):
    import importlib
    mod = importlib.import_module(module_name)
    reg = Registry()
    mod.setup(reg)
    for name in expected_names:
        assert name in reg.perspectives, f"'{name}' not registered by {module_name}"
        p = reg.perspectives[name]
        assert isinstance(p, PerspectiveType)
        assert p.name == name


# ── select_thoughts stores ctx in _ctx ───────────────────────────────────────

def test_select_thoughts_stores_ctx():
    from exocortex.synth.perspectives.client_review import ClientReview
    p = ClientReview()
    ctx = _make_ctx()
    with patch("exocortex.synthesizer._select_thoughts_for_client", return_value=[]):
        p.select_thoughts(ctx)
    assert p._ctx is ctx


# ── runner.run() routes to synthesizer via legacy_type ───────────────────────

def test_runner_run_unknown_perspective():
    from exocortex.synth.runner import run
    reg = Registry()
    setup_builtins(reg)
    result = run(reg, "does_not_exist", "key")
    assert result.status == "error"
    assert "does_not_exist" in result.reason


def test_runner_run_delegates_to_synthesize():
    from exocortex.synth.runner import run
    reg = Registry()
    setup_builtins(reg)

    sentinel = MagicMock()
    sentinel.status = "ok"
    with patch("exocortex.synthesizer.synthesize", return_value=sentinel) as mock_synth:
        result = run(reg, "client_review", "acme", dry_run=True)

    mock_synth.assert_called_once_with(
        "client",   # legacy_type for client_review
        "acme",
        source_thoughts=None,
        tenant_id=None,
        dry_run=True,
        force=False,
    )
    assert result is sentinel


# ── No acme/globex in public perspectives package ─────────────────────────────

def test_no_acme_or_globex_in_synth_package(tmp_path):
    """grep-equivalent: no 'globex' or 'acme_pillar' in exocortex/synth/ source."""
    import pathlib
    synth_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "synth"
    forbidden = {"globex", "acme_pillar", "acme_topic", "acme_concept"}
    violations: list[str] = []
    for py_file in synth_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for word in forbidden:
            if word in text:
                violations.append(f"{py_file.name}: contains '{word}'")
    assert violations == [], "\n".join(violations)
