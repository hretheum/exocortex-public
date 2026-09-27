# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for the MCP tool registry layer (F31.7.4)."""
from __future__ import annotations

import os

# mcp_server.py checks TENANT_ID at module level — set before any import.
os.environ.setdefault("TENANT_ID", "test-tenant")

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from exocortex.core.registry import Registry
from exocortex.mcp.tools.base import McpTool, _LegacyMcpTool
from exocortex.mcp.server import setup_builtins, setup_from_registry


# ── Helpers ───────────────────────────────────────────────────────────────────

EXPECTED_BUILTINS = {
    "search_thoughts",
    "expand_node",
    "synthesize",
    "find_action_items",
    "find_contradictions",
    "ask",
}

EXPECTED_FRP = {
    "query_content_queue",
    "create_frp_session",
    "append_session_thought",
    "complete_session",
    "enqueue_generated_frp_story",
    "add_revisit",
}

EXPECTED_PROMOTION = {"promote_action_items", "unpromote", "list_promoted"}

EXPECTED_LIVE_SECTIONS = {"list_live_sections", "trigger_live_section"}


# ── _LegacyMcpTool contract ───────────────────────────────────────────────────

class _StubTool(_LegacyMcpTool):
    _legacy_fn_name = "search_thoughts"

    @property
    def name(self) -> str:
        return "stub_tool"


def test_legacy_mcp_tool_is_mcp_tool():
    assert issubclass(_StubTool, McpTool)


def test_legacy_mcp_tool_schema_is_empty_dict():
    stub = _StubTool()
    assert stub.schema == {}


def test_legacy_mcp_tool_get_fn_returns_callable():
    stub = _StubTool()
    with patch("importlib.import_module") as mock_import:
        mock_mod = MagicMock()
        mock_mod.search_thoughts = lambda query_text, top_k=10: []
        mock_import.return_value = mock_mod
        fn = stub._get_fn()
    assert callable(fn)


def test_legacy_mcp_tool_get_fn_raises_on_missing_fn():
    class _BadTool(_LegacyMcpTool):
        _legacy_fn_name = "does_not_exist_ever"

        @property
        def name(self) -> str:
            return "bad_tool"

    bad = _BadTool()
    with patch("importlib.import_module") as mock_import:
        mock_mod = MagicMock(spec=[])  # no attributes
        mock_import.return_value = mock_mod
        with pytest.raises(AttributeError, match="does_not_exist_ever"):
            bad._get_fn()


def test_legacy_mcp_tool_handler_delegates_to_fn():
    stub = _StubTool()
    sentinel = [{"thought_id": "abc"}]
    mock_fn = MagicMock(return_value=sentinel)
    with patch.object(_StubTool, "_get_fn", return_value=mock_fn):
        result = stub.handler({"query_text": "hello", "top_k": 5})
    mock_fn.assert_called_once_with(query_text="hello", top_k=5)
    assert result is sentinel


# ── setup_builtins ────────────────────────────────────────────────────────────

def test_setup_builtins_registers_6_tools():
    reg = Registry()
    setup_builtins(reg)
    assert EXPECTED_BUILTINS.issubset(set(reg.mcp_tools.keys()))


def test_setup_builtins_count_is_exactly_6():
    reg = Registry()
    setup_builtins(reg)
    assert len(reg.mcp_tools) == 6


def test_setup_builtins_all_are_mcp_tool_instances():
    reg = Registry()
    setup_builtins(reg)
    for name, tool in reg.mcp_tools.items():
        assert isinstance(tool, McpTool), f"{name!r} is not a McpTool"


def test_setup_builtins_all_are_legacy_mcp_tools():
    reg = Registry()
    setup_builtins(reg)
    for name, tool in reg.mcp_tools.items():
        assert isinstance(tool, _LegacyMcpTool), f"{name!r} is not a _LegacyMcpTool"


def test_setup_builtins_all_have_legacy_fn_name():
    reg = Registry()
    setup_builtins(reg)
    for name, tool in reg.mcp_tools.items():
        assert tool._legacy_fn_name, f"{name!r}: _legacy_fn_name is empty"


def test_setup_builtins_tool_name_matches_key():
    reg = Registry()
    setup_builtins(reg)
    for key, tool in reg.mcp_tools.items():
        assert tool.name == key, f"tool.name={tool.name!r} != key={key!r}"


