# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Wiki compilation package.

Public façade:
  from exocortex.wiki.runner import RunContext, setup_builtins, compile_all
  from exocortex.wiki.domains.base import DomainCompiler, _LegacyDomainCompiler
"""

from exocortex.wiki.runner import RunContext, compile_all, setup_builtins
from exocortex.wiki.domains.base import DomainCompiler

__all__ = [
    "RunContext",
    "compile_all",
    "setup_builtins",
    "DomainCompiler",
]
