from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

from backend.app.master_cv.contracts import MasterCvDocument


def render_master_cv_pdf(document: MasterCvDocument) -> bytes:
    """Create a deterministic, selectable-text A4 PDF without executing HTML."""

    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    })
    font_ref = writer._add_object(font)
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    lines = [document.title]
    for section in document.sections:
        visible = [block.text for block in section.blocks if block.visible]
        if visible:
            lines.extend((section.title, *visible))
    per_page = 54
    pages = [lines[index:index + per_page] for index in range(0, len(lines), per_page)] or [[]]
    pages = pages[: document.design.page_count]
    for page_lines in pages:
        page = writer.add_blank_page(width=595.276, height=841.89)
        commands = ["BT", "/F1 10 Tf", "48 793 Td", "13 TL"]
        for index, line in enumerate(page_lines):
            safe = line.encode("cp1252", errors="replace").decode("cp1252").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if index:
                commands.append("T*")
            commands.append(f"({safe}) Tj")
        commands.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("cp1252"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = resources
        page[NameObject("/MediaBox")] = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(595.276), NumberObject(841.89)])
    writer.add_metadata({
        "/Title": document.title,
        "/Creator": "Auto Initiativ deterministic Master CV renderer",
        "/Subject": f"Master CV snapshot {document.document_snapshot_id}",
    })
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
