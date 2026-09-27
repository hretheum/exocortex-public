# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.1.4 — pg_notify → Telegram push daemon.

Subscribes to the channels defined in ``schema/27_notify_triggers.sql`` and
fans each NOTIFY out to a Telegram message via
``exocortex.telegram_bot.send_message`` (reused, no duplicated MarkdownV2
escape logic).

Channels handled:
  - ``contradiction_detected`` : new ``edges`` row with ``type='contradicts'``.
  - ``action_item_due``        : reserved for a future producer (cron path).
                                 Listening pre-emptively costs nothing.

Throttling
    A new event on the same channel within ``THROTTLE_SEC`` of the last push
    on that channel is dropped silently. The state is in-memory, so a daemon
    restart also resets the throttle — that is intentional: restarts are
    rare, and re-sending a message after one is the lesser harm.

Reconnect
    On a transport error the daemon waits ``RECONNECT_DELAY_SEC`` and retries,
    up to ``MAX_RECONNECT_ATTEMPTS``. The counter resets after a successful
    LISTEN cycle so a short network blip doesn't burn the budget.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

import psycopg
from psycopg import AsyncConnection

from exocortex.settings import get_settings
from exocortex.telegram_bot import send_message

log = logging.getLogger("exocortex.notify_listener")

CHANNELS: tuple[str, ...] = ("contradiction_detected", "action_item_due")
THROTTLE_SEC: float = 5 * 60.0
RECONNECT_DELAY_SEC: float = 5.0
MAX_RECONNECT_ATTEMPTS: int = 3


# ─────────────────────────── Formatters ───────────────────────────


def format_message(channel: str, payload: dict[str, Any]) -> str:
    """Render a NOTIFY payload as a plain-text body for Telegram.

    Output is plain text — ``send_message`` runs ``escape_markdown_v2`` on it,
    so we avoid pre-escaping here (would double-escape).
    """
    if channel == "contradiction_detected":
        src = str(payload.get("src_id", "?"))[:8]
        dst = str(payload.get("dst_id", "?"))[:8]
        return (
            f"⚠️ Sprzeczność wykryta\n"
            f"src: {src} ({payload.get('src_type', '?')})\n"
            f"dst: {dst} ({payload.get('dst_type', '?')})"
        )
    if channel == "action_item_due":
        owner = payload.get("owner") or payload.get("owner_name") or "?"
        content = (payload.get("content") or "").strip() or "(brak treści)"
        due = payload.get("due_date") or payload.get("due") or ""
        suffix = f" [{due}]" if due else ""
        return f"⏰ Action item due{suffix}\n[{owner}] {content}"
    return f"[{channel}] {json.dumps(payload, ensure_ascii=False)}"


# ─────────────────────────── Throttle ───────────────────────────


class Throttle:
    """Per-channel monotonic-clock throttle. Pure logic, no I/O."""

    def __init__(self, window_sec: float = THROTTLE_SEC) -> None:
        self.window = window_sec
        self._last: dict[str, float] = {}

    def allow(self, channel: str, now: float) -> bool:
        last = self._last.get(channel)
        if last is not None and (now - last) < self.window:
            return False
        self._last[channel] = now
        return True


# ─────────────────────────── Dispatcher ───────────────────────────


def _parse_payload(raw: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        log.warning("bad notify payload: %r", raw)
        return None
    if not isinstance(decoded, dict):
        log.warning("notify payload is not a JSON object: %r", raw)
        return None
    return decoded


def handle_notify(
    channel: str,
    payload_raw: str,
    *,
    throttle: Throttle,
    now: float,
    bot_token: str,
    chat_id: int,
    send=send_message,
) -> bool:
    """Process one NOTIFY. Returns True iff a Telegram message was sent.

    Pure-ish: external I/O is injected via ``send`` so unit tests can stub it.
    """
    payload = _parse_payload(payload_raw)
    if payload is None:
        return False
    if not throttle.allow(channel, now):
        log.debug("throttled %s", channel)
        return False
    text = format_message(channel, payload)
    try:
        send(bot_token, chat_id, text)
    except Exception:
        log.exception("send_message failed for channel=%s", channel)
        return False
    log.info("pushed Telegram message for channel=%s", channel)
    return True


# ─────────────────────────── LISTEN loop ───────────────────────────


async def _listen_once(
    dsn: str,
    *,
    throttle: Throttle,
    bot_token: str,
    chat_id: int,
    stop_event: asyncio.Event,
    loop_clock=asyncio.get_running_loop,
) -> None:
    """Single connect → LISTEN → consume cycle. Exits when ``stop_event`` set
    or the connection drops (re-raises on transport error so the outer loop
    handles backoff)."""
    conn = await AsyncConnection.connect(dsn, autocommit=True)
    try:
        for ch in CHANNELS:
            await conn.execute(f"LISTEN {ch}")
        log.info("listening on: %s", ", ".join(CHANNELS))

        notify_iter = conn.notifies()
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            while not stop_event.is_set():
                notify_task = asyncio.create_task(notify_iter.__anext__())
                done, _ = await asyncio.wait(
                    {notify_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stop_task in done:
                    notify_task.cancel()
                    break
                try:
                    n = notify_task.result()
                except StopAsyncIteration:
                    break
                handle_notify(
                    n.channel,
                    n.payload,
                    throttle=throttle,
                    now=loop_clock().time(),
                    bot_token=bot_token,
                    chat_id=chat_id,
                )
        finally:
            stop_task.cancel()
    finally:
        await conn.close()


async def run(stop_event: asyncio.Event | None = None) -> int:
    """Outer reconnect loop. Returns process exit code."""
    settings = get_settings()
    if not settings.tg_bot_token or not settings.tg_chat_id:
        log.warning(
            "TG_BOT_TOKEN and TG_CHAT_ID are not set — notify-listener running "
            "in idle mode (pg_notify events will be dropped). "
            "Set TG_BOT_TOKEN + TG_CHAT_ID to enable Telegram push."
        )
        # Idle loop: stay running so the container is healthy, check every 60s
        # in case credentials are injected at runtime via docker compose override.
        if stop_event is None:
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except NotImplementedError:
                    pass
        while not stop_event.is_set():
            await asyncio.sleep(60)
            new_settings = get_settings()
            if new_settings.tg_bot_token and new_settings.tg_chat_id:
                log.info("Telegram credentials now available — restarting listener.")
                break
        return 0

    if stop_event is None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

    # Deferred import: exocortex.db pulls in psycopg_pool + AGE wiring at
    # module load, which forces Settings() (and therefore a vault_path) to be
    # present. Unit tests for the pure-logic helpers don't need any of that.
    from exocortex.db import _conninfo

    throttle = Throttle()
    attempts = 0
    while not stop_event.is_set():
        try:
            await _listen_once(
                _conninfo(),
                throttle=throttle,
                bot_token=settings.tg_bot_token,
                chat_id=int(settings.tg_chat_id),
                stop_event=stop_event,
            )
            attempts = 0
            if stop_event.is_set():
                break
        except (psycopg.OperationalError, ConnectionError):
            attempts += 1
            log.warning(
                "listener connection lost (attempt %d/%d); reconnecting in %ss",
                attempts, MAX_RECONNECT_ATTEMPTS, RECONNECT_DELAY_SEC,
            )
            if attempts >= MAX_RECONNECT_ATTEMPTS:
                log.error("max reconnect attempts exhausted; exiting")
                return 1
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=RECONNECT_DELAY_SEC)
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            break
    log.info("notify listener shutting down")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
