# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""exocortex.synth — registry-driven synthesis engine."""
from exocortex.synth.runner import SynthContext, run, setup_builtins

__all__ = ["SynthContext", "run", "setup_builtins"]
