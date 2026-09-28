# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for F31.1.3 night_shift_briefing orchestrator."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TENANT_ID", "test-tenant")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

import pytest

from workers import night_shift_briefing as nsb


@pytest.fixture(autouse=True)
def _stub_pipeline_log(monkeypatch):
    """night_shift_briefing.run() now reports to pipeline_log (F14) — stub
    it out by default so unit tests never touch the real DB. Tests that
    assert on the wiring itself override with their own patch."""
    monkeypatch.setattr("exocortex.pipeline_log.log_run_start",
                        lambda *a, **k: None)
    monkeypatch.setattr("exocortex.pipeline_log.log_run_end",
                        lambda *a, **k: None)


# ─────────────────────────── Telegram formatting ───────────────────────────


def test_escape_md_v2_escapes_reserved_chars():
    out = nsb._escape_md_v2("a.b(c)d!")
    assert out == "a\\.b\\(c\\)d\\!"


def test_escape_md_v2_passes_through_safe_chars():
    assert nsb._escape_md_v2("abc 123 XYZ") == "abc 123 XYZ"


def test_format_telegram_message_full_payload():
    content = {
        "narrative_pl": "Dziś dużo o AI. Klienci pytali o roadmapę.",
        "patterns": ["tag spike: AI x5 (ratio 4.2)", "embedding drift: 0.42"],
        "contradictions_list": ["Plan A vs Plan B", "ETA 2026-06 vs 2026-05"],
        "action_items_due": ["Zadanie X (due: 2026-05-20)"],
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    # Headline + sections present.
    assert "Nocna Zmiana" in text
    assert "2026\\-05\\-24" in text  # date is MD-v2 escaped
    # Sections render with bold + bullets.
    assert "*Wzorce" in text
    assert "*Sprzeczności:*" in text
    assert "*Przeterminowane zadania:*" in text
    # Narrative present (dot escaped).
    assert "Dziś dużo o AI" in text


def test_format_telegram_message_skips_empty_sections():
    content = {
        "narrative_pl": "Spokojny dzień.",
        "patterns": [],
        "contradictions_list": [],
        "action_items_due": [],
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    assert "Spokojny dzień" in text
    assert "Wzorce" not in text
    assert "Sprzeczności" not in text
    assert "Przeterminowane" not in text


def test_format_telegram_message_uses_fallback_narrative_when_blank():
    content = {
        "narrative_pl": "", "patterns": [], "contradictions_list": [],
        "action_items_due": [],
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    assert "Brak istotnych wzorców" in text


def test_format_telegram_message_caps_at_max_chars():
    long_items = [f"item-{i}-" + ("x" * 200) for i in range(50)]
    content = {
        "narrative_pl": "x" * 5000,
        "patterns": long_items,
        "contradictions_list": [], "action_items_due": [],
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    assert len(text) <= nsb.TELEGRAM_MAX_CHARS + 2  # +"\n…"
    assert text.endswith("…")


def test_format_telegram_message_shows_degraded_marker():
    content = {
        "narrative_pl": "LLM niedostępny — surowy podgląd.",
        "patterns": [], "contradictions_list": [], "action_items_due": [],
        "_meta": {"degraded": True},
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    assert "awaryjny" in text.lower()


def test_format_telegram_message_no_marker_when_not_degraded():
    content = {
        "narrative_pl": "Spokojny dzień.",
        "patterns": [], "contradictions_list": [], "action_items_due": [],
        "_meta": {"degraded": False},
    }
    text = nsb.format_telegram_message(content, "2026-05-24")
    assert "awaryjny" not in text.lower()


# ─────────────────────────── Content normalization ───────────────────────────


def test_normalize_content_full_dict():
    raw = {
        "narrative_pl": "  hello  ",
        "contradictions_list": ["a", "", "b"],
        "action_items_due": ["x"],
        "patterns": ["p1", "p2"],
    }
    out = nsb._normalize_content(raw)
    assert out["narrative_pl"] == "hello"
    assert out["contradictions_list"] == ["a", "b"]
    assert out["action_items_due"] == ["x"]
    assert out["patterns"] == ["p1", "p2"]


def test_normalize_content_falls_back_when_empty():
    out = nsb._normalize_content({})
    assert out["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."
    assert out["contradictions_list"] == []
    assert out["action_items_due"] == []
    assert out["patterns"] == []


def test_normalize_content_handles_non_dict():
    out = nsb._normalize_content("not a dict")
    assert out["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."


def test_normalize_content_coerces_non_list_fields():
    out = nsb._normalize_content({
        "narrative_pl": "ok",
        "contradictions_list": "not-a-list",
        "action_items_due": 42,
        "patterns": None,
    })
    assert out["narrative_pl"] == "ok"
    assert out["contradictions_list"] == []
    assert out["action_items_due"] == []
    assert out["patterns"] == []


# ─────────────────────────── Data gathering ───────────────────────────


def test_fetch_new_thoughts_uses_24h_window_sql():
    with patch("exocortex.db.query") as q:
        q.return_value = [
            {
                "id": "abc-123",
                "body": "x",
                "metadata": {"title": "Spotkanie"},
                "thought_type": "work_meeting_note",
                "created_at": "2026-05-24T10:00:00",
            }
        ]
        out = nsb.fetch_new_thoughts(window_hours=24)
    sql_called = q.call_args[0][0]
    assert "INTERVAL '24 hours'" in sql_called
    assert "FROM thoughts" in sql_called
    assert len(out) == 1
    assert out[0]["title"] == "Spotkanie"


def test_fetch_new_contradictions_with_since_filters_by_timestamp():
    with patch("exocortex.db.query") as q:
        q.return_value = [{
            "src_id": "11111111-1111-1111-1111-111111111111",
            "src_type": "thought",
            "dst_id": "22222222-2222-2222-2222-222222222222",
            "dst_type": "thought",
            "created_at": "2026-05-23T08:00:00",
        }]
        out = nsb.fetch_new_contradictions(since_iso="2026-05-23T00:00:00")
    sql_called = q.call_args[0][0]
    assert "created_at > %s" in sql_called
    assert "type = 'contradicts'" in sql_called
    assert "resolved IS NOT TRUE" in sql_called
    assert len(out) == 1


def test_fetch_new_contradictions_without_since_falls_back_to_24h():
    with patch("exocortex.db.query") as q:
        q.return_value = []
        nsb.fetch_new_contradictions(since_iso=None)
    sql_called = q.call_args[0][0]
    assert "INTERVAL '24 hours'" in sql_called


def test_fetch_overdue_actions_returns_past_due_items():
    with patch("exocortex.db.query") as q:
        q.return_value = [
            {
                "id": "t1",
                "metadata": {
                    "title": "Old task",
                    "due_date": "2026-05-01",
                },
                "body": "",
            },
            {
                "id": "t2",
                "metadata": {
                    "action_items": [
                        {"content": "Subtask Y", "due_date": "2026-05-10",
                         "status": "open"},
                        {"content": "Done item", "due_date": "2026-04-01",
                         "status": "done"},
                    ],
                },
                "body": "",
            },
        ]
        out = nsb.fetch_overdue_actions(now_iso="2026-05-24")
    assert any("Old task" in x for x in out)
    assert any("Subtask Y" in x for x in out)
    assert not any("Done item" in x for x in out)


def test_fetch_overdue_actions_degraded_mode_on_db_error():
    with patch("exocortex.db.query", side_effect=RuntimeError("db down")):
        out = nsb.fetch_overdue_actions()
    assert out == []


# ─────────────────────────── Orchestration ───────────────────────────


def test_build_inputs_assembles_full_payload():
    with patch("workers.night_shift_briefing.fetch_new_thoughts") as t, \
         patch("workers.night_shift_briefing.fetch_new_contradictions") as c, \
         patch("workers.night_shift_briefing.fetch_overdue_actions") as o, \
         patch("workers.night_shift_briefing.get_last_briefing_time",
               return_value="2026-05-23T05:00:00"), \
         patch("exocortex.pattern_detector.detect_patterns") as p:
        t.return_value = [{"id": "x", "title": "T", "body": "b",
                           "thought_type": "x", "metadata": {}}]
        c.return_value = [{
            "src_id": "11111111-1111-1111-1111-111111111111",
            "src_type": "thought",
            "dst_id": "22222222-2222-2222-2222-222222222222",
            "dst_type": "thought",
            "created_at": "2026-05-24T01:00:00",
        }]
        o.return_value = ["Task X (due: 2026-05-20)"]
        p.return_value = [
            {"term": "AI", "spike_ratio": 4.0, "frequency_now": 5,
             "drift_score": 0.0},
            {"term": "_embedding_drift", "drift_score": 0.42,
             "spike_ratio": 0.0, "frequency_now": 10},
        ]
        out = nsb.build_inputs()
    assert out["new_thoughts"][0]["title"] == "T"
    assert any("AI" in s for s in out["pattern_spikes"])
    # The drift signal must reach the briefing, but in plain Polish — b2a9e97
    # deliberately stopped emitting "embedding drift 0.4" style jargon, and the
    # prompt now forbids it outright. Asserting the old wording kept this test
    # red; asserting its absence is what actually guards the intent.
    assert any("zmiana tematyczna" in s for s in out["pattern_spikes"])
    assert not any("embedding drift" in s for s in out["pattern_spikes"])
    assert not any("drift_score" in s or "spike_ratio" in s
                   for s in out["pattern_spikes"])
    assert out["overdue_actions"] == ["Task X (due: 2026-05-20)"]
    # "↔", not "vs" — same b2a9e97 rewrite toward human-readable output.
    assert out["new_contradictions"] and "↔" in out["new_contradictions"][0]


def test_build_inputs_pattern_detector_failure_is_non_fatal():
    with patch("workers.night_shift_briefing.fetch_new_thoughts",
               return_value=[]), \
         patch("workers.night_shift_briefing.fetch_new_contradictions",
               return_value=[]), \
         patch("workers.night_shift_briefing.fetch_overdue_actions",
               return_value=[]), \
         patch("workers.night_shift_briefing.get_last_briefing_time",
               return_value=None), \
         patch("exocortex.pattern_detector.detect_patterns",
               side_effect=RuntimeError("boom")):
        out = nsb.build_inputs()
    assert out["pattern_spikes"] == []


def test_run_no_signal_skips_llm_and_uses_empty_content(monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_CHAT_ID", raising=False)
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing") as persist, \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.call_llm") as llm:
        bi.return_value = {
            "new_thoughts": [], "new_contradictions": [],
            "overdue_actions": [], "pattern_spikes": [],
        }
        content = nsb.run(dry_run=False)
    llm.assert_not_called()
    persist.assert_called_once()
    assert content["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."
    assert content["_meta"]["degraded"] is False


def test_run_with_signal_calls_llm_and_persists():
    fake_usage = {"_cost_usd": 0.001, "_model": "test-model"}
    fake_llm_out = {
        "narrative_pl": "Wzorzec AI w 5 wpisach.",
        "contradictions_list": ["A vs B"],
        "action_items_due": [],
        "patterns": ["tag spike: AI x5"],
    }
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing") as persist, \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.call_llm",
               return_value=(fake_llm_out, fake_usage)) as llm, \
         patch("workers.night_shift_briefing.send_telegram") as tg, \
         patch.dict(os.environ,
                    {"TG_BOT_TOKEN": "tok", "TG_CHAT_ID": "1234"},
                    clear=False):
        bi.return_value = {
            "new_thoughts": [{"id": "x", "title": "T", "body": "b",
                              "thought_type": "x", "metadata": {}}],
            "new_contradictions": [],
            "overdue_actions": [],
            "pattern_spikes": ["tag spike: AI x5"],
        }
        content = nsb.run(dry_run=False)
    llm.assert_called_once()
    persist.assert_called_once()
    tg.assert_called_once()
    sent_text = tg.call_args[0][2]
    assert "Wzorzec AI" in sent_text
    assert content["narrative_pl"].startswith("Wzorzec AI")
    assert content["_meta"]["degraded"] is False


def test_run_dry_run_skips_persist_and_telegram():
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing") as persist, \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.send_telegram") as tg, \
         patch("workers.night_shift_briefing.call_llm",
               return_value=({"narrative_pl": "x", "contradictions_list": [],
                              "action_items_due": [], "patterns": []},
                             {"_cost_usd": 0, "_model": "m"})):
        bi.return_value = {
            "new_thoughts": [{"id": "x", "title": "", "body": "",
                              "thought_type": "x", "metadata": {}}],
            "new_contradictions": [], "overdue_actions": [],
            "pattern_spikes": ["x"],
        }
        nsb.run(dry_run=True)
    persist.assert_not_called()
    tg.assert_not_called()


def test_run_llm_failure_falls_back_to_raw_inputs(monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_CHAT_ID", raising=False)
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing"), \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.call_llm",
               side_effect=RuntimeError("llm offline")), \
         patch("workers.night_shift_briefing.send_telegram"):
        bi.return_value = {
            "new_thoughts": [{"id": "x", "title": "T", "body": "b",
                              "thought_type": "x", "metadata": {}}],
            "new_contradictions": ["A vs B"],
            "overdue_actions": ["Task X"],
            "pattern_spikes": ["spike"],
        }
        content = nsb.run(dry_run=False)
    assert "LLM niedostępny" in content["narrative_pl"]
    assert content["contradictions_list"] == ["A vs B"]
    assert content["patterns"] == ["spike"]
    assert content["_meta"]["degraded"] is True


def test_run_llm_failure_logs_pipeline_run_as_failure(monkeypatch):
    """The parsing failure must be visible in pipeline_log (F14), not just
    a WARNING that gets swallowed — regression test for 5 days
    of silent fallback that nobody noticed."""
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_CHAT_ID", raising=False)
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing"), \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.call_llm",
               side_effect=RuntimeError("llm offline")), \
         patch("workers.night_shift_briefing.send_telegram"), \
         patch("exocortex.pipeline_log.log_run_start",
               return_value="run-123") as start, \
         patch("exocortex.pipeline_log.log_run_end") as end:
        bi.return_value = {
            "new_thoughts": [{"id": "x", "title": "T", "body": "b",
                              "thought_type": "x", "metadata": {}}],
            "new_contradictions": [], "overdue_actions": [],
            "pattern_spikes": [],
        }
        nsb.run(dry_run=False)
    start.assert_called_once()
    end.assert_called_once()
    args, kwargs = end.call_args
    assert args[0] == "run-123"
    assert args[1] == "failure"
    error_message = kwargs.get("error_message") or (args[3] if len(args) > 3 else "")
    assert "llm offline" in error_message


def test_run_success_logs_pipeline_run_as_success(monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("EXOCORTEX_TG_CHAT_ID", raising=False)
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing"), \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.send_telegram"), \
         patch("exocortex.pipeline_log.log_run_start",
               return_value="run-123") as start, \
         patch("exocortex.pipeline_log.log_run_end") as end:
        bi.return_value = {
            "new_thoughts": [], "new_contradictions": [],
            "overdue_actions": [], "pattern_spikes": [],
        }
        nsb.run(dry_run=False)
    start.assert_called_once()
    end.assert_called_once()
    args, _ = end.call_args
    assert args[0] == "run-123"
    assert args[1] == "success"


def test_run_dry_run_skips_pipeline_log():
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing"), \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.send_telegram"), \
         patch("workers.night_shift_briefing.call_llm",
               return_value=({"narrative_pl": "x", "contradictions_list": [],
                              "action_items_due": [], "patterns": []},
                             {"_cost_usd": 0, "_model": "m"})), \
         patch("exocortex.pipeline_log.log_run_start") as start, \
         patch("exocortex.pipeline_log.log_run_end") as end:
        bi.return_value = {
            "new_thoughts": [{"id": "x", "title": "", "body": "",
                              "thought_type": "x", "metadata": {}}],
            "new_contradictions": [], "overdue_actions": [],
            "pattern_spikes": ["x"],
        }
        nsb.run(dry_run=True)
    start.assert_not_called()
    end.assert_not_called()


# ─────────────────────────── main() exit code ───────────────────────────


def test_main_returns_zero_on_clean_success():
    with patch("workers.night_shift_briefing.run",
               return_value={"narrative_pl": "ok", "_meta": {"degraded": False}}):
        rc = nsb.main(["--dry-run"])
    assert rc == 0


def test_main_returns_nonzero_when_degraded():
    with patch("workers.night_shift_briefing.run",
               return_value={"narrative_pl": "raw", "_meta": {"degraded": True}}):
        rc = nsb.main(["--dry-run"])
    assert rc != 0
    assert rc != 1  # distinct from the "hard crash" exit code


def test_main_returns_one_on_crash():
    with patch("workers.night_shift_briefing.run",
               side_effect=RuntimeError("db down")):
        rc = nsb.main(["--dry-run"])
    assert rc == 1


def test_run_skips_telegram_when_token_missing():
    with patch("workers.night_shift_briefing.build_inputs") as bi, \
         patch("workers.night_shift_briefing.persist_briefing"), \
         patch("workers.night_shift_briefing.fetch_corpus_digest",
               return_value=[]), \
         patch("workers.night_shift_briefing.send_telegram") as tg, \
         patch.dict(os.environ,
                    {"TG_BOT_TOKEN": "", "EXOCORTEX_TG_BOT_TOKEN": "",
                     "TG_CHAT_ID": "1234"}, clear=False):
        bi.return_value = {
            "new_thoughts": [], "new_contradictions": [],
            "overdue_actions": [], "pattern_spikes": [],
        }
        nsb.run(dry_run=False)
    tg.assert_not_called()


def test_send_telegram_swallows_network_error():
    from urllib import error as urlerror
    with patch("workers.night_shift_briefing.urlrequest.urlopen",
               side_effect=urlerror.URLError("unreachable")):
        # Must not raise — the briefing is already persisted.
        nsb.send_telegram("tok", 1234, "hello")


@pytest.mark.parametrize("raw,expected_substr", [
    ('```json\n{"narrative_pl":"ok","contradictions_list":[],'
     '"action_items_due":[],"patterns":[]}\n```', "ok"),
    (json.dumps({"narrative_pl": "trim me   ", "contradictions_list": [],
                 "action_items_due": [], "patterns": []}), "trim me"),
])
def test_normalize_content_does_not_crash_on_perspective_parse_outputs(
        raw, expected_substr):
    """Sanity: outputs from the perspective's own parse_response feed the
    normalizer cleanly."""
    from exocortex.synth.perspectives.night_shift import NightShiftBriefing
    parsed = NightShiftBriefing().parse_response(raw)
    out = nsb._normalize_content(parsed)
    assert expected_substr in out["narrative_pl"]


# ─────────────────────────── persist_briefing ────────────────────────────────


def test_persist_briefing_supersedes_previous_and_inserts_new():
    """UPDATE (supersede) must fire before INSERT and use the same new_id."""
    mock_c = MagicMock()
    mock_c.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_c.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn_ctx = MagicMock()
    mock_conn_ctx.__enter__ = MagicMock(return_value=mock_c)
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)

    content = {"narrative_pl": "ok", "contradictions_list": [], "action_items_due": [], "patterns": []}
    usage = {"input_tokens": 100, "output_tokens": 50, "_cost_usd": 0.001, "_model": "qwen"}

    with patch("exocortex.db.conn", return_value=mock_conn_ctx), \
         patch("exocortex.settings.get_tenant_id", return_value="t1"):
        new_id = nsb.persist_briefing(content, usage, "2026-05-24")

    assert len(new_id) == 36  # UUID4
    calls = mock_c.execute.call_args_list
    assert len(calls) == 2
    # First call: UPDATE (supersede)
    assert "UPDATE syntheses" in calls[0][0][0]
    assert calls[0][0][1][0] == new_id  # superseded_by = new_id
    # Second call: INSERT
    assert "INSERT INTO syntheses" in calls[1][0][0]
    assert calls[1][0][1][0] == new_id  # id = new_id
