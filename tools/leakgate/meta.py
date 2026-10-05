"""File classification, metadata checks and text extraction.

Every file ends up as a list of text "parts" to scan plus metadata findings.
Formats we cannot read are rejected, because an unreadable file is a file we
cannot vouch for.
"""

from __future__ import annotations

import io
import re
import tarfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath

TEXT_EXT = {
    ".md", ".txt", ".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".jsonl", ".csv", ".tsv",
    ".cfg", ".ini", ".conf", ".sh", ".bash", ".zsh", ".sql", ".html", ".htm", ".css", ".scss",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".astro", ".svg", ".xml", ".j2", ".jinja",
    ".service", ".timer", ".container", ".network", ".volume", ".env", ".example", ".lock",
    ".rst", ".mdx", ".dockerfile", ".gitignore", ".dockerignore", ".editorconfig", ".plist",
    ".caddyfile", ".in", ".typed", ".rs", ".go", ".mermaid", ".dot",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}
FONT_EXT = {".woff", ".woff2", ".ttf", ".otf", ".eot", ".ico"}
OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
ARCHIVE_EXT = {".zip", ".whl", ".tar", ".tgz", ".gz", ".jar"}
MAX_MEMBER = 50 * 1024 * 1024
PRINTABLE_RE = re.compile(rb"[\x20-\x7e\x80-\xff]{4,}")


@dataclass
class Extracted:
    parts: list[tuple[str, str]] = field(default_factory=list)  # (label, text)
    meta: list[tuple[str, str, str]] = field(default_factory=list)  # (rule, tier, note)
    children: list[tuple[str, bytes]] = field(default_factory=list)  # nested files


def _decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _strings(data: bytes) -> str:
    """Printable runs from binary data, decoded as UTF-8 and, separately, as Latin-1."""
    runs = PRINTABLE_RE.findall(data)
    return "\n".join(r.decode("utf-8", "ignore") + "\n" + r.decode("latin-1") for r in runs)


def _jpeg_meta(data: bytes, ex: Extracted) -> None:
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker in (0xD9, 0xDA):
            break
        size = int.from_bytes(data[i + 2 : i + 4], "big")
        seg = data[i + 4 : i + 2 + size]
        if marker == 0xE1 and seg.startswith(b"Exif"):
            ex.meta.append(("meta.image_exif", "block", "EXIF block present"))
            if b"GPS" in seg or b"\x88\x25" in seg:
                ex.meta.append(("meta.image_gps", "block", "GPS data present"))
            ex.parts.append(("exif", _strings(seg)))
        elif marker == 0xE1 and b"adobe" in seg[:64].lower():
            ex.meta.append(("meta.image_xmp", "block", "XMP block present"))
            ex.parts.append(("xmp", _strings(seg)))
        elif marker == 0xFE:
            ex.meta.append(("meta.image_comment", "block", "JPEG comment present"))
            ex.parts.append(("comment", _strings(seg)))
        i += 2 + size


def _png_meta(data: bytes, ex: Extracted) -> None:
    i = 8
    while i + 8 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        ctype = data[i + 4 : i + 8]
        chunk = data[i + 8 : i + 8 + length]
        if ctype in (b"tEXt", b"iTXt", b"zTXt", b"eXIf"):
            ex.meta.append(("meta.image_text_chunk", "block", f"PNG {ctype.decode()} chunk present"))
            text = chunk
            if ctype == b"zTXt":
                try:
                    key, _, rest = chunk.partition(b"\x00")
                    text = key + b" " + zlib.decompress(rest[1:])
                except zlib.error:
                    pass
            ex.parts.append((ctype.decode(), _strings(text)))
        if ctype == b"IEND":
            break
        i += 12 + length


def _pdf(data: bytes, ex: Extracted) -> None:
    for key in (b"/Author", b"/Creator", b"/Title", b"/Subject", b"/Keywords"):
        m = re.search(re.escape(key) + rb"\s*\((.*?)\)", data, re.S)
        if m and m.group(1).strip():
            ex.meta.append(("meta.pdf_info", "block", f"PDF {key.decode()} set"))
    if b"<x:xmpmeta" in data or b"<?xpacket" in data:
        ex.meta.append(("meta.pdf_xmp", "block", "PDF XMP metadata present"))
    if b"/Annot" in data:
        ex.meta.append(("meta.pdf_annotations", "block", "PDF annotations present"))
    ex.parts.append(("pdf-raw", _strings(data)))
    try:
        # optional: pypdf is not a dependency of the gate tools; without it the raw PDF strings above still apply
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        meta = reader.metadata or {}
        ex.parts.append(("pdf-text", text))
        ex.parts.append(("pdf-meta", "\n".join(str(v) for v in meta.values())))
    except Exception:  # noqa: BLE001 - raw strings above still get scanned
        ex.meta.append(("meta.pdf_unparsed", "warn", "PDF text could not be extracted"))


