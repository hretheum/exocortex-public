# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Exocortex ACME Corp example plugin.

This package is a *minimal, working* community plugin. It registers three
extension points so a community-author can copy this directory, rename
``acme`` → ``their_client``, and have a working starting point.

Extension points exercised:
    - perspective:    ``acme_client_review`` — synth one summary per quarter
    - mcp tool:       ``acme_quarterly_status`` — read-only DB peek
    - compile domain: ``acme`` — render ``wiki/acme/_index.md``

See ../README.md for the smoke-test commands.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exocortex.core.registry import Registry


def setup(registry: "Registry") -> None:
    """Plugin entry-point invoked by the engine at startup.

    Imports are local so that loading the plugin's metadata (e.g. for
    ``importlib.metadata.entry_points`` listing) does not pull in the
    full Exocortex runtime — useful when you only want to verify the
    plugin is installed.
    """
    from .perspectives import AcmeClientReview
    from .mcp_tools import AcmeQuarterlyStatus
    from .wiki import AcmeDomainCompiler

    registry.register_perspective(AcmeClientReview())
    registry.register_mcp_tool(AcmeQuarterlyStatus())
    registry.register_compile_domain(AcmeDomainCompiler())
