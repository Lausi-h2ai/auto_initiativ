from __future__ import annotations

from pathlib import Path

from backend.app.onboarding.document_text import extract_document_text


def _simple_pdf(text: str) -> bytes:
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj"
        ),
        b"4 0 obj\n<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream\nendobj",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(data))
        data += obj + b"\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    data += b"0000000000 65535 f \n"
    for offset in offsets:
        data += f"{offset:010d} 00000 n \n".encode("ascii")
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return data


def test_extract_document_text_reads_pdf(tmp_path: Path):
    path = tmp_path / "resume.pdf"
    path.write_bytes(_simple_pdf("Backend engineer resume"))

    result = extract_document_text(path)

    assert result["kind"] == "pdf"
    assert "Backend engineer resume" in result["text"]
    assert result["truncated"] is False


def test_extract_document_text_truncates_text_file(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("abcdef", encoding="utf-8")

    result = extract_document_text(path, max_chars=3)

    assert result["kind"] == "txt"
    assert result["text"] == "abc"
    assert result["truncated"] is True
