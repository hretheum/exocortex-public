# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/processors/claude_session.py.

The processor turns one already-redacted session body into a `claude_session`
thought: summary, decisions, mistakes-with-cause, touched areas. Two things
matter beyond "it calls the LLM": it must feed the model the stored body (not
re-read files), and re-processing must not fabricate — an empty LLM field
falls back rather than overwriting with junk (lesson from recipe._resolve_title).
"""
from __future__ import annotations

from exocortex.processors import claude_session as proc


def _source(body="## Użytkownik\nNapraw X\n\n## Claude\nZrobione.", title="Naprawa X"):
    return {
        'id': 'src-1',
        'uri': 'claude-session://sid-abc',
        'title': title,
        'metadata': {'raw_payload': body, 'session_id': 'sid-abc',
                     'redaction_verdict': 'clean', 'domain': 'sb'},
    }


def _llm_ok():
    return ({
        'summary_pl': 'Naprawiono X, dopięto timer.',
        'decisions': ['Timer o 22:45', 'Bramka we wszystkich przebiegach'],
        'mistakes': [{'what': 'Podpiąłem do złego dyspozytora',
                      'cause': 'Są dwa, myślałem że jeden'}],
        'touched': ['exocortex/sources', 'deploy/quadlet'],
    }, {'input_tokens': 100, 'output_tokens': 50, '_cost_usd': 0.0})


def test_happy_path_emits_thought(monkeypatch):
    captured = {}
    monkeypatch.setattr(proc, 'already_processed', lambda *a, **k: False)
    monkeypatch.setattr(proc, 'fetch_source', lambda *a, **k: _source())
    monkeypatch.setattr(proc, 'call_tool', lambda *a, **k: _llm_ok())
    monkeypatch.setattr(proc, 'estimate_cost_usd', lambda *a, **k: 0.0)
    monkeypatch.setattr(proc, 'mark_processed', lambda *a, **k: None)
    monkeypatch.setattr(proc, 'emit_thought_for_source',
                        lambda **kw: (captured.update(kw), 'tid-1')[1])

    out = proc.process('src-1')
    assert out['status'] == 'ok'
    assert captured['thought_type'] == 'claude_session'
    assert captured['domain'] == 'sb'
    body = captured['body']
    assert 'Naprawiono X' in body
    # mistakes-with-cause are the whole point — they must render
    assert 'Podpiąłem do złego dyspozytora' in body


def test_llm_receives_stored_body_not_a_reread(monkeypatch):
    seen = {}
    monkeypatch.setattr(proc, 'already_processed', lambda *a, **k: False)
    monkeypatch.setattr(proc, 'fetch_source', lambda *a, **k: _source(body="UNIKALNY_MARKER_TRESCI"))
    monkeypatch.setattr(proc, 'estimate_cost_usd', lambda *a, **k: 0.0)
    monkeypatch.setattr(proc, 'mark_processed', lambda *a, **k: None)
    monkeypatch.setattr(proc, 'emit_thought_for_source', lambda **kw: 'tid-1')

    def _capture_prompt(system, user, schema, **k):
        seen['user'] = user
        return _llm_ok()
    monkeypatch.setattr(proc, 'call_tool', _capture_prompt)

    proc.process('src-1')
    assert 'UNIKALNY_MARKER_TRESCI' in seen['user']


def test_already_processed_short_circuits(monkeypatch):
    monkeypatch.setattr(proc, 'already_processed', lambda *a, **k: True)
    called = {'llm': False}
    monkeypatch.setattr(proc, 'fetch_source', lambda *a, **k: _source())
    monkeypatch.setattr(proc, 'call_tool',
                        lambda *a, **k: called.update(llm=True) or _llm_ok())
    out = proc.process('src-1')
    assert out['status'] == 'skipped'
    assert called['llm'] is False, 'nie wolno wolac LLM dla juz przetworzonego'


def test_missing_source_returns_error(monkeypatch):
    monkeypatch.setattr(proc, 'already_processed', lambda *a, **k: False)
    monkeypatch.setattr(proc, 'fetch_source', lambda *a, **k: None)
    out = proc.process('nieistnieje')
    assert out['status'] == 'error'


def test_empty_body_short_circuits_before_llm(monkeypatch):
    monkeypatch.setattr(proc, 'already_processed', lambda *a, **k: False)
    monkeypatch.setattr(proc, 'fetch_source',
                        lambda *a, **k: _source(body='   '))
    llm = {'called': False}
    monkeypatch.setattr(proc, 'call_tool',
                        lambda *a, **k: llm.update(called=True) or _llm_ok())
    out = proc.process('src-1')
    assert out['status'] == 'error'
    assert llm['called'] is False


# ── long sessions: clip must stay within the limit, marker included ────────

def test_clip_respects_limit_including_marker():
    """Regression: the head+tail split forgot the join marker's length, so a
    clipped body came out ~45 chars over the cap — a silent context overflow
    on the largest sessions."""
    from exocortex.processors.claude_session import _MAX_BODY_CHARS, _clip
    body = "x" * (_MAX_BODY_CHARS * 3)
    out = _clip(body)
    assert len(out) <= _MAX_BODY_CHARS
    assert out.startswith("x")
    assert out.endswith("x")
    assert "pominięty" in out


def test_clip_leaves_short_body_untouched():
    from exocortex.processors.claude_session import _clip
    body = "krótka sesja"
    assert _clip(body) == body
