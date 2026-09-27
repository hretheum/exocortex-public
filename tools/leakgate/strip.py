"""Removing metadata from files before publication."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path


def strip_file(path: Path) -> str:
    """Strip metadata in place. Returns a short description of what was done."""
    data = path.read_bytes()
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))
            if "icc_profile" in img.info:
                clean.info["icc_profile"] = img.info["icc_profile"]
            buf = io.BytesIO()
            fmt = "JPEG" if data[:3] == b"\xff\xd8\xff" else "PNG"
            clean.save(buf, format=fmt, quality=95) if fmt == "JPEG" else clean.save(buf, format=fmt)
        path.write_bytes(buf.getvalue())
        return "image metadata removed"
    if data[:5] == b"%PDF-":
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(data))
        writer = PdfWriter()
        for page in reader.pages:
            if "/Annots" in page:
                del page["/Annots"]
            writer.add_page(page)
        writer.add_metadata({"/Producer": ""})
        buf = io.BytesIO()
        writer.write(buf)
        path.write_bytes(buf.getvalue())
        return "PDF metadata and annotations removed"
    if path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
        src = zipfile.ZipFile(io.BytesIO(data))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                raw = src.read(info)
                if info.filename.endswith("core.xml"):
                    raw = re.sub(rb"<(dc:creator|cp:lastModifiedBy)>[^<]*</\1>", rb"<\1></\1>", raw)
                dst.writestr(info, raw)
        path.write_bytes(buf.getvalue())
        return "office author fields cleared (comments and revisions still need manual removal)"
    return "nothing to strip"
