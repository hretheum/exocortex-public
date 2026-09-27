"""Text normalisation shared by the denylist builder and the scanner.

Both sides must produce identical tokens for the same input, otherwise hashes
will not match. Keep every transformation here and nowhere else.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse

# Characters that render as nothing but split a word for naive matching.
_ZERO_WIDTH = dict.fromkeys(
    map(ord, "​‌‍⁠﻿­᠎⁡⁢⁣⁤"),
    None,
)

# Look-alike letters from Cyrillic and Greek mapped to Latin. NFKC already
# folds full-width forms and most compatibility characters.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h",
        "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i",
        "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w",
        "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v",
        "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ω": "w", "ѵ": "v",
    }
)

# Polish letters that NFKD does not decompose into base letter + mark.
_FOLD_EXTRA = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"})

_LEET = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"})

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Inflection endings used to generate forms of denylist terms. Generation
# happens only on the denylist side; text tokens are compared as they are.
CONSONANT_SUFFIXES = (
    "u", "owi", "em", "ie", "y", "a", "e", "ach", "ami", "om", "ow",
    "owy", "owa", "owe", "owego", "owej", "owemu", "owym", "owych", "owymi",
    "owski", "owska", "owskie", "owskiego", "owskich",
)
VOWEL_SUFFIXES = ("a", "y", "i", "e", "o", "ie", "ze", "om", "ami", "ach")
MIN_TOKEN = 2


def fold(text: str) -> str:
    """Return lower-case text with look-alikes, invisible characters and diacritics folded."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZERO_WIDTH)
    text = text.lower()
    text = text.translate(_CONFUSABLES)
    text = text.translate(_FOLD_EXTRA)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def decode_layers(text: str) -> list[str]:
    """Return the text plus decoded variants that could hide a name.

    Covers percent-encoding and JSON-style unicode escapes. The caller scans
    every returned variant.
    """
    variants = [text]
    if "%" in text:
        try:
            decoded = urllib.parse.unquote(text)
            if decoded != text:
                variants.append(decoded)
        except Exception:  # noqa: BLE001 - best effort
            pass
    if "\\u" in text or "\\x" in text:
        try:
            decoded = re.sub(
                r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
                lambda m: chr(int(m.group(1) or m.group(2), 16)),
                text,
            )
            if decoded != text:
                variants.append(decoded)
        except Exception:  # noqa: BLE001 - best effort
            pass
    return variants


def tokens(text: str) -> list[str]:
    """Split folded text into alphanumeric tokens."""
    return _TOKEN_RE.findall(fold(text))


def token_variants(token: str) -> set[str]:
    """Forms of a text token worth checking: itself, digits stripped, leet decoded."""
    out = {token}
    frontier = [token]
    while frontier:
        tok = frontier.pop()
        for cand in (tok.rstrip("0123456789"), tok.translate(_LEET)):
            if len(cand) >= MIN_TOKEN and cand not in out:
                out.add(cand)
                frontier.append(cand)
    return out


def canonical(token: str) -> str:
    """Single canonical form: leet decoded, trailing digits removed."""
    out = token.translate(_LEET).rstrip("0123456789")
    return out if len(out) >= MIN_TOKEN else token


def term_forms(term: str) -> dict[str, bool]:
    """Keys a denylist term is stored under, mapped to "is generated".

    Exact forms are the folded token sequence joined with a space and joined
    without a space. Generated forms add Polish inflections of the last token.
    Generated forms can collide with ordinary words (for example a stem plus
    "y" giving an English word), so the builder downgrades them to the warn
    tier when the term ends in a vowel.
    """
    toks = tokens(term)
    if not toks:
        return {}
    forms: dict[str, bool] = {" ".join(toks): False, "".join(toks): False}
    last = toks[-1]
    head = toks[:-1]
    generated: set[str] = set()
    if last[-1] in "aeiouy":
        stem = last[:-1]
        if len(stem) >= 3:
            generated |= {stem + suf for suf in VOWEL_SUFFIXES}
    elif len(last) >= 3 and last.isalpha():
        generated |= {last + suf for suf in CONSONANT_SUFFIXES}
    for g in generated:
        key = " ".join(head + [g])
        forms.setdefault(key, True)
        forms.setdefault("".join(head + [g]), True)
    return forms
