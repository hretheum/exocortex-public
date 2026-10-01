# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.0.3 — Unit tests for the Telegram bot worker."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from exocortex import telegram_bot

# ─────────────────────────── classify_intent ───────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/capture To jest nowa myśl o AI", "capture"),
        ("/capture@MyBot foo bar", "capture"),
        ("/CAPTURE\nwielolinijka", "capture"),
        ("todo na dziś", "action_items"),
        ("pokaż action items", "action_items"),
        ("co do zrobienia w tym tygodniu", "action_items"),
        ("znajdź notatki o Postgresie", "search"),
        ("szukaj wszystkich projektów", "search"),
        ("co Ola mówiła o remediation", "ask"),
        ("kiedy ustaliliśmy budżet", "ask"),
        ("jak działa AGE graph", "ask"),
        ("", "unknown"),
        ("losowy tekst bez intencji 12345", "unknown"),
    ],
)
def test_classify_intent_patterns(text: str, expected: str) -> None:
    assert telegram_bot.classify_intent(text) == expected


# ─────────────────────────── escape_markdown_v2 ───────────────────────────


def test_escape_markdown_v2_escapes_specials() -> None:
    raw = "hello_world (test) [link] *bold* `code` 1+2=3. dash-here!"
    escaped = telegram_bot.escape_markdown_v2(raw)
    for ch in "_()[]*`+=-.!":
        assert "\\" + ch in escaped, f"missing escape for {ch!r} in {escaped!r}"


def test_escape_markdown_v2_idempotent_on_plain_text() -> None:
    plain = "abc 123 xyz"
    assert telegram_bot.escape_markdown_v2(plain) == plain


# ─────────────────────────── get_allowed_ids ───────────────────────────


def test_get_allowed_ids_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("TG_ALLOWED_USER_IDS", raising=False)
    assert telegram_bot.get_allowed_ids() == set()


def test_get_allowed_ids_parses_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("TG_ALLOWED_USER_IDS", "111,222,  333  ")
    assert telegram_bot.get_allowed_ids() == {111, 222, 333}


def test_get_allowed_ids_skips_garbage(monkeypatch) -> None:
    monkeypatch.setenv("TG_ALLOWED_USER_IDS", "111,abc,222,,")
    assert telegram_bot.get_allowed_ids() == {111, 222}


# ─────────────────────────── handle_message ───────────────────────────


def _msg(*, user_id: int = 111, chat_id: int = 111, message_id: int = 42,
         text: str = "hello") -> dict:
    return {
        "from": {"id": user_id, "first_name": "T"},
        "chat": {"id": chat_id, "type": "private"},
        "message_id": message_id,
        "text": text,
    }


def test_non_whitelist_user_silently_ignored(monkeypatch) -> None:
    """Security: messages from non-allowlisted users must not produce ANY
    outbound side effect (no Telegram reply, no MCP call, no capture POST).
    """
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    # Sentinel: if any MCP tool is touched, raise so the test fails loudly.
    fake = types.ModuleType("exocortex.mcp_server")
    fake.ask = MagicMock(side_effect=AssertionError("ask must not be called"))
    fake.search_thoughts = MagicMock(
        side_effect=AssertionError("search_thoughts must not be called")
    )
    fake.find_action_items = MagicMock(
        side_effect=AssertionError("find_action_items must not be called")
    )
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)

    result = telegram_bot.handle_message(
        "TOKEN", _msg(user_id=999, text="co mówiła Ola"),
        allowed_ids={111, 222},
    )
    assert result is None
    send_mock.assert_not_called()


def test_whitelist_ask_intent_calls_ask(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)

    ask_mock = MagicMock(return_value={
        "answer": "Ola mówiła o Q4.",
        "sources": [{"title": "meeting-2026-05-01", "thought_id": "abc"}],
    })
    fake = types.ModuleType("exocortex.mcp_server")
    fake.ask = ask_mock
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="co Ola mówiła o Q4"),
        allowed_ids={111},
    )
    assert intent == "ask"
    ask_mock.assert_called_once_with("co Ola mówiła o Q4")
    send_mock.assert_called_once()
    _, args, kwargs = send_mock.mock_calls[0]
    # token, chat_id, body
    assert args[0] == "TOKEN"
    assert args[1] == 111
    assert "Ola mówiła o Q4" in args[2]
    assert "meeting-2026-05-01" in args[2]
    assert kwargs.get("reply_to") == 42