def _office(data: bytes, ex: Extracted) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        ex.meta.append(("file.corrupt", "block", "office file is not a valid zip"))
        return
    for info in zf.infolist():
        if info.file_size > MAX_MEMBER:
            ex.meta.append(("file.too_large", "block", f"member {info.filename} too large"))
            continue
        raw = zf.read(info)
        name = info.filename
        if name.endswith("core.xml") or name == "meta.xml":
            if re.search(rb"<(dc:creator|cp:lastModifiedBy|meta:initial-creator|dc:creator)>[^<]+<", raw):
                ex.meta.append(("meta.office_author", "block", "document author fields set"))
        if "comments" in name.lower():
            ex.meta.append(("meta.office_comments", "block", f"comments part {name}"))
        if re.search(rb"<w:(ins|del) ", raw):
            ex.meta.append(("meta.office_revisions", "block", "tracked changes present"))
        if name.endswith(".xml") or name.endswith(".rels"):
            text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
            ex.parts.append((name, text))
        else:
            ex.children.append((name, raw))


def _archive(name: str, data: bytes, ex: Extracted) -> None:
    lower = name.lower()
    try:
        if lower.endswith((".zip", ".whl", ".jar")):
            zf = zipfile.ZipFile(io.BytesIO(data))
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > MAX_MEMBER:
                    ex.meta.append(("file.too_large", "block", f"member {info.filename} too large"))
                    continue
                ex.children.append((info.filename, zf.read(info)))
            return
        if lower.endswith((".tar", ".tgz", ".tar.gz", ".gz")):
            if lower.endswith(".gz") and not lower.endswith((".tar.gz", ".tgz")):
                ex.children.append((name[:-3], zlib.decompress(data, 16 + zlib.MAX_WBITS)))
                return
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    if member.size > MAX_MEMBER:
                        ex.meta.append(("file.too_large", "block", f"member {member.name} too large"))
                        continue
                    fh = tf.extractfile(member)
                    if fh is not None:
                        ex.children.append((member.name, fh.read()))
    except (zipfile.BadZipFile, tarfile.TarError, zlib.error, OSError):
        ex.meta.append(("file.corrupt", "block", "archive could not be opened"))


def _pyc_strings(data: bytes) -> str | None:
    """String constants of a CPython bytecode file, or None if this Python
    cannot read it. Scanning real constants instead of printable byte runs
    avoids false alarms from bytecode that happens to look like text."""
    import marshal
    import types

    try:
        code = marshal.loads(data[16:])
    except Exception:  # noqa: BLE001 - other Python version or not a pyc
        return None
    out: list[str] = []
    stack = [code]
    while stack:
        c = stack.pop()
        for const in getattr(c, "co_consts", ()):
            if isinstance(const, str):
                out.append(const)
            elif isinstance(const, bytes):
                out.append(const.decode("utf-8", "replace"))
            elif isinstance(const, types.CodeType):
                stack.append(const)
            elif isinstance(const, (tuple, frozenset)):
                out.extend(x for x in const if isinstance(x, str))
    return "\n".join(out)


def _is_compiled(suffix: str, data: bytes) -> bool:
    """ELF objects and CPython bytecode: expected inside container images."""
    return data[:4] == b"\x7fELF" or suffix == ".pyc"


def extract(name: str, data: bytes, compiled_ok: bool = False) -> Extracted:
    """Classify a file by name and content, and return what has to be scanned.

    With ``compiled_ok`` (used for container image layers) ELF objects and .pyc
    files are accepted; their printable strings are still scanned.
    """
    ex = Extracted()
    suffix = PurePosixPath(name.lower()).suffix
    base = PurePosixPath(name).name.lower()
    ex.parts.append(("path", name))
    if compiled_ok and _is_compiled(suffix, data):
        consts = _pyc_strings(data) if suffix == ".pyc" else None
        ex.parts.append(("strings", consts if consts is not None else _strings(data)))
        return ex
    if data[:3] == b"\xff\xd8\xff":
        _jpeg_meta(data, ex)
        return ex
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        _png_meta(data, ex)
        return ex
    if data[:5] == b"%PDF-":
        _pdf(data, ex)
        return ex
    if suffix in OFFICE_EXT:
        _office(data, ex)
        return ex
    if suffix in ARCHIVE_EXT or base.endswith(".tar.gz"):
        _archive(name, data, ex)
        return ex
    text = _decode(data)
    if text is not None and ("\x00" not in text):
        ex.parts.append(("text", text))
        return ex
    if suffix in IMAGE_EXT or suffix in FONT_EXT:
        ex.parts.append(("strings", _strings(data)))
        return ex
    ex.meta.append(("file.unknown_binary", "block", f"binary file of unknown type ({suffix or 'no extension'})"))
    ex.parts.append(("strings", _strings(data)))
    return ex
