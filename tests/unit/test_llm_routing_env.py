# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""EXOCORTEX_LLM_ROUTING selects the routing file."""
from __future__ import annotations

from pathlib import Path

import pytest

from exocortex import llm_routing


@pytest.fixture
def fresh(monkeypatch):
    calls: list[Path] = []
    monkeypatch.setattr(llm_routing, "_initialized", False)
    monkeypatch.setattr(llm_routing, "_set_routing_config", lambda p: calls.append(Path(p)))
    monkeypatch.setattr(llm_routing, "_set_telemetry_sink", lambda s: None)
    yield calls
    monkeypatch.setattr(llm_routing, "_initialized", False)


def test_env_selects_repo_relative_file(monkeypatch, fresh) -> None:
    monkeypatch.chdir("/")
    monkeypatch.setenv("EXOCORTEX_LLM_ROUTING", "config/llm_routing.selfhosted.yaml")
    llm_routing.initialize()
    assert fresh == [llm_routing._REPO_ROOT / "config" / "llm_routing.selfhosted.yaml"]


def test_env_missing_file_is_an_error(monkeypatch, fresh, tmp_path) -> None:
    monkeypatch.setenv("EXOCORTEX_LLM_ROUTING", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        llm_routing.initialize()


def test_default_without_env(monkeypatch, fresh) -> None:
    monkeypatch.delenv("EXOCORTEX_LLM_ROUTING", raising=False)
    llm_routing.initialize()
    assert fresh == [llm_routing._DEFAULT_ROUTING_PATH]
