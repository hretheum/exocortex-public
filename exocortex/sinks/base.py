# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Sink protocol — 6th extension point on the plugin registry.

A Sink takes already-persisted PG state and pushes it to an external system
(Notion, Telegram, GitHub, …). Sinks are best-effort and idempotent.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Sink(Protocol):
    name: str
