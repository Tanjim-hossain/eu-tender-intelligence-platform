from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

MAX_EXTRACTED_CHARACTERS = 250_000


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str | None
    method: str | None
    format: str
    supported: bool


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def _normalize_text(value: str) -> str:
    return "\n".join(
        line.strip()
        for line in value.replace("\r", "\n").split("\n")
        if line.strip()
    )[:MAX_EXTRACTED_CHARACTERS]


def _format_from(content_type: str | None, source_url: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    suffix = PurePosixPath(urlparse(source_url).path).suffix.casefold()
    if mime == "application/pdf" or suffix == ".pdf":
        return "pdf"
    if mime in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"} or suffix == ".docx":
        return "docx"
    if mime in {"text/html", "application/xhtml+xml"} or suffix in {".html", ".htm"}:
        return "html"
    if mime in {"application/xml", "text/xml"} or suffix == ".xml":
        return "xml"
    if mime == "application/json" or suffix == ".json":
        return "json"
    if mime == "text/csv" or suffix == ".csv":
        return "csv"
    if mime.startswith("text/") or suffix in {".txt", ".md"}:
        return "text"
    return "unknown"


def _extract_html(content: bytes) -> str:
    parser = _TextHTMLParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return _normalize_text("\n".join(parser.parts))


def _extract_xml(content: bytes) -> str:
    root = ET.fromstring(content)
    return _normalize_text(" ".join(part.strip() for part in root.itertext() if part.strip()))


def _extract_docx(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > 20_000_000:
            raise ValueError("DOCX document.xml exceeds extraction safety limit")
        xml_content = archive.read(info)
    root = ET.fromstring(xml_content)
    return _normalize_text(" ".join(part.strip() for part in root.itertext() if part.strip()))


def _extract_pdf(content: bytes, pdftotext_path: str | None) -> ExtractionResult:
    binary = pdftotext_path or shutil.which("pdftotext")
    if not binary:
        return ExtractionResult(text=None, method=None, format="pdf", supported=False)

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(content)
        handle.flush()
        completed = subprocess.run(
            [binary, "-layout", handle.name, "-"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    text = completed.stdout.decode("utf-8", errors="replace")
    return ExtractionResult(
        text=_normalize_text(text),
        method="pdftotext",
        format="pdf",
        supported=True,
    )


def extract_document_text(
    content: bytes,
    *,
    content_type: str | None,
    source_url: str,
    pdftotext_path: str | None = None,
) -> ExtractionResult:
    """Extract bounded text using local/free tooling only."""

    detected = _format_from(content_type, source_url)
    try:
        if detected == "pdf":
            return _extract_pdf(content, pdftotext_path)
        if detected == "docx":
            return ExtractionResult(
                text=_extract_docx(content),
                method="docx-xml",
                format=detected,
                supported=True,
            )
        if detected == "html":
            return ExtractionResult(
                text=_extract_html(content),
                method="html-parser",
                format=detected,
                supported=True,
            )
        if detected == "xml":
            return ExtractionResult(
                text=_extract_xml(content),
                method="xml-itertext",
                format=detected,
                supported=True,
            )
        if detected == "json":
            parsed = json.loads(content.decode("utf-8", errors="strict"))
            return ExtractionResult(
                text=_normalize_text(json.dumps(parsed, ensure_ascii=False, indent=2)),
                method="json",
                format=detected,
                supported=True,
            )
        if detected in {"csv", "text"}:
            return ExtractionResult(
                text=_normalize_text(content.decode("utf-8", errors="replace")),
                method="text-decode",
                format=detected,
                supported=True,
            )
    except (ET.ParseError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError, OSError, ValueError):
        return ExtractionResult(text=None, method=None, format=detected, supported=False)

    return ExtractionResult(text=None, method=None, format=detected, supported=False)