def test_setup_builtins_idempotent():
    reg = Registry()
    setup_builtins(reg)
    count1 = len(reg.mcp_tools)
    setup_builtins(reg)
    assert len(reg.mcp_tools) == count1


# ── Individual tool modules ───────────────────────────────────────────────────

@pytest.mark.parametrize("module_name,expected_names", [
    ("exocortex.mcp.tools.search_thoughts", ["search_thoughts"]),
    ("exocortex.mcp.tools.expand_node", ["expand_node"]),
    ("exocortex.mcp.tools.synthesize", ["synthesize"]),
    ("exocortex.mcp.tools.find_action_items", ["find_action_items"]),
    ("exocortex.mcp.tools.find_contradictions", ["find_contradictions"]),
    ("exocortex.mcp.tools.ask", ["ask"]),
    (
        "exocortex.mcp.tools.frp",
        ["query_content_queue", "create_frp_session", "append_session_thought",
         "complete_session", "enqueue_generated_frp_story", "add_revisit"],
    ),
    (
        "exocortex.mcp.tools.promotion",
        ["promote_action_items", "unpromote", "list_promoted"],
    ),
    (
        "exocortex.mcp.tools.live_sections",
        ["list_live_sections", "trigger_live_section"],
    ),
])
def test_tool_module_setup(module_name: str, expected_names: list[str]):
    import importlib
    mod = importlib.import_module(module_name)
    reg = Registry()
    mod.setup(reg)
    for name in expected_names:
        assert name in reg.mcp_tools, f"'{name}' not registered by {module_name}"
        tool = reg.mcp_tools[name]
        assert isinstance(tool, McpTool)
        assert tool.name == name


# ── opt-in extra tool groups ──────────────────────────────────────────────────

def test_frp_extras_register_6_tools():
    from exocortex.mcp.tools import frp
    reg = Registry()
    frp.setup(reg)
    assert EXPECTED_FRP == set(reg.mcp_tools.keys())


def test_promotion_extras_register_3_tools():
    from exocortex.mcp.tools import promotion
    reg = Registry()
    promotion.setup(reg)
    assert EXPECTED_PROMOTION == set(reg.mcp_tools.keys())


def test_live_sections_extras_register_2_tools():
    from exocortex.mcp.tools import live_sections
    reg = Registry()
    live_sections.setup(reg)
    assert EXPECTED_LIVE_SECTIONS == set(reg.mcp_tools.keys())


# ── setup_from_registry ───────────────────────────────────────────────────────

def test_setup_from_registry_calls_add_tool_for_each_tool():
    reg = Registry()
    setup_builtins(reg)
    mcp_mock = MagicMock()

    sentinel_fn = MagicMock(name="mock_fn")
    with patch.object(_LegacyMcpTool, "_get_fn", return_value=sentinel_fn):
        setup_from_registry(reg, mcp_mock)

    assert mcp_mock.add_tool.call_count == len(reg.mcp_tools)


def test_setup_from_registry_passes_fn_not_handler():
    reg = Registry()
    setup_builtins(reg)
    mcp_mock = MagicMock()

    sentinel_fn = MagicMock(name="sentinel_fn")
    with patch.object(_LegacyMcpTool, "_get_fn", return_value=sentinel_fn):
        setup_from_registry(reg, mcp_mock)

    for call in mcp_mock.add_tool.call_args_list:
        positional = call[0]
        assert positional[0] is sentinel_fn, "add_tool must receive the fn from _get_fn()"


def test_setup_from_registry_passes_name_kwarg():
    reg = Registry()
    setup_builtins(reg)
    mcp_mock = MagicMock()
    registered_names = set()

    sentinel_fn = MagicMock(name="fn")
    with patch.object(_LegacyMcpTool, "_get_fn", return_value=sentinel_fn):
        setup_from_registry(reg, mcp_mock)

    for call in mcp_mock.add_tool.call_args_list:
        kw = call[1]
        assert "name" in kw, "add_tool must pass name= kwarg"
        registered_names.add(kw["name"])

    assert registered_names == EXPECTED_BUILTINS


def test_setup_from_registry_raises_on_non_legacy_tool():
    class _NativeTool(McpTool):
        @property
        def name(self) -> str:
            return "native_tool"

        @property
        def schema(self) -> dict[str, Any]:
            return {}

        def handler(self, args: dict[str, Any]) -> dict[str, Any]:
            return {}

    reg = Registry()
    reg.register_mcp_tool(_NativeTool())
    mcp_mock = MagicMock()

    with pytest.raises(NotImplementedError, match="Non-legacy McpTool"):
        setup_from_registry(reg, mcp_mock)


