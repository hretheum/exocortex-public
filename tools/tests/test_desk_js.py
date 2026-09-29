"""Runs the page logic tests in Node with its built-in runner (no browser needed)."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS_TEST = Path(__file__).parent / "js" / "desk.test.cjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_desk_logic_in_node():
    r = subprocess.run(["node", "--test", str(JS_TEST)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
