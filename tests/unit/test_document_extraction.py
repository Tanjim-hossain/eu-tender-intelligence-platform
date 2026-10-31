from pathlib import Path
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from tendergraph.documents.extract import extract_document_text


def test_extract_html_omits_script_content_and_tracks_section() -> None:
    result = extract_document_text(
        (
            b"<html><body><h1>Eligibility</h1>"
            b"<p>Mandatory ISO 27001</p>"
            b"<script>ignore me</script>"
            b"<p>Submit ESPD.</p></body></html>"
        ),
        content_type="text/html; charset=utf-8",
        source_url="https://buyer.example/spec.html",
    )

    assert result.supported is True
    assert result.method == "html-parser"
    assert result.text is not None
    assert "Mandatory ISO 27001" in result.text
    assert "Submit ESPD" in result.text
    assert "ignore me" not in result.text
    assert result.chunks
    assert any(
        chunk.section_title == "Eligibility"
        and "Mandatory ISO 27001" in chunk.text
        for chunk in result.chunks
    )


def test_extract_docx_from_document_xml_with_heading() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w='urn:test'><w:body>
            <w:p><w:pPr><w:pStyle w:val='Heading1'/></w:pPr>
              <w:r><w:t>Technical capacity</w:t></w:r>
            </w:p>
            <w:p><w:r><w:t>The bidder must provide three reference projects.</w:t></w:r></w:p>
            </w:body></w:document>""",
        )

    result = extract_document_text(
        buffer.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        source_url="https://buyer.example/spec.docx",
    )

    assert result.supported is True
    assert result.method == "docx-xml"
    assert result.text is not None
    assert "three reference projects" in result.text
    assert any(
        chunk.section_title == "Technical capacity"
        and "three reference projects" in chunk.text
        for chunk in result.chunks
    )


def test_pdf_without_pdftotext_is_safe_unsupported() -> None:
    result = extract_document_text(
        b"%PDF-1.7 synthetic",
        content_type="application/pdf",
        source_url="https://buyer.example/spec.pdf",
        pdftotext_path="/definitely/missing/pdftotext",
    )

    assert result.supported is False
    assert result.text is None
    assert result.format == "pdf"
    assert result.chunks == ()


def test_pdf_page_breaks_become_provenance_pages(
    tmp_path: Path,
) -> None:
    pdftotext = tmp_path / "pdftotext"
    pdftotext.write_text(
        "#!/bin/sh\nprintf 'Page one requirement\\fPage two evidence\\f'\n",
        encoding="utf-8",
    )
    pdftotext.chmod(0o755)

    result = extract_document_text(
        b"%PDF-1.7 synthetic",
        content_type="application/pdf",
        source_url="https://buyer.example/spec.pdf",
        pdftotext_path=str(pdftotext),
    )

    assert result.supported is True
    assert result.method == "pdftotext"
    assert [chunk.page_number for chunk in result.chunks] == [1, 2]
    assert result.chunks[0].text == "Page one requirement"
    assert result.chunks[1].text == "Page two evidence"
    assert result.chunks[0].checksum != result.chunks[1].checksum
