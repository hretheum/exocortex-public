# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Domain compiler modules.

Each sub-module exposes a setup(registry) function that registers its
DomainCompiler subclasses into the provided Registry.
"""

from exocortex.wiki.domains import (
    clippings,
    cross_domain,
    live_sections,
)
from exocortex.wiki.domains.frp import setup as frp_setup
from exocortex.wiki.domains.home import setup as home_setup
from exocortex.wiki.domains.news import setup as news_setup
from exocortex.wiki.domains.work import setup as work_setup

__all__ = [
    "clippings",
    "cross_domain",
    "live_sections",
    "frp_setup",
    "home_setup",
    "news_setup",
    "work_setup",
]