def test_whitelist_search_intent_calls_search_thoughts(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)

    search_mock = MagicMock(return_value=[
        {"title": "note-a", "score": 0.91},
        {"title": "note-b", "score": 0.88},
    ])
    fake = types.ModuleType("exocortex.mcp_server")
    fake.search_thoughts = search_mock
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="znajdź notatki o AGE"),
        allowed_ids={111},
    )
    assert intent == "search"
    search_mock.assert_called_once_with("znajdź notatki o AGE")
    assert send_mock.call_count == 1


def test_whitelist_action_items_intent(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)

    items_mock = MagicMock(return_value=[
        {"owner_name": "Eryk", "content": "ship F31.0.3", "due_date": "2026-05-25"},
    ])
    fake = types.ModuleType("exocortex.mcp_server")
    fake.find_action_items = items_mock
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="todo na dziś"),
        allowed_ids={111},
    )
    assert intent == "action_items"
    items_mock.assert_called_once_with()
    body = send_mock.mock_calls[0].args[2]
    assert "ship F31.0.3" in body
    assert "Eryk" in body


def test_unknown_intent_falls_back_to_ask(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)

    ask_mock = MagicMock(return_value={"answer": "fallback", "sources": []})
    fake = types.ModuleType("exocortex.mcp_server")
    fake.ask = ask_mock
    monkeypatch.setitem(sys.modules, "exocortex.mcp_server", fake)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="zupełnie losowa wypowiedź bez słów kluczowych"),
        allowed_ids={111},
    )
    assert intent == "ask"
    ask_mock.assert_called_once()


def test_capture_command_posts_to_capture_api(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    post_mock = MagicMock(return_value=(True, "src-uuid-123"))
    monkeypatch.setattr(telegram_bot, "post_capture", post_mock)

    intent = telegram_bot.handle_message(
        "TOKEN",
        _msg(text="/capture Pomysł na artykuł o exocortex"),
        allowed_ids={111},
        capture_base_url="http://example/api",
        capture_token="secret",
    )
    assert intent == "capture"
    post_mock.assert_called_once()
    kwargs = post_mock.mock_calls[0].kwargs
    assert kwargs["base_url"] == "http://example/api"
    assert kwargs["api_token"] == "secret"
    assert kwargs["user_id"] == 111
    assert kwargs["text"] == "Pomysł na artykuł o exocortex"
    body = send_mock.mock_calls[0].args[2]
    assert "src-uuid-123" in body
    assert body.startswith("✓")


def test_capture_command_without_body_prompts_usage(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    post_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "post_capture", post_mock)

    intent = telegram_bot.handle_message(
        "TOKEN", _msg(text="/capture"), allowed_ids={111},
    )
    assert intent == "capture"
    post_mock.assert_not_called()
    send_mock.assert_called_once()
    assert "Użycie" in send_mock.mock_calls[0].args[2]


def test_capture_failure_surfaces_reason(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    monkeypatch.setattr(
        telegram_bot, "post_capture",
        MagicMock(return_value=(False, "HTTP 401")),
    )

    telegram_bot.handle_message(
        "TOKEN", _msg(text="/capture some text"),
        allowed_ids={111}, capture_base_url="http://x",
    )
    body = send_mock.mock_calls[0].args[2]
    assert body.startswith("✗")
    assert "HTTP 401" in body


def test_message_without_text_ignored(monkeypatch) -> None:
    send_mock = MagicMock()
    monkeypatch.setattr(telegram_bot, "send_message", send_mock)
    msg = _msg()
    msg["text"] = ""
    assert telegram_bot.handle_message("TOKEN", msg, allowed_ids={111}) is None
    send_mock.assert_not_called()


# ─────────────────────────── post_capture ───────────────────────────


def test_post_capture_builds_request(monkeypatch) -> None:
    captured: dict = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"source_id": "abc", "created": true}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["data"] = req.data
        captured["method"] = req.get_method()
        return _FakeResp()

    monkeypatch.setattr(telegram_bot.urlrequest, "urlopen", fake_urlopen)

    ok, info = telegram_bot.post_capture(
        base_url="http://example/api/",
        api_token="tok",
        user_id=111, message_id=42,
        text="hello world",
    )
    assert ok is True
    assert info == "abc"
    assert captured["url"] == "http://example/api/capture"
    assert captured["method"] == "POST"
    assert "Authorization" in {k.title() for k in captured["headers"]}
    import json as _json
    payload = _json.loads(captured["data"].decode("utf-8"))
    assert payload["source_type"] == "telegram-capture"
    assert payload["uri"] == "telegram://message/111/42"
    assert payload["raw_payload"] == "hello world"
    assert payload["metadata"]["telegram_user_id"] == 111
