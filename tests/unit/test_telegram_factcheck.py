# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.4.3 — Unit tests for the Telegram ``/factcheck`` command and the
.md-attachment auto fact-check path."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from exocortex import telegram_bot


# ─────────────────────────── helpers ───────────────────────────


def _msg(*, user_id: int = 111, chat_id: int = 111, message_id: int = 42,
         text: str | None = "hello", document: dict | None = None) -> dict:
    out: dict = {
        "from": {"id": user_id, "first_name": "T"},
        "chat": {"id": chat_id, "type": "private"},
        "message_id": message_id,
    }
    if text is not None:
        out["text"] = text
    if document is not None:
        out["document"] = document
    return out


def _install_gfc(monkeypatch, gfc_mock: MagicMock) -> None:
    fake = types.ModuleType("exocortex.mcp_server")
    fake.graph_fact_check = gfc_mock
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)


# ─────────────────────────── _format_fact_check ───────────────────────────


def test_format_fact_check_empty_returns_friendly_message():
    out = telegram_bot._format_fact_check([])
    assert "Nie znalazłem" in out


def test_format_fact_check_mixed_verdicts():
    verdicts = [
        {
            "claim": "GLOBEX budget Q4 2026",
            "verdict": "supported",
            "sources": [{"title": "meeting-1"}, {"title": "meeting-2"}],
        },
        {
            "claim": "Tyrell approved remediation",
            "verdict": "contradicts",
            "sources": [{"title": "memo-3"}],
        },
        {"claim": "X happened", "verdict": "no_evidence", "sources": []},
    ]
    out = telegram_bot._format_fact_check(verdicts)
    assert "✅ GLOBEX budget Q4 2026" in out
    assert "❌ Tyrell approved remediation" in out
    assert "❓ X happened" in out
    assert "meeting-1, meeting-2" in out
    assert "Fact-check: 3 twierdzenie(ń)" in out


def test_format_fact_check_unknown_verdict_defaults_to_question_mark():
    out = telegram_bot._format_fact_check([
        {"claim": "weird", "verdict": "garbage", "sources": []},
    ])
    assert "❓ weird" in out


def test_format_fact_check_falls_back_to_thought_id_when_no_title():
    out = telegram_bot._format_fact_check([
        {"claim": "c", "verdict": "supported",
         "sources": [{"thought_id": "abc-123"}]},
    ])
    assert "abc-123" in out


# ─────────────────────────── _split_long_message ───────────────────────────


def test_split_long_message_short_returns_single():
    assert telegram_bot._split_long_message("hi", limit=100) == ["hi"]


def test_split_long_message_splits_on_blank_line():
    para = "x" * 200
    text = para + "\n\n" + para + "\n\n" + para
    parts = telegram_bot._split_long_message(text, limit=250)
    assert len(parts) == 3
    for p in parts:
        assert len(p) <= 250


def test_split_long_message_hard_truncates_when_no_paragraph_breaks():
    text = "y" * 5000
    parts = telegram_bot._split_long_message(text, limit=1000)
    assert len(parts) == 1
    assert len(parts[0]) == 1000


# ─────────────────────────── _strip_factcheck_prefix ───────────────────────


@pytest.mark.parametrize("text,expected", [
    ("/factcheck Ola zatwierdziła Q4", "Ola zatwierdziła Q4"),
    ("/factcheck@MyBot some claim", "some claim"),
    ("/factcheck", ""),
    ("/FACTCHECK multi\nline", "multi\nline"),
    ("raw text without slash", "raw text without slash"),
])
def test_strip_factcheck_prefix(text, expected):
    assert telegram_bot._strip_factcheck_prefix(text) == expected


# ─────────────────────────── /factcheck command ───────────────────────────


def test_factcheck_command_calls_graph_fact_check(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    gfc = MagicMock(return_value=[
        {"claim": "X", "verdict": "supported", "sources": [{"title": "t1"}]},
    ])
    _install_gfc(monkeypatch, gfc)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="/factcheck Ola zatwierdziła Q4 budget"),
        allowed_ids={111},
    )
    assert intent == "factcheck"
    gfc.assert_called_once_with("Ola zatwierdziła Q4 budget")
    send_mock.assert_called_once()
    _, args, kwargs = send_mock.mock_calls[0]
    assert args[1] == 111
    assert "✅ X" in args[2]
    assert kwargs.get("reply_to") == 42


