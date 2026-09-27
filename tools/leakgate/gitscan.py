"""Scanning git metadata of commits that are about to be pushed."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .scan import Finding, Scanner

SEP = "\x1e"


def scan_commits(scanner: Scanner, repo: Path, rev_range: str | None) -> list[Finding]:
    if rev_range is None:
        has_origin = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "origin/main"],
            capture_output=True,
        ).returncode == 0
        rev_range = "origin/main..HEAD" if has_origin else "HEAD"
    fmt = SEP.join(["%H", "%an", "%ae", "%cn", "%ce", "%B"]) + "\x1f"
    out = subprocess.run(
        ["git", "-C", str(repo), "log", f"--format={fmt}", rev_range],
        check=True, capture_output=True, text=True,
    ).stdout
    found: list[Finding] = []
    for record in filter(None, (r.strip("\n") for r in out.split("\x1f"))):
        sha, an, ae, cn, ce, body = record.split(SEP, 5)
        label = f"commit:{sha[:12]}"
        text = f"{an} <{ae}>\n{cn} <{ce}>\n{body}"
        found.extend(scanner.scan_text(label, text))
    return found
