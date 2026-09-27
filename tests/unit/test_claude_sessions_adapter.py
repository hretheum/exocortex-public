# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/sources/claude_sessions.py.

The adapter reads a Claude Code `.jsonl`, keeps only the dialogue (user
prompts + assistant prose), runs it through fail-closed redaction, and hands
back a capture payload — or nothing, if the session is refused. It must never
carry `tool_result`/`tool_use` content forward (that is where secrets and
bulk live), and a refused session must produce no payload at all.

Fixtures are synthetic `.jsonl` built inline — the tests never touch
~/.claude/projects/.
"""
from __future__ import annotations

import json

from exocortex.sources import claude_sessions as cs


def _write_session(tmp_path, records, name="sess-1.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return p


def _rec(type_, content, role=None):
    m = {"content": content}
    if role:
        m["role"] = role
    return {"type": type_, "message": m, "sessionId": "sid-abc"}


# ── dialogue extraction ────────────────────────────────────────────────────

def test_extracts_user_prompt_and_assistant_text(tmp_path):
    p = _write_session(tmp_path, [
        {"type": "ai-title", "aiTitle": "Naprawa bramki", "sessionId": "sid-abc"},
        _rec("user", "Napraw bramkę miodka.", role="user"),
        _rec("assistant", [{"type": "thinking", "thinking": "hmm"},
                           {"type": "text", "text": "Zrobione, dopiąłem timer."}],
             role="assistant"),
    ])
    out = cs.build_payload(p)
    assert out is not None
    body = out["metadata"]["raw_payload"]
    assert "Napraw bramkę miodka." in body
    assert "Zrobione, dopiąłem timer." in body


def test_tool_result_and_tool_use_are_dropped(tmp_path):
    p = _write_session(tmp_path, [
        _rec("user", "Uruchom testy.", role="user"),
        _rec("assistant", [{"type": "tool_use", "name": "Bash",
                            "input": {"command": "pytest"}}], role="assistant"),
        _rec("user", [{"type": "tool_result",
                       "content": "SEKRET_W_OUTPUCIE_KOMENDY_xyz"}], role="user"),
        _rec("assistant", [{"type": "text", "text": "Testy zielone."}],
             role="assistant"),
    ])
    out = cs.build_payload(p)
    body = out["metadata"]["raw_payload"]
    assert "SEKRET_W_OUTPUCIE" not in body, "tool_result nie moze wejsc do body"
    assert "pytest" not in body, "tool_use input tez nie"
    assert "Uruchom testy." in body
    assert "Testy zielone." in body


def test_title_and_uri_come_from_session(tmp_path):
    p = _write_session(tmp_path, [
        {"type": "ai-title", "aiTitle": "Tytuł sesji", "sessionId": "sid-abc"},
        _rec("user", "coś", role="user"),
        _rec("assistant", [{"type": "text", "text": "odp"}], role="assistant"),
    ])
    out = cs.build_payload(p)
    assert out["source_type"] == "claude-session"
    assert out["uri"] == "claude-session://sid-abc"
    assert out["title"] == "Tytuł sesji"


def test_session_without_ai_title_falls_back(tmp_path):
    p = _write_session(tmp_path, [
        _rec("user", "coś", role="user"),
        _rec("assistant", [{"type": "text", "text": "odp"}], role="assistant"),
    ])
    out = cs.build_payload(p)
    assert out["title"]  # some non-empty fallback, never crashes


# ── redaction is wired in, before anything is returned ─────────────────────

def test_refused_session_yields_no_payload(tmp_path):
    p = _write_session(tmp_path, [
        _rec("user", 'ustaw password = jakas_nieprzejrzysta_wartosc', role="user"),
        _rec("assistant", [{"type": "text", "text": "ok"}], role="assistant"),
    ])
    out = cs.build_payload(p)
    assert out is None, "sesja z refuse nie moze dac payloadu"


def test_redacted_secret_absent_from_payload(tmp_path):
    p = _write_session(tmp_path, [
        _rec("user", "token: ghp_FAKE0000000000000000000000000000000000",
             role="user"),
        _rec("assistant", [{"type": "text", "text": "ok"}], role="assistant"),
    ])
    out = cs.build_payload(p)
    assert out is not None
    assert "ghp_FAKE" not in out["metadata"]["raw_payload"]
    assert out["metadata"]["redaction_verdict"] == "redacted"


# ── empty / dialogue-free sessions ─────────────────────────────────────────

def test_session_with_no_dialogue_yields_no_payload(tmp_path):
    p = _write_session(tmp_path, [
        _rec("user", [{"type": "tool_result", "content": "x"}], role="user"),
    ])
    assert cs.build_payload(p) is None


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "sess.jsonl"
    p.write_text(
        "{ this is not json\n"
        + json.dumps(_rec("user", "prawdziwy prompt", role="user")) + "\n"
        + json.dumps(_rec("assistant", [{"type": "text", "text": "odp"}],
                          role="assistant")) + "\n",
        encoding="utf-8")
    out = cs.build_payload(p)
    assert out is not None
    assert "prawdziwy prompt" in out["metadata"]["raw_payload"]
