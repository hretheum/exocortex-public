# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.1.4 — Unit tests for the pg_notify listener daemon."""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock

import pytest

# Settings() requires vault_path; the listener is the unit under test and we
# monkeypatch get_settings in the few cases that need it, so satisfy the env
# eagerly here to avoid the cached-settings ValidationError on import.
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from exocortex import notify_listener
from exocortex.notify_listener import (
    Throttle,
    format_message,
    handle_notify,
)

# ─────────────────────────── Throttle ───────────────────────────


def test_throttle_first_event_passes() -> None:
    t = Throttle(window_sec=300.0)
    assert t.allow("contradiction_detected", now=1000.0) is True


def test_throttle_blocks_within_window() -> None:
    t = Throttle(window_sec=300.0)
    assert t.allow("contradiction_detected", now=1000.0) is True
    assert t.allow("contradiction_detected", now=1100.0) is False
    assert t.allow("contradiction_detected", now=1299.99) is False


def test_throttle_releases_after_window() -> None:
    t = Throttle(window_sec=300.0)
    assert t.allow("contradiction_detected", now=1000.0) is True
    assert t.allow("contradiction_detected", now=1301.0) is True


def test_throttle_is_per_channel() -> None:
    t = Throttle(window_sec=300.0)
    assert t.allow("contradiction_detected", now=1000.0) is True
    assert t.allow("action_item_due", now=1000.0) is True
    assert t.allow("contradiction_detected", now=1100.0) is False
    assert t.allow("action_item_due", now=1100.0) is False


def test_throttle_3_events_in_10s_only_one_pass() -> None:
    t = Throttle(window_sec=300.0)
    passed = sum(
        1
        for ts in (1000.0, 1005.0, 1010.0)
        if t.allow("contradiction_detected", now=ts)
    )
    assert passed == 1


# ─────────────────────────── format_message ───────────────────────────


def test_format_message_contradiction() -> None:
    out = format_message(
        "contradiction_detected",
        {
            "edge_id": "abc",
            "src_id": "11111111-1111-1111-1111-111111111111",
            "src_type": "thought",
            "dst_id": "22222222-2222-2222-2222-222222222222",
            "dst_type": "thought",
        },
    )
    assert "Sprzeczność" in out
    assert "11111111" in out
    assert "22222222" in out


def test_format_message_action_item_due() -> None:
    out = format_message(
        "action_item_due",
        {"owner": "Ola", "content": "Review remediation plan", "due_date": "2026-06-01"},
    )
    assert "Ola" in out
    assert "Review remediation plan" in out
    assert "2026-06-01" in out


def test_format_message_unknown_channel_falls_back_to_json() -> None:
    out = format_message("custom_channel", {"foo": "bar"})
    assert "custom_channel" in out
    assert "bar" in out


# ─────────────────────────── handle_notify ───────────────────────────


def test_handle_notify_sends_message() -> None:
    send = MagicMock()
    throttle = Throttle(window_sec=300.0)
    payload = json.dumps(
        {"src_id": "a", "src_type": "thought", "dst_id": "b", "dst_type": "thought"}
    )

    sent = handle_notify(
        "contradiction_detected",
        payload,
        throttle=throttle,
        now=1000.0,
        bot_token="TOKEN",
        chat_id=42,
        send=send,
    )

    assert sent is True
    send.assert_called_once()
    token, chat_id, text = send.call_args.args
    assert token == "TOKEN"
    assert chat_id == 42
    assert "Sprzeczność" in text


def test_handle_notify_drops_when_throttled() -> None:
    send = MagicMock()
    throttle = Throttle(window_sec=300.0)
    payload = json.dumps({"src_id": "a", "dst_id": "b"})

    first = handle_notify(
        "contradiction_detected", payload,
        throttle=throttle, now=1000.0,
        bot_token="t", chat_id=1, send=send,
    )
    second = handle_notify(
        "contradiction_detected", payload,
        throttle=throttle, now=1100.0,
        bot_token="t", chat_id=1, send=send,
    )

    assert first is True
    assert second is False
    assert send.call_count == 1


def test_handle_notify_bad_payload_no_send() -> None:
    send = MagicMock()
    throttle = Throttle(window_sec=300.0)

    sent = handle_notify(
        "contradiction_detected", "not-json{",
        throttle=throttle, now=1000.0,
        bot_token="t", chat_id=1, send=send,
    )

    assert sent is False
    send.assert_not_called()


def test_handle_notify_non_object_payload_no_send() -> None:
    send = MagicMock()
    throttle = Throttle(window_sec=300.0)

    sent = handle_notify(
        "contradiction_detected", json.dumps(["not", "a", "dict"]),
        throttle=throttle, now=1000.0,
        bot_token="t", chat_id=1, send=send,
    )

    assert sent is False
    send.assert_not_called()


def test_handle_notify_send_exception_swallowed() -> None:
    send = MagicMock(side_effect=RuntimeError("network down"))
    throttle = Throttle(window_sec=300.0)

    sent = handle_notify(
        "contradiction_detected", json.dumps({"src_id": "a"}),
        throttle=throttle, now=1000.0,
        bot_token="t", chat_id=1, send=send,
    )

    assert sent is False
    send.assert_called_once()


def test_handle_notify_throttle_releases_after_window() -> None:
    send = MagicMock()
    throttle = Throttle(window_sec=300.0)
    payload = json.dumps({"src_id": "a"})

    handle_notify("contradiction_detected", payload,
                  throttle=throttle, now=1000.0,
                  bot_token="t", chat_id=1, send=send)
    handle_notify("contradiction_detected", payload,
                  throttle=throttle, now=1301.0,
                  bot_token="t", chat_id=1, send=send)

    assert send.call_count == 2


# ─────────────────────────── run() — config + graceful shutdown ───────────────────────────


def test_run_exits_when_telegram_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = MagicMock(tg_bot_token=None, tg_chat_id=None)
    monkeypatch.setattr(notify_listener, "get_settings", lambda: fake_settings)

    rc = asyncio.run(notify_listener.run(stop_event=asyncio.Event()))
    assert rc == 2


def test_run_graceful_shutdown_on_stop_event(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = MagicMock(tg_bot_token="t", tg_chat_id=42)
    monkeypatch.setattr(notify_listener, "get_settings", lambda: fake_settings)

    async def _scenario() -> int:
        stop = asyncio.Event()

        async def fake_listen_once(dsn, *, throttle, bot_token, chat_id, stop_event):
            await stop_event.wait()

        monkeypatch.setattr(notify_listener, "_listen_once", fake_listen_once)
        task = asyncio.create_task(notify_listener.run(stop_event=stop))
        await asyncio.sleep(0)
        stop.set()
        return await asyncio.wait_for(task, timeout=2.0)

    rc = asyncio.run(_scenario())
    assert rc == 0


def test_run_reconnects_on_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    fake_settings = MagicMock(tg_bot_token="t", tg_chat_id=42)
    monkeypatch.setattr(notify_listener, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(notify_listener, "RECONNECT_DELAY_SEC", 0.01)
    monkeypatch.setattr(notify_listener, "MAX_RECONNECT_ATTEMPTS", 3)

    calls = {"n": 0}

    async def fake_listen_once(dsn, *, throttle, bot_token, chat_id, stop_event):
        calls["n"] += 1
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(notify_listener, "_listen_once", fake_listen_once)
    rc = asyncio.run(notify_listener.run(stop_event=asyncio.Event()))
    assert rc == 1
    assert calls["n"] == 3
