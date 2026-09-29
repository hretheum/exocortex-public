"""Existing behaviour of tools.leakgate.strip for files that need no third-party libraries."""

import io
import zipfile

from tools.leakgate.strip import strip_file


def test_plain_text_is_left_alone(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert strip_file(f) == "nothing to strip"
    assert f.read_text(encoding="utf-8") == "hello"


def test_office_author_fields_are_cleared(tmp_path):
    core = (b'<cp:coreProperties><dc:creator>Someone</dc:creator>'
            b'<cp:lastModifiedBy>Someone Else</cp:lastModifiedBy><dc:title>T</dc:title></cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", b"<w:document/>")
    f = tmp_path / "a.docx"
    f.write_bytes(buf.getvalue())
    assert strip_file(f).startswith("office author fields cleared")
    with zipfile.ZipFile(f) as z:
        cleaned = z.read("docProps/core.xml")
        assert b"Someone" not in cleaned
        assert b"<dc:creator></dc:creator>" in cleaned
        assert b"<dc:title>T</dc:title>" in cleaned
        assert z.read("word/document.xml") == b"<w:document/>"
