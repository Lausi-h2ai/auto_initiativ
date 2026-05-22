from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


class DocumentExtractionError(RuntimeError):
    pass


def extract_document_text(path: Path, *, max_chars: int = 120_000) -> dict[str, Any]:
    path = path.resolve()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_text(path)
        kind = "pdf"
    elif suffix == ".docx":
        text = _extract_docx_text(path)
        kind = "docx"
    elif suffix in {".txt", ".md", ".json"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        kind = suffix.lstrip(".")
    else:
        raise DocumentExtractionError(f"Unsupported input document type: {suffix or '<none>'}")

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "filename": path.name,
        "kind": kind,
        "char_count": len(text),
        "truncated": truncated,
        "text": text,
    }


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentExtractionError("PDF extraction requires the pypdf dependency") from exc

    reader = PdfReader(str(path))
    page_text: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            page_text.append(f"\n\n--- page {index} ---\n{text.strip()}")
    return "\n".join(page_text).strip()


def _extract_docx_text(path: Path) -> str:
    paragraphs: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise DocumentExtractionError("DOCX file could not be read") from exc

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _safe_child(root: Path, filename: str) -> Path:
    if Path(filename).name != filename or filename in {"", ".", ".."}:
        raise DocumentExtractionError("Invalid input filename")
    root = root.resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise DocumentExtractionError("Path escapes onboarding input directory")
    return path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Extract text from an onboarding input document.")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--max-chars", type=int, default=120_000)
    args = parser.parse_args(argv)

    try:
        path = _safe_child(Path(args.input_root), args.filename)
        result = extract_document_text(path, max_chars=args.max_chars)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
