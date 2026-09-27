"""The scanning engine: files and text in, findings out."""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import hmac
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from . import pii
from .denylist import BLOCK, WARN, Denylist
from .meta import extract
from .normalize import decode_layers, fold, tokens

DATA_DIR = Path(__file__).parent / "data"
MAX_DEPTH = 6


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    tier: str
    digest: str
    note: str = ""
    excerpt: str = field(default="", repr=False)

    def to_dict(self, reveal: bool = False) -> dict:
        d = asdict(self)
        if not reveal:
            d.pop("excerpt")
        return d


@dataclass
class Config:
    email_allow: list[str]
    name_allow: list[str]
    ack_hashes: set[str]
    corpus: list[dict]
    exclude_dirs: set[str]

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or DATA_DIR / "allowlist.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            email_allow=[e["pattern"] for e in data.get("emails", [])],
            name_allow=[n["name"] for n in data.get("names", [])],
            ack_hashes={a["hash"] for a in data.get("ack_hashes", []) or []},
            corpus=data.get("corpus", []) or [],
            exclude_dirs=set(data.get("exclude_dirs", [])),
        )


class Scanner:
    def __init__(self, denylist: Denylist, config: Config, root: Path | None = None):
        self.denylist = denylist
        self.config = config
        self.root = root
        self._manifest_cache: dict[Path, set[str]] = {}

    # -- helpers -----------------------------------------------------------
    def _pii_digest(self, text: str) -> str:
        return hmac.new(self.denylist.key, ("pii:" + fold(text)).encode(), hashlib.sha256).hexdigest()[:32]

    def _corpus_verified(self, rel: str, data: bytes) -> bool:
        for rule in self.config.corpus:
            if fnmatch.fnmatch(rel, rule["glob"]) and self.root is not None:
                parts = Path(rel).parts
                # corpus root is the folder that holds the manifest: dowody/corpus/<name>
                for depth in range(len(parts) - 1, 0, -1):
                    manifest = self.root.joinpath(*parts[:depth]) / rule["manifest"]
                    if manifest.is_file():
                        hashes = self._manifest_hashes(manifest)
                        return hashlib.sha256(data).hexdigest() in hashes
        return False

    def _manifest_hashes(self, manifest: Path) -> set[str]:
        if manifest not in self._manifest_cache:
            with manifest.open(encoding="utf-8") as fh:
                self._manifest_cache[manifest] = {
                    row.get("sha256_file", "").strip().lower() for row in csv.DictReader(fh)
                }
        return self._manifest_cache[manifest]

    # -- text ---------------------------------------------------------------
    def scan_text(self, label: str, text: str, skip_denylist: bool = False) -> list[Finding]:
        found: list[Finding] = []
        seen: set[tuple[int, str]] = set()
        for variant in decode_layers(text):
            if not skip_denylist:
                toks = []
                for lineno, line in enumerate(variant.splitlines() or [variant], start=1):
                    toks.extend((t, lineno) for t in tokens(line))
                for m in self.denylist.match_tokens(toks):
                    if m.digest in self.config.ack_hashes or (m.line, m.digest) in seen:
                        continue
                    seen.add((m.line, m.digest))
                    found.append(Finding(label, m.line, "denylist", m.tier, m.digest, excerpt=m.form))
            for line, rule, tier, matched in pii.detect(variant, self.config.email_allow, self.config.name_allow):
                d = self._pii_digest(matched)
                if (line, d) in seen or d in self.config.ack_hashes:
                    continue
                seen.add((line, d))
                found.append(Finding(label, line, rule, tier, d, excerpt=matched))
        return found

    # -- files --------------------------------------------------------------
    def scan_bytes(self, rel: str, data: bytes, depth: int = 0, compiled_ok: bool = False) -> list[Finding]:
        found: list[Finding] = []
        if depth > MAX_DEPTH:
            return [Finding(rel, 0, "file.nesting_too_deep", BLOCK, "")]
        skip_deny = depth == 0 and self._corpus_verified(rel, data)
        ex = extract(rel, data, compiled_ok=compiled_ok)
        for rule, tier, note in ex.meta:
            found.append(Finding(rel, 0, rule, tier, "", note))
        for label, text in ex.parts:
            where = rel if label in ("text", "path") else f"{rel}#{label}"
            if label == "path":
                found.extend(self.scan_text(where, text, skip_denylist=False))
            else:
                found.extend(self.scan_text(where, text, skip_denylist=skip_deny))
        for child_name, child_data in ex.children:
            found.extend(self.scan_bytes(f"{rel}!/{child_name}", child_data, depth + 1, compiled_ok))
        return found

    def scan_path(self, path: Path) -> list[Finding]:
        path = path.resolve()
        base = self.root.resolve() if self.root else (path if path.is_dir() else path.parent)
        files: list[Path] = []
        if path.is_file():
            files = [path]
        else:
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [d for d in dirnames if d not in self.config.exclude_dirs]
                files.extend(Path(dirpath) / f for f in filenames)
        found: list[Finding] = []
        for f in sorted(files):
            try:
                rel = f.relative_to(base).as_posix()
            except ValueError:
                rel = f.as_posix()
            found.extend(self.scan_bytes(rel, f.read_bytes()))
        return found


def exit_code(findings: list[Finding], strict: bool = False) -> int:
    if any(f.tier == BLOCK for f in findings):
        return 1
    if strict and any(f.tier == WARN for f in findings):
        return 1
    return 0
