from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

MAX_EXTRACTED_CHARACTERS = 250_000
CHUNK_TARGET_CHARACTERS = 1_800


@dataclass(frozen=True, slots=True)
class ExtractedChunk:
    chunk_index: int
    page_number: int | None
    section_title: str | None
    text: str
    character_count: int
    checksum: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str | None
    method: str | None
    format: str
    supported: bool
    chunks: tuple[ExtractedChunk, ...] = ()


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._current_section: str | None = None
        self.segments: list[tuple[str, int | None, str | None]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if not self._skip_depth and normalized in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self._heading_tag = normalized
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if (
            not self._skip_depth
            and self._heading_tag is not None
            and normalized == self._heading_tag
        ):
            heading = _normalize_piece(" ".join(self._heading_parts))
            if heading:
                self._current_section = heading[:500]
                self.segments.append(
                    (heading, None, self._current_section)
                )
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self._heading_tag is not None:
            self._heading_parts.append(cleaned)
            return
        self.segments.append((cleaned, None, self._current_section))


def _normalize_piece(value: str) -> str:
    return " ".join(value.replace("\r", "\n").split())


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
    if (
        mime
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or suffix == ".docx"
    ):
        return "docx"
    if mime in {"text/html", "application/xhtml+xml"} or suffix in {
        ".html",
        ".htm",
    }:
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


def _split_piece(value: str) -> list[str]:
    if len(value) <= CHUNK_TARGET_CHARACTERS:
        return [value]

    words = value.split()
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        projected = current_length + len(word) + (1 if current else 0)
        if current and projected > CHUNK_TARGET_CHARACTERS:
            chunks.append(" ".join(current))
            current = [word]
            current_length = len(word)
        else:
            current.append(word)
            current_length = projected
    if current:
        chunks.append(" ".join(current))
    return chunks


def _bounded_segments(
    segments: list[tuple[str, int | None, str | None]],
) -> list[tuple[str, int | None, str | None]]:
    bounded: list[tuple[str, int | None, str | None]] = []
    remaining = MAX_EXTRACTED_CHARACTERS

    for value, page_number, section_title in segments:
        cleaned = _normalize_piece(value)
        if not cleaned or remaining <= 0:
            continue
        if len(cleaned) > remaining:
            cleaned = cleaned[:remaining].rstrip()
        if cleaned:
            bounded.append((cleaned, page_number, section_title))
            remaining -= len(cleaned) + 1
    return bounded


def _build_result(
    segments: list[tuple[str, int | None, str | None]],
    *,
    method: str,
    format: str,
) -> ExtractionResult:
    bounded = _bounded_segments(segments)
    if not bounded:
        return ExtractionResult(
            text="",
            method=method,
            format=format,
            supported=True,
        )

    merged: list[tuple[str, int | None, str | None]] = []
    for value, page_number, section_title in bounded:
        if merged:
            previous, previous_page, previous_section = merged[-1]
            if (
                previous_page == page_number
                and previous_section == section_title
                and len(previous) + len(value) + 1
                <= CHUNK_TARGET_CHARACTERS
            ):
                merged[-1] = (
                    f"{previous} {value}",
                    page_number,
                    section_title,
                )
                continue
        for part in _split_piece(value):
            merged.append((part, page_number, section_title))

    chunks: list[ExtractedChunk] = []
    for index, (value, page_number, section_title) in enumerate(merged):
        checksum_input = (
            f"{page_number or ''}\n{section_title or ''}\n{value}"
        ).encode("utf-8")
        chunks.append(
            ExtractedChunk(
                chunk_index=index,
                page_number=page_number,
                section_title=section_title,
                text=value,
                character_count=len(value),
                checksum=sha256(checksum_input).hexdigest(),
            )
        )

    return ExtractionResult(
        text=_normalize_text("\n".join(value for value, _, _ in bounded)),
        method=method,
        format=format,
        supported=True,
        chunks=tuple(chunks),
    )


def _extract_html(content: bytes) -> ExtractionResult:
    parser = _TextHTMLParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return _build_result(
        parser.segments,
        method="html-parser",
        format="html",
    )


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _attribute_by_local_name(
    element: ET.Element,
    name: str,
) -> str | None:
    for key, value in element.attrib.items():
        if _local_name(key) == name:
            return value
    return None


def _extract_xml(content: bytes) -> ExtractionResult:
    root = ET.fromstring(content)
    segments: list[tuple[str, int | None, str | None]] = []
    for element in root.iter():
        direct = _normalize_piece(element.text or "")
        if direct:
            segments.append(
                (direct, None, _local_name(element.tag)[:500])
            )
    if not segments:
        segments.append(
            (
                " ".join(
                    part.strip()
                    for part in root.itertext()
                    if part.strip()
                ),
                None,
                _local_name(root.tag)[:500],
            )
        )
    return _build_result(
        segments,
        method="xml-itertext",
        format="xml",
    )


def _extract_docx(content: bytes) -> ExtractionResult:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > 20_000_000:
            raise ValueError(
                "DOCX document.xml exceeds extraction safety limit"
            )
        xml_content = archive.read(info)

    root = ET.fromstring(xml_content)
    segments: list[tuple[str, int | None, str | None]] = []
    current_section: str | None = None

    for paragraph in root.iter():
        if _local_name(paragraph.tag) != "p":
            continue
        text = _normalize_piece(
            " ".join(
                element.text or ""
                for element in paragraph.iter()
                if _local_name(element.tag) == "t" and element.text
            )
        )
        if not text:
            continue

        style: str | None = None
        for element in paragraph.iter():
            if _local_name(element.tag) == "pStyle":
                style = _attribute_by_local_name(element, "val")
                break

        normalized_style = (style or "").casefold()
        if normalized_style.startswith("heading") or normalized_style == "title":
            current_section = text[:500]
        segments.append((text, None, current_section))

    return _build_result(
        segments,
        method="docx-xml",
        format="docx",
    )


def _extract_pdf(
    content: bytes,
    pdftotext_path: str | None,
) -> ExtractionResult:
    binary = pdftotext_path or shutil.which("pdftotext")
    if not binary:
        return ExtractionResult(
            text=None,
            method=None,
            format="pdf",
            supported=False,
        )

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(content)
        handle.flush()
        completed = subprocess.run(
            [binary, "-layout", "-enc", "UTF-8", handle.name, "-"],
            check=True,
            capture_output=True,
            timeout=30,
        )

    raw_text = completed.stdout.decode("utf-8", errors="replace")
    pages = raw_text.split("\f")
    segments = [
        (page, page_number, None)
        for page_number, page in enumerate(pages, start=1)
        if _normalize_piece(page)
    ]
    return _build_result(
        segments,
        method="pdftotext",
        format="pdf",
    )


def extract_document_text(
    content: bytes,
    *,
    content_type: str | None,
    source_url: str,
    pdftotext_path: str | None = None,
) -> ExtractionResult:
    """Extract bounded text and auditable provenance using local/free tooling."""

    detected = _format_from(content_type, source_url)
    try:
        if detected == "pdf":
            return _extract_pdf(content, pdftotext_path)
        if detected == "docx":
            return _extract_docx(content)
        if detected == "html":
            return _extract_html(content)
        if detected == "xml":
            return _extract_xml(content)
        if detected == "json":
            parsed = json.loads(content.decode("utf-8", errors="strict"))
            return _build_result(
                [
                    (
                        json.dumps(
                            parsed,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        None,
                        None,
                    )
                ],
                method="json",
                format=detected,
            )
        if detected in {"csv", "text"}:
            return _build_result(
                [
                    (
                        content.decode(
                            "utf-8",
                            errors="replace",
                        ),
                        None,
                        None,
                    )
                ],
                method="text-decode",
                format=detected,
            )
    except (
        ET.ParseError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
        KeyError,
        subprocess.SubprocessError,
        OSError,
        ValueError,
    ):
        return ExtractionResult(
            text=None,
            method=None,
            format=detected,
            supported=False,
        )

    return ExtractionResult(
        text=None,
        method=None,
        format=detected,
        supported=False,
    )
