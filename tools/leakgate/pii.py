"""Personal data detectors.

All detectors return (line, rule_id, matched_text). The scanner hashes the
matched text before it goes into a report; nothing here prints it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
from datetime import date
from pathlib import Path

EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b")
PHONE_RE = re.compile(
    r"(?<![\w+])(?:\+48[ -]?|0048[ -]?)?(?:\d{3}[ -]\d{3}[ -]\d{3}|\(\d{2}\)[ -]?\d{3}[ -]\d{2}[ -]\d{2})(?!\w)"
    r"|(?<![\w+])\+(?!48)\d{1,3}[ -]\d{2,4}[ -]\d{3,4}[ -]\d{3,4}(?!\w)"
)
PESEL_RE = re.compile(r"(?<![0-9A-Za-z])\d{11}(?![0-9A-Za-z])")
NIP_RE = re.compile(r"(?<![0-9A-Za-z])(\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3})(?![0-9A-Za-z])|(?i:\bnip\b[:\s]*)(\d{10})(?!\d)")
REGON_RE = re.compile(r"(?i:\bregon\b[:\s]*)(\d{14}|\d{9})(?!\d)")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")

# Common Polish first names (public data), stored as truncated SHA-256 hashes
# so that the list itself does not trigger the person-name rule. Used only as a
# hint for a "first name + capitalised word" pattern, reported at warn tier.
_NAMES_FILE = Path(__file__).parent / "data" / "first_names.sha256"
FIRST_NAME_HASHES = {
    line.strip() for line in _NAMES_FILE.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")
}


def _is_first_name(word: str) -> bool:
    return hashlib.sha256(word.lower().encode()).hexdigest()[:12] in FIRST_NAME_HASHES


NAME_PAIR_RE = re.compile(r"\b([A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,})\s+([A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,}(?:-[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,})?)\b")


def _pesel_ok(s: str) -> bool:
    w = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    d = [int(c) for c in s]
    if (10 - sum(a * b for a, b in zip(w, d[:10])) % 10) % 10 != d[10]:
        return False
    yy, mm, dd = int(s[0:2]), int(s[2:4]), int(s[4:6])
    century = {0: 1900, 20: 2000, 40: 2100, 60: 2200, 80: 1800}
    for off, base in century.items():
        if off < mm <= off + 12 or (off == 0 and 1 <= mm <= 12):
            try:
                date(base + yy, mm - off, dd)
                return True
            except ValueError:
                return False
    return False


def _nip_ok(s: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if len(d) != 10:
        return False
    w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    return sum(a * b for a, b in zip(w, d[:9])) % 11 == d[9]


def _regon_ok(s: str) -> bool:
    d = [int(c) for c in s]
    if len(d) == 9:
        w = [8, 9, 2, 3, 4, 5, 6, 7]
    elif len(d) == 14:
        w = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]
    else:
        return False
    return sum(a * b for a, b in zip(w, d[:-1])) % 11 % 10 == d[-1]


def _iban_ok(s: str) -> bool:
    s = s.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    num = "".join(str(int(c, 36)) for c in moved)
    return int(num) % 97 == 1


def _email_allowed(email: str, allow: list[str]) -> bool:
    email = email.lower()
    return any(fnmatch.fnmatch(email, pat.lower()) for pat in allow)


def detect(text: str, email_allow: list[str], name_allow: list[str]) -> list[tuple[int, str, str, str]]:
    """Return (line, rule, tier, matched) for personal data in text."""
    out: list[tuple[int, str, str, str]] = []
    names_ok = {n.lower() for n in name_allow}
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in EMAIL_RE.finditer(line):
            if not _email_allowed(m.group(0), email_allow):
                out.append((lineno, "pii.email", "block", m.group(0)))
        for m in PHONE_RE.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) >= 9:
                out.append((lineno, "pii.phone", "block", m.group(0)))
        for m in PESEL_RE.finditer(line):
            if _pesel_ok(m.group(0)):
                out.append((lineno, "pii.pesel", "block", m.group(0)))
        for m in NIP_RE.finditer(line):
            val = m.group(1) or m.group(2)
            if val and _nip_ok(val):
                out.append((lineno, "pii.nip", "block", val))
        for m in REGON_RE.finditer(line):
            if _regon_ok(m.group(1)):
                out.append((lineno, "pii.regon", "block", m.group(1)))
        for m in IBAN_RE.finditer(line):
            if _iban_ok(m.group(0)):
                out.append((lineno, "pii.iban", "block", m.group(0)))
        for m in NAME_PAIR_RE.finditer(line):
            first, last = m.group(1), m.group(2)
            if _is_first_name(first) and f"{first} {last}".lower() not in names_ok:
                out.append((lineno, "pii.person_name", "warn", m.group(0)))
    return out
