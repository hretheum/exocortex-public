# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Auto-stub missing runtime dependencies for isolated unit tests.

A sys.meta_path loader intercepts ANY ImportError for modules not installed in
the test venv and returns an empty MagicMock stub.  This lets unit tests for
pure-Python registry/ABC code run without installing psycopg, anthropic, etc.

Only modules listed in _PASS_THROUGH are NOT stubbed (they must be real).
"""
from __future__ import annotations

import sys
import types
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from unittest.mock import MagicMock

_PASS_THROUGH = frozenset(
    {
        # stdlib — always real
        "abc",
        "collections",
        "contextlib",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "importlib",
        "importlib.abc",
        "importlib.machinery",
        "importlib.metadata",
        "importlib.util",
        "io",
        "itertools",
        "json",
        "logging",
        "math",
        "os",
        "pathlib",
        "re",
        "sys",
        "threading",
        "time",
        "types",
        "typing",
        "unittest",
        "unittest.mock",
        "warnings",
        # test packages — must be real
        "pytest",
        "_pytest",
        "pluggy",
        # exocortex core under test — must be real
        "exocortex",
        "exocortex.cli",
        "exocortex.core",
        "exocortex.core.db",
        "exocortex.core.db.migrations",
        "exocortex.core.registry",
        "exocortex.graph_rag_prompt",
        "exocortex.integrations",
        "exocortex.prompts",
        "exocortex.prompts.graph_rag",
        "exocortex.live_sections",
        "exocortex.live_sections.base",
        "exocortex.mcp",
        "exocortex.mcp.tools",
        "exocortex.mcp.tools.base",
        "exocortex.processors",
        "exocortex.processors.base",
        "exocortex.settings",
        "exocortex.synth",
        "exocortex.synth.perspectives",
        "exocortex.synth.perspectives.base",
        "exocortex.wiki",
        "exocortex.wiki.domains",
        "exocortex.wiki.domains.base",
        # third-party dependencies of settings/integrations — must be real
        "pydantic",
        "pydantic_settings",
        # template rendering (F31.8.2)
        "jinja2",
        "markupsafe",
        # psycopg3 + pool: the binary C extension must never be stubbed —
        # stubbing it causes psycopg/pq/__init__.py to crash on __impl__
        # when it calls import_from_libpq() and gets a MagicMock back.
        "psycopg",
        "psycopg_pool",
    }
)


class _StubLoader(Loader):
    def create_module(self, spec: ModuleSpec):
        mod = types.ModuleType(spec.name)
        mod.__spec__ = spec  # type: ignore[assignment]
        # Make every attribute access return a MagicMock so dotted calls work
        _m = MagicMock(name=spec.name)
        mod.__class__ = type(
            "_StubModule",
            (types.ModuleType,),
            {"__getattr__": lambda self, name: _m},
        )
        return mod

    def exec_module(self, module):
        pass  # no execution needed — stub is already set up


class _AutoStubFinder(MetaPathFinder):
    """Return a stub for any module that would otherwise fail to import."""

    def find_spec(self, fullname, path, target=None):
        # Let real modules resolve normally
        if fullname in _PASS_THROUGH:
            return None
        if fullname.startswith(tuple(_PASS_THROUGH)):
            return None
        # If the module is already (successfully) loaded, skip
        if fullname in sys.modules:
            return None
        # Try to find it through the normal chain first
        for finder in sys.meta_path:
            if finder is self:
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                return None  # real module found — let it load normally
        # Nothing found → return a stub spec
        return ModuleSpec(fullname, _StubLoader())


# Install once when conftest is loaded
_finder = _AutoStubFinder()
if _finder not in sys.meta_path:
    sys.meta_path.insert(0, _finder)
