"""Building and matching the hashed denylist.

The private source list (YAML, kept outside the repository) is turned into a
set of HMAC-SHA256 hashes of normalised forms. Scanning hashes every candidate
form found in the text with the same key and looks it up in that set. Without
the key the hash file reveals nothing, and a dictionary attack does not work
because every hash depends on the key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .normalize import canonical, term_forms, token_variants, tokens

BLOCK = "block"
WARN = "warn"
_RANK = {WARN: 1, BLOCK: 2}
MAX_N = 4
JOIN_MIN_PART = 3
GENERIC_LOCAL_PARTS = {"info", "admin", "contact", "kontakt", "biuro", "office", "noreply", "hello", "team",
                       "jan.kowalski", "jkowalski", "john.doe", "jane.doe", "test", "user", "example"}


class KeyError_(RuntimeError):
    """Raised when the HMAC key is missing or does not match the hash file."""


def load_key() -> bytes:
    """Read the HMAC key from LEAKGATE_HMAC_KEY (hex) or LEAKGATE_HMAC_KEY_FILE."""
    raw = os.environ.get("LEAKGATE_HMAC_KEY")
    path = os.environ.get("LEAKGATE_HMAC_KEY_FILE")
    if not raw and path:
        raw = Path(path).expanduser().read_text(encoding="utf-8").strip()
    if not raw:
        raise KeyError_("no HMAC key: set LEAKGATE_HMAC_KEY or LEAKGATE_HMAC_KEY_FILE")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise KeyError_("HMAC key must be hex") from exc
    if len(key) < 16:
        raise KeyError_("HMAC key too short, need at least 16 bytes")
    return key


def key_id(key: bytes) -> str:
    return hashlib.sha256(b"leakgate-key-id:" + key).hexdigest()[:12]


def digest(key: bytes, form: str) -> str:
    return hmac.new(key, form.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _stronger(a: str | None, b: str) -> str:
    if a is None:
        return b
    return a if _RANK[a] >= _RANK[b] else b


def build(source: Path, key: bytes, email_allow: list[str] | None = None) -> dict:
    """Build the public hash file content from the private YAML source.

    Addresses matching the public email allowlist (for example the author's
    own address) are skipped, otherwise the gate would block the allowlist.
    """
    import fnmatch

    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    email_allow = [p.lower() for p in (email_allow or [])]
    hashes: dict[str, str] = {}

    def add(form: str, tier: str) -> None:
        h = digest(key, form)
        hashes[h] = _stronger(hashes.get(h), tier)

    excluded = {" ".join(tokens(f)) for f in data.get("exclude_forms", []) or []}
    for entry in data.get("entries", []):
        term, tier = entry["term"], entry.get("tier", BLOCK)
        for form, generated in term_forms(term).items():
            if generated and form in excluded:
                continue
            if generated and form[-1:] and tokens(term)[-1][-1] in "aeiouy":
                add(form, WARN)
            else:
                add(form, tier)
    for rel in data.get("extra_email_files", []):
        path = (source.parent / rel).resolve()
        for line in path.read_text(encoding="utf-8").splitlines():
            email = line.strip().lower()
            if "@" not in email or any(fnmatch.fnmatch(email, p) for p in email_allow):
                continue
            for form in term_forms(email):
                add(form, BLOCK)
            local = email.split("@", 1)[0]
            if local not in GENERIC_LOCAL_PARTS:
                for form in term_forms(local):
                    if len(form.replace(" ", "")) >= 5:
                        add(form, BLOCK if len(form) >= 6 else WARN)
    return {
        "version": 1,
        "key_id": key_id(key),
        "max_n": MAX_N,
        "count": len(hashes),
        "hashes": dict(sorted(hashes.items())),
    }


@dataclass(frozen=True)
class Match:
    line: int
    tier: str
    digest: str
    n: int
    form: str = ""


class Denylist:
    """Hashed denylist loaded from the public JSON file."""

    def __init__(self, hashes: dict[str, str], key: bytes, max_n: int = MAX_N):
        self.hashes = hashes
        self.key = key
        self.max_n = max_n

    @classmethod
    def load(cls, path: Path, key: bytes) -> "Denylist":
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("key_id") != key_id(key):
            raise KeyError_(f"hash file {path} was built with a different key")
        return cls(data["hashes"], key, data.get("max_n", MAX_N))

    def _lookup(self, form: str) -> tuple[str, str] | None:
        h = digest(self.key, form)
        tier = self.hashes.get(h)
        return (tier, h) if tier else None

    def match_tokens(self, toks: list[tuple[str, int]]) -> list[Match]:
        """Match (token, line) pairs; returns one Match per hit."""
        found: list[Match] = []
        words = [t for t, _ in toks]
        canon = [canonical(w) for w in words]
        sequences = [words] if canon == words else [words, canon]
        for i in range(len(words)):
            line = toks[i][1]
            for variant in token_variants(words[i]):
                hit = self._lookup(variant)
                if hit:
                    found.append(Match(line, hit[0], hit[1], 1, variant))
            for n in range(2, self.max_n + 1):
                if i + n > len(words):
                    break
                forms: set[str] = set()
                for seq in sequences:
                    gram = seq[i : i + n]
                    forms.add(" ".join(gram))
                    # Joining without a space catches a name split in two
                    # ("Enx oo"), but short parts ("or len") join into
                    # ordinary words far too often, so require 3+ letters each.
                    if all(len(part) >= JOIN_MIN_PART for part in gram):
                        forms.add("".join(gram))
                for form in forms:
                    hit = self._lookup(form)
                    if hit:
                        found.append(Match(line, hit[0], hit[1], n, form))
        return found
