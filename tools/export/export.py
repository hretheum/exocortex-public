"""Export the public part of the private working repository.

Copies only files tracked by git that match tools/export/allowlist.txt, then
optionally applies a private replacement map (kept outside the repository,
because it names what is being replaced). The result is scanned by leakgate
before anything is committed.

    python -m tools.export.export --src ../exocortex --dest /tmp/export \
        [--replacements /private/path/export-replacements.yaml]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ALLOWLIST = Path(__file__).with_name("allowlist.txt")
TEXT_SUFFIXES = {".py", ".md", ".sql", ".yaml", ".yml", ".toml", ".txt", ".json", ".sh", ".service", ".timer",
                 ".container", ".mjs", ".ts", ".astro", ".css", ".j2", ".cfg", ".ini", ""}


def load_rules(path: Path) -> list[tuple[bool, str]]:
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rules.append((not line.startswith("!"), line.lstrip("!")))
    return rules


def selected(path: str, rules: list[tuple[bool, str]]) -> bool:
    keep = False
    for include, pattern in rules:
        pat = pattern.replace("**", "*")
        if fnmatch.fnmatch(path, pat) or (pattern.endswith("/**") and path.startswith(pattern[:-3] + "/")):
            keep = include
    return keep


def apply_replacements(text: str, rules: list[dict]) -> tuple[str, int]:
    count = 0
    for r in rules:
        pattern = r["pattern"] if r.get("regex") else re.escape(r["pattern"])
        flags = re.IGNORECASE if r.get("ignore_case") else 0
        text, n = re.subn(pattern, r["replace"], text, flags=flags)
        count += n
    return text, count


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--allowlist", default=str(ALLOWLIST))
    p.add_argument("--replacements", default=None)
    args = p.parse_args(argv)
    src, dest = Path(args.src).resolve(), Path(args.dest).resolve()
    rules = load_rules(Path(args.allowlist))
    files = subprocess.run(["git", "-C", str(src), "ls-files"], check=True, capture_output=True, text=True).stdout.split("\n")
    repl = []
    if args.replacements:
        repl = yaml.safe_load(Path(args.replacements).read_text(encoding="utf-8")).get("replacements", [])
    copied = changed = 0
    for rel in filter(None, files):
        if not selected(rel, rules):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        source = src / rel
        if repl and Path(rel).suffix in TEXT_SUFFIXES:
            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(source, target)
            else:
                text, n = apply_replacements(text, repl)
                changed += n
                target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(source, target)
        copied += 1
    print(f"exported {copied} files, {changed} replacements applied", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
