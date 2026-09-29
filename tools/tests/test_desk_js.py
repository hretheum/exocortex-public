"""Runs the page logic and render tests in Node with its built-in runner (no browser needed)."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted((Path(__file__).parent / "js").glob("*.test.cjs"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_desk_scripts_in_node():
    r = subprocess.run(["node", "--test", *map(str, JS_TESTS)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
