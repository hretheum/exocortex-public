"""Gate self-test: plant canaries in many shapes and require every one caught.

Canaries are random words generated at run time with a throwaway key, so the
public repository never contains them in plain text. The optional private
suite takes real names from a private YAML file and runs only on machines
that hold the real key.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import os
import random
import secrets
import string
import subprocess
import tarfile
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .denylist import Denylist, digest, key_id
from .gitscan import scan_commits
from .artifacts import scan_image
from .normalize import term_forms
from .scan import Config, Scanner

HOMOGLYPHS = {"a": "а", "o": "о", "e": "е", "c": "с", "p": "р", "x": "х"}


@dataclass
class Case:
    cid: str
    target: str | None  # term that must be found, None for a clean control
    kind: str


def _canaries(rng: random.Random) -> list[str]:
    def word(n: int) -> str:
        return "".join(rng.choice("bcdfghjklmnprstvwz") + rng.choice("aeiouy") for _ in range(n)) + rng.choice("klmnrst")

    return [
        word(3).capitalize(),
        "Żół" + word(2),
        word(2).capitalize() + " " + word(3).capitalize(),
    ]


def _jpeg_with_exif(text: str) -> bytes:
    payload = b"Exif\x00\x00MM\x00*\x00\x00\x00\x08" + text.encode("utf-8")
    seg = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return b"\xff\xd8" + seg + b"\xff\xd9"


def _png_with_text(text: str) -> bytes:
    import zlib

    def chunk(t: bytes, d: bytes) -> bytes:
        return len(d).to_bytes(4, "big") + t + d + zlib.crc32(t + d).to_bytes(4, "big")

    ihdr = (1).to_bytes(4, "big") * 2 + b"\x08\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"iTXt", b"Comment\x00\x00\x00\x00\x00" + text.encode("utf-8")) + chunk(b"IEND", b"")


def _pdf_with_author(text: str) -> bytes:
    safe = text.encode("utf-8")
    return b"%PDF-1.4\n1 0 obj << /Author (" + safe + b") >> endobj\ntrailer << /Info 1 0 R >>\n%%EOF\n"


def _docx_with_comment(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document><w:t>quarterly plan</w:t></w:document>")
        z.writestr("word/comments.xml", f"<w:comments><w:t>{text}</w:t></w:comments>")
    return buf.getvalue()


def _wheel_with(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pkg/__init__.py", f"# maintained by {text}\n")
    return buf.getvalue()


def _targz_with(text: str) -> bytes:
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode="w:gz") as tf:
        data = f"notes about {text}\n".encode()
        info = tarfile.TarInfo("deep/notes.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return inner.getvalue()


def _docker_archive(file_text: str | None, env_text: str | None) -> bytes:
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as tf:
        data = (f"docs mention {file_text}\n" if file_text else "hello\n").encode()
        info = tarfile.TarInfo("opt/app/README.md")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    config = {"config": {"Env": [f"OWNER={env_text}"] if env_text else ["PATH=/usr/bin"]}, "history": []}
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tf:
        for name, data in (
            ("layer.tar", layer.getvalue()),
            ("config.json", json.dumps(config).encode()),
            ("manifest.json", json.dumps([{"Config": "config.json", "Layers": ["layer.tar"]}]).encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return out.getvalue()


def _homoglyph(term: str) -> str:
    return "".join(HOMOGLYPHS.get(ch, ch) for ch in term)


def _zero_width(term: str) -> str:
    mid = len(term) // 2
    return term[:mid] + "​" + term[mid:]


def _leet(term: str) -> str:
    return term.replace("o", "0").replace("e", "3", 1)


def _write_cases(base: Path, terms: list[str], rng: random.Random) -> list[tuple[Case, str, bytes]]:
    """Return (case, relative path, content) triples. Image and git cases are handled separately."""
    out: list[tuple[Case, str, bytes]] = []
    for i, term in enumerate(terms):
        one = term.split()[0]
        variants = {
            "plain": f"Meeting notes: {term} asked about the budget.\n",
            "upper": f"CC: {term.upper()}\n",
            "lower_nodiacritics": f"do {term.lower().translate(str.maketrans('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ', 'acelnoszzACELNOSZZ'))}\n",
            "inflected": f"Wysłano {term}owi raport.\n" if term[-1] not in "aeiouyAEIOUY" else f"Wysłano do {term[:-1]}y.\n",
            "zero_width": f"owner: {_zero_width(term)}\n",
            "homoglyph": f"owner: {_homoglyph(term)}\n",
            "leet": f"owner: {_leet(term.lower())}\n",
            "digits": f"login {term.replace(' ', '').lower()}2026\n",
            "code_comment": f"def f():\n    # ask {term} before changing this\n    return 1\n",
            "json_escaped": json.dumps({"owner": term}, ensure_ascii=True) + "\n",
            "percent_encoded": f"https://example.com/?q={urllib.parse.quote(term)}\n",
        }
        if " " in term:
            variants["split_line"] = term.replace(" ", "\n", 1) + " reviewed it.\n"
            variants["joined"] = term.replace(" ", "") + "\n"
        for kind, text in variants.items():
            target = term
            ext = ".py" if kind == "code_comment" else ".json" if kind == "json_escaped" else ".md"
            out.append((Case(f"t{i}-{kind}", target, kind), f"case_t{i}_{kind}{ext}", text.encode("utf-8")))
        out.append((Case(f"t{i}-jpeg_exif", term, "jpeg_exif"), f"case_t{i}.jpg", _jpeg_with_exif(term)))
        out.append((Case(f"t{i}-png_text", term, "png_text"), f"case_t{i}.png", _png_with_text(term)))
        out.append((Case(f"t{i}-pdf_author", term, "pdf_author"), f"case_t{i}.pdf", _pdf_with_author(term)))
        out.append((Case(f"t{i}-docx_comment", term, "docx_comment"), f"case_t{i}.docx", _docx_with_comment(term)))
        out.append((Case(f"t{i}-wheel", term, "wheel"), f"case_t{i}.whl", _wheel_with(term)))
        out.append((Case(f"t{i}-targz", term, "targz"), f"case_t{i}.tar.gz", _targz_with(term)))
        out.append((Case(f"t{i}-gzip_text", term, "gzip_text"), f"case_t{i}_notes.txt.gz", gzip.compress(f"{term}\n".encode())))
        out.append((Case(f"t{i}-filename", term, "filename"), f"notes-{term.replace(' ', '-').lower()}.md", b"nothing here\n"))
    out.append((Case("pii-email", "pii.email", "pii"), "case_pii_email.md", b"write to someone@company-internal.pl\n"))
    out.append((Case("pii-pesel", "pii.pesel", "pii"), "case_pii_pesel.md", b"PESEL 44051401359\n"))
    out.append((Case("pii-iban", "pii.iban", "pii"), "case_pii_iban.md", b"PL61 1090 1014 0000 0712 1981 2874\n"))
    out.append((Case("pii-phone", "pii.phone", "pii"), "case_pii_phone.md", b"tel. +48 601 234 567\n"))
    out.append((Case("clean-text", None, "clean"), "case_clean.md", b"The quarterly plan covers retrieval quality and cost.\n"))
    return out


def _run(terms: list[str], key: bytes, hashes: dict[str, str] | None, config: Config) -> dict:
    rng = random.Random(secrets.randbits(32))
    if hashes is None:
        hashes = {}
        for t in terms:
            for form in term_forms(t):
                hashes[digest(key, form)] = "block"
    denylist = Denylist(hashes, key)
    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        scanner = Scanner(denylist, config, base)
        expected_digests = {t: {digest(key, f) for f in term_forms(t)} | {digest(key, f) for w in t.split() for f in term_forms(w)} for t in terms}
        for case, rel, content in _write_cases(base, terms, rng):
            path = base / rel
            path.write_bytes(content)
            findings = scanner.scan_bytes(rel, content)
            results.append(_judge(case, findings, expected_digests))
        for i, term in enumerate(terms):
            for kind, archive in (("image_layer", _docker_archive(term, None)), ("image_env", _docker_archive(None, term))):
                img = base / f"img_{i}_{kind}.tar"
                img.write_bytes(archive)
                results.append(_judge(Case(f"t{i}-{kind}", term, kind), scan_image(scanner, img), expected_digests))
            repo = base / f"repo_{i}"
            repo.mkdir()
            env = {**os.environ, "GIT_AUTHOR_NAME": term, "GIT_AUTHOR_EMAIL": "dev@example.com",
                   "GIT_COMMITTER_NAME": "ci", "GIT_COMMITTER_EMAIL": "ci@example.com"}
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "chore: init"], check=True, env=env)
            results.append(_judge(Case(f"t{i}-git_author", term, "git_author"), scan_commits(scanner, repo, "HEAD"), expected_digests))
    return {"cases": len(results), "missed": [r for r in results if not r["ok"]], "results": results}


def _judge(case: Case, findings: list, expected: dict[str, set[str]]) -> dict:
    if case.target is None:
        ok = not findings
    elif case.target.startswith("pii."):
        ok = any(f.rule == case.target for f in findings)
    else:
        wanted = next((v for k, v in expected.items() if k == case.target or case.target in k.split()), set())
        ok = any(f.rule == "denylist" and f.digest in wanted for f in findings)
    return {"id": case.cid, "kind": case.kind, "ok": ok}


def run_selftest(args) -> int:
    config = Config.load(Path(args.allowlist) if getattr(args, "allowlist", None) else None)
    key = secrets.token_bytes(32)
    rng = random.Random(secrets.randbits(32))
    summary = _run(_canaries(rng), key, None, config)
    summary["suite"] = "public-canaries"
    summaries = [summary]
    if getattr(args, "private_cases", None):
        from .denylist import load_key

        real_key = load_key()
        data = yaml.safe_load(Path(args.private_cases).read_text(encoding="utf-8"))
        hashes = json.loads(Path(args.hashes).read_text(encoding="utf-8"))
        if hashes.get("key_id") != key_id(real_key):
            print("selftest: private suite key does not match the hash file")
            return 2
        private = _run(list(data.get("terms", [])), real_key, hashes["hashes"], config)
        private["suite"] = "private-real-names"
        private["results"] = [{"id": r["id"], "kind": r["kind"], "ok": r["ok"]} for r in private["results"]]
        summaries.append(private)
    missed = sum(len(s["missed"]) for s in summaries)
    total = sum(s["cases"] for s in summaries)
    report = {
        "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "total_cases": total,
        "missed": missed,
        "suites": [{"suite": s["suite"], "cases": s["cases"], "missed": [m["id"].split("-", 1)[1] for m in s["missed"]]} for s in summaries],
    }
    if args.results:
        Path(args.results).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lock = Path(args.lock_file).expanduser() if args.lock_file else None
    if missed:
        print(f"selftest: {missed} of {total} cases slipped through")
        for s in report["suites"]:
            for kind in s["missed"]:
                print(f"  missed [{s['suite']}]: {kind}")
        if lock:
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text(f"locked by leakgate selftest at {report['date']}: {missed} missed\n", encoding="utf-8")
        return 1
    print(f"selftest: all {total} cases caught")
    if lock and lock.exists() and lock.read_text(encoding="utf-8").startswith("locked by leakgate selftest"):
        lock.unlink()
    return 0
