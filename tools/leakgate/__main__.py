"""Command line interface: python -m tools.leakgate <command> ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .denylist import Denylist, KeyError_, build, load_key
from .scan import DATA_DIR, Config, Finding, Scanner, exit_code

DEFAULT_HASHES = DATA_DIR / "denylist.hmac.json"


def _scanner(args: argparse.Namespace) -> Scanner:
    key = load_key()
    denylist = Denylist.load(Path(args.hashes), key)
    config = Config.load(Path(args.allowlist) if args.allowlist else None)
    root = Path(args.root).resolve() if getattr(args, "root", None) else None
    return Scanner(denylist, config, root)


def _reveal_allowed(args: argparse.Namespace) -> bool:
    """Showing matched text is for the private operator only, never in CI."""
    if not args.reveal:
        return False
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("LEAKGATE_ALLOW_REVEAL") != "1":
        print("leakgate: --reveal needs LEAKGATE_ALLOW_REVEAL=1 and is refused in CI", file=sys.stderr)
        return False
    return True


def _report(findings: list[Finding], args: argparse.Namespace) -> int:
    code = exit_code(findings, strict=args.strict)
    reveal = _reveal_allowed(args)
    if args.json:
        Path(args.json).write_text(json.dumps([f.to_dict(reveal) for f in findings], indent=2), encoding="utf-8")
    for f in findings:
        note = f" ({f.note})" if f.note else ""
        shown = f" [{f.excerpt}]" if reveal and f.excerpt else ""
        print(f"{f.tier.upper():5} {f.path}:{f.line} {f.rule} {f.digest}{note}{shown}")
    blocks = sum(f.tier == "block" for f in findings)
    warns = sum(f.tier == "warn" for f in findings)
    print(f"leakgate: {blocks} block, {warns} warn -> {'FAIL' if code else 'OK'}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="leakgate", description="Publishing gate for client material.")
    p.add_argument("--hashes", default=str(DEFAULT_HASHES), help="hashed denylist file")
    p.add_argument("--allowlist", default=None, help="allowlist YAML (default: bundled)")
    p.add_argument("--json", default=None, help="write findings as JSON to this file")
    p.add_argument("--strict", action="store_true", help="treat warn findings as failures")
    p.add_argument("--reveal", action="store_true", help="print matched text (private use only, refused in CI)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build-denylist", help="build the hashed denylist from the private YAML")
    b.add_argument("--source", required=True)
    b.add_argument("--out", default=str(DEFAULT_HASHES))

    s = sub.add_parser("scan", help="scan files and directories")
    s.add_argument("paths", nargs="+")
    s.add_argument("--root", default=None, help="repository root for relative paths and corpus manifests")

    for name in ("scan-wheel", "scan-sdist"):
        w = sub.add_parser(name, help=f"unpack and scan a {name.split('-')[1]}")
        w.add_argument("file")

    i = sub.add_parser("scan-image", help="scan a docker-archive tar or OCI layout")
    i.add_argument("image")

    g = sub.add_parser("scan-git", help="scan author data and messages of commits in a range")
    g.add_argument("--repo", default=".")
    g.add_argument("--range", dest="rev_range", default="origin/main..HEAD")

    t = sub.add_parser("strip", help="remove metadata from files in place")
    t.add_argument("files", nargs="+")

    st = sub.add_parser("selftest", help="run the gate self-test with planted canaries")
    st.add_argument("--lock-file", default=None, help="create this file when a case slips through")
    st.add_argument("--results", default=None, help="write a JSON summary here")
    st.add_argument("--private-cases", default=None, help="YAML with private real-name cases (never public)")

    args = p.parse_args(argv)
    try:
        if args.cmd == "build-denylist":
            cfg = Config.load(Path(args.allowlist) if args.allowlist else None)
            data = build(Path(args.source), load_key(), cfg.email_allow)
            Path(args.out).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {args.out}: {data['count']} hashes, key id {data['key_id']}")
            return 0
        if args.cmd == "strip":
            from .strip import strip_file

            for f in args.files:
                print(f"{f}: {strip_file(Path(f))}")
            return 0
        if args.cmd == "selftest":
            from .selftest import run_selftest

            return run_selftest(args)
        scanner = _scanner(args)
        if args.cmd == "scan":
            findings: list[Finding] = []
            for path in args.paths:
                findings.extend(scanner.scan_path(Path(path)))
            return _report(findings, args)
        if args.cmd in ("scan-wheel", "scan-sdist"):
            from .artifacts import scan_package

            return _report(scan_package(scanner, Path(args.file)), args)
        if args.cmd == "scan-image":
            from .artifacts import scan_image

            return _report(scan_image(scanner, Path(args.image)), args)
        if args.cmd == "scan-git":
            from .gitscan import scan_commits

            return _report(scan_commits(scanner, Path(args.repo), args.rev_range), args)
    except KeyError_ as exc:
        print(f"leakgate: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