def test_factcheck_no_args_prompts_usage(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    gfc = MagicMock(side_effect=AssertionError("must not be called"))
    _install_gfc(monkeypatch, gfc)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="/factcheck"),
        allowed_ids={111},
    )
    assert intent == "factcheck"
    send_mock.assert_called_once()
    args = send_mock.mock_calls[0].args
    assert "Użycie" in args[2]


def test_factcheck_timeout_returns_friendly_message(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    gfc = MagicMock(side_effect=RuntimeError("Database query timeout"))
    _install_gfc(monkeypatch, gfc)

    telegram_bot.handle_message(
        "TOKEN", _msg(text="/factcheck some long claim"),
        allowed_ids={111},
    )
    sent = send_mock.mock_calls[0].args[2]
    assert "⏱️" in sent or "Timeout" in sent


def test_factcheck_generic_error_returns_error_message(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    gfc = MagicMock(side_effect=RuntimeError("db down"))
    _install_gfc(monkeypatch, gfc)

    telegram_bot.handle_message(
        "TOKEN", _msg(text="/factcheck claim"),
        allowed_ids={111},
    )
    sent = send_mock.mock_calls[0].args[2]
    assert "Błąd fact-check" in sent
    assert "db down" in sent


def test_factcheck_long_response_splits_into_multiple_sends(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    # Build a result whose formatted form exceeds MAX_REPLY_CHARS (3500).
    verdicts = [
        {
            "claim": "C" + str(i) + " " + ("y" * 400),
            "verdict": "supported",
            "sources": [{"title": "t" + str(i)}],
        }
        for i in range(20)
    ]
    gfc = MagicMock(return_value=verdicts)
    _install_gfc(monkeypatch, gfc)

    telegram_bot.handle_message(
        "TOKEN", _msg(text="/factcheck big claim list"),
        allowed_ids={111},
    )
    assert send_mock.call_count >= 2
    # Only the first send should carry reply_to=42.
    first_kwargs = send_mock.mock_calls[0].kwargs
    later_kwargs = send_mock.mock_calls[1].kwargs
    assert first_kwargs.get("reply_to") == 42
    assert later_kwargs.get("reply_to") is None


# ─────────────────────────── MD attachment ───────────────────────────


def test_md_attachment_triggers_fact_check(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    download_mock = MagicMock(return_value="# Note\nKamila approved Q4 budget.")
    monkeypatch.setattr(telegram_bot, "_download_telegram_file", download_mock)
    gfc = MagicMock(return_value=[
        {"claim": "Ola approved Q4 budget",
         "verdict": "supported", "sources": [{"title": "src"}]},
    ])
    _install_gfc(monkeypatch, gfc)

    intent = telegram_bot.handle_message(
        "TOKEN",
        _msg(text=None, document={"file_id": "AABBCC", "file_name": "note.md"}),
        allowed_ids={111},
    )
    assert intent == "factcheck"
    download_mock.assert_called_once()
    gfc.assert_called_once_with("# Note\nKamila approved Q4 budget.")
    assert send_mock.call_count >= 1
    assert "✅" in send_mock.mock_calls[0].args[2]


def test_md_attachment_too_large_returns_error(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    monkeypatch.setattr(
        telegram_bot, "_download_telegram_file",
        MagicMock(side_effect=telegram_bot._FileTooLargeError("too big")),
    )
    gfc = MagicMock(side_effect=AssertionError("must not be called"))
    _install_gfc(monkeypatch, gfc)

    telegram_bot.handle_message(
        "TOKEN",
        _msg(text=None, document={"file_id": "X", "file_name": "huge.md"}),
        allowed_ids={111},
    )
    assert "Plik za duży" in send_mock.mock_calls[0].args[2]


def test_non_md_attachment_ignored(monkeypatch):
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    download_mock = MagicMock(side_effect=AssertionError("must not download"))
    monkeypatch.setattr(telegram_bot, "_download_telegram_file", download_mock)
    gfc = MagicMock(side_effect=AssertionError("must not be called"))
    _install_gfc(monkeypatch, gfc)

    # No text + non-md doc → handle_message returns None silently
    result = telegram_bot.handle_message(
        "TOKEN",
        _msg(text=None, document={"file_id": "Y", "file_name": "note.pdf"}),
        allowed_ids={111},
    )
    assert result is None
    send_mock.assert_not_called()


# ─────────────────────────── intent route: graph_fact_check ────────────────


def test_llm_intent_graph_fact_check_routes_to_factcheck(monkeypatch):
    """When the LLM classifier returns 'graph_fact_check' for a non-slash
    message, handle_message must still route to the fact-check pipeline."""
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    # Force the regex classifier to return unknown, then stub the LLM one.
    monkeypatch.setattr(telegram_bot, "classify_intent", lambda _t: "unknown")
    fake_ti = types.ModuleType("exocortex.telegram_intent")
    fake_ti.classify_intent_llm = MagicMock(return_value="graph_fact_check")
    monkeypatch.setitem(sys.modules, "exocortex.telegram_intent", fake_ti)

    gfc = MagicMock(return_value=[
        {"claim": "claim", "verdict": "supported", "sources": []},
    ])
    _install_gfc(monkeypatch, gfc)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="czy to jest prawda że X"),
        allowed_ids={111},
    )
    assert intent == "graph_fact_check"
    gfc.assert_called_once_with("czy to jest prawda że X")


# ─────────────────────────── security: allowlist on MD path ────────────────


def test_non_allowlisted_user_with_md_attachment_is_ignored(monkeypatch):
    """Non-whitelisted user sending an .md file must be silently dropped
    — allowlist check must fire before the attachment handler."""
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    download_mock = MagicMock(side_effect=AssertionError("must not download for unknown user"))
    monkeypatch.setattr(telegram_bot, "_download_telegram_file", download_mock)
    gfc = MagicMock(side_effect=AssertionError("must not be called"))
    _install_gfc(monkeypatch, gfc)

    result = telegram_bot.handle_message(
        "TOKEN",
        _msg(user_id=999, text=None, document={"file_id": "X", "file_name": "secret.md"}),
        allowed_ids={111},
    )
    assert result is None
    send_mock.assert_not_called()
    download_mock.assert_not_called()


def test_md_attachment_with_empty_file_id_does_not_crash(monkeypatch):
    """When document.file_id is absent/None the handler should skip silently."""
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    download_mock = MagicMock(side_effect=AssertionError("must not attempt download"))
    monkeypatch.setattr(telegram_bot, "_download_telegram_file", download_mock)

    result = telegram_bot.handle_message(
        "TOKEN",
        _msg(text=None, document={"file_name": "notes.md"}),  # no file_id
        allowed_ids={111},
    )
    # No file_id → falls through to "no text" early exit
    download_mock.assert_not_called()
    send_mock.assert_not_called()


def test_download_telegram_file_wall_timeout(monkeypatch):
    """_download_telegram_file must raise TimeoutError when wall-clock deadline
    is exceeded mid-stream (mocked via time.monotonic)."""
    import io

    call_count = 0

    class _SlowResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"x" * 100
            # Second read: pretend deadline has passed
            return b"y" * 100

    monkeypatch.setattr(
        telegram_bot, "_telegram_call",
        lambda *_a, **_kw: {"result": {"file_path": "documents/file.md"}},
    )
    monkeypatch.setattr(telegram_bot.urlrequest, "urlopen",
                        lambda *_a, **_kw: _SlowResponse())

    import time as _time
    _original_monotonic = _time.monotonic
    _calls = [0]

    def _fast_deadline():
        _calls[0] += 1
        # First call (deadline setup) returns real time; after that push past deadline.
        if _calls[0] <= 1:
            return _original_monotonic()
        return _original_monotonic() + 9999  # already past deadline

    import exocortex.telegram_bot as _bot_mod
    monkeypatch.setattr(_bot_mod.time, "monotonic", _fast_deadline)

    with pytest.raises(TimeoutError):
        telegram_bot._download_telegram_file("TOKEN", "file123", wall_timeout=1.0)