def test_setup_from_registry_collects_all_errors_before_raising():
    """All tools are attempted before raising — errors are batched."""
    class _NativeTool(McpTool):
        def __init__(self, n: str):
            self._name = n

        @property
        def name(self) -> str:
            return self._name

        @property
        def schema(self) -> dict[str, Any]:
            return {}

        def handler(self, args: dict[str, Any]) -> dict[str, Any]:
            return {}

    reg = Registry()
    reg.register_mcp_tool(_NativeTool("tool_a"))
    reg.register_mcp_tool(_NativeTool("tool_b"))
    mcp_mock = MagicMock()

    with pytest.raises(NotImplementedError) as exc_info:
        setup_from_registry(reg, mcp_mock)
    msg = str(exc_info.value)
    assert "tool_a" in msg
    assert "tool_b" in msg


def test_setup_from_registry_uses_register_method_for_non_legacy():
    """Tools with a register(mcp) method bypass the NotImplementedError path."""
    class _NativeTool(McpTool):
        def __init__(self):
            self.registered_with: Any = None

        @property
        def name(self) -> str:
            return "native_tool"

        @property
        def schema(self) -> dict[str, Any]:
            return {}

        def handler(self, args: dict[str, Any]) -> dict[str, Any]:
            return {}

        def register(self, mcp_instance: Any) -> None:
            self.registered_with = mcp_instance

    tool = _NativeTool()
    reg = Registry()
    reg.register_mcp_tool(tool)
    mcp_mock = MagicMock()

    setup_from_registry(reg, mcp_mock)
    assert tool.registered_with is mcp_mock


def test_legacy_mcp_tool_get_fn_raises_when_fn_name_empty():
    class _EmptyNameTool(_LegacyMcpTool):
        # _legacy_fn_name intentionally left as "" (default)
        @property
        def name(self) -> str:
            return "empty_name_tool"

    t = _EmptyNameTool()
    with pytest.raises(AttributeError, match="_legacy_fn_name is empty"):
        t._get_fn()


def test_legacy_mcp_tool_get_fn_caches_result():
    stub = _StubTool()
    sentinel_fn = MagicMock(name="fn")
    call_count = 0

    def mock_import(name: str):
        nonlocal call_count
        call_count += 1
        mod = MagicMock()
        mod.search_thoughts = sentinel_fn
        return mod

    with patch("importlib.import_module", side_effect=mock_import):
        fn1 = stub._get_fn()
        fn2 = stub._get_fn()

    assert fn1 is fn2
    assert call_count == 1  # import_module called only once


def test_setup_from_registry_empty_registry_no_calls():
    reg = Registry()
    mcp_mock = MagicMock()
    setup_from_registry(reg, mcp_mock)
    mcp_mock.add_tool.assert_not_called()


# ── No acme/globex in mcp/tools/ ───────────────────────────────────────────────

def test_no_acme_or_globex_in_mcp_tools_package():
    import pathlib
    tools_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp" / "tools"
    forbidden = {"globex", "acme_pillar", "acme_topic", "acme_concept", "validate_coe"}
    violations: list[str] = []
    for py_file in tools_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for word in forbidden:
            if word in text:
                violations.append(f"{py_file.name}: contains '{word}'")
    assert violations == [], "\n".join(violations)


def test_no_get_gantt_data_in_mcp_tools_package():
    import pathlib
    tools_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp" / "tools"
    for py_file in tools_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "get_gantt_data" not in text, f"{py_file.name}: contains 'get_gantt_data'"


# ── mcp_server.py — GLOBEX tools removed ──────────────────────────────────────

def test_mcp_server_no_validate_coe():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "validate_coe_page" not in text


def test_mcp_server_no_unvalidate_coe():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "unvalidate_coe_page" not in text


def test_mcp_server_no_prepare_meeting_brief():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "prepare_meeting_brief" not in text


def test_mcp_server_no_get_gantt_data():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "get_gantt_data" not in text


def test_mcp_server_no_backlog_adapter_import():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "backlog_adapter" not in text


def test_mcp_server_no_acme_helpers():
    import pathlib
    srv = pathlib.Path(__file__).resolve().parent.parent.parent / "exocortex" / "mcp_server.py"
    text = srv.read_text(encoding="utf-8")
    assert "_acme_validate_target_paths" not in text
    assert "_acme_set_human_validated" not in text
