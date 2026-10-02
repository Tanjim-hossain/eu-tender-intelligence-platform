from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from tendergraph.documents.extract import extract_document_text


def test_extract_html_omits_script_content() -> None:
    result = extract_document_text(
        b"<html><body><h1>Mandatory ISO 27001</h1><script>ignore me</script><p>Submit ESPD.</p></body></html>",
        content_type="text/html; charset=utf-8",
        source_url="https://buyer.example/spec.html",
    )

    assert result.supported is True
    assert result.method == "html-parser"
    assert result.text is not None
    assert "Mandatory ISO 27001" in result.text
    assert "Submit ESPD" in result.text
    assert "ignore me" not in result.text


def test_extract_docx_from_document_xml() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w='urn:test'><w:body><w:p><w:r><w:t>The bidder must provide three reference projects.</w:t></w:r></w:p></w:body></w:document>""",
        )

    result = extract_document_text(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        source_url="https://buyer.example/spec.docx",
    )

    assert result.supported is True
    assert result.method == "docx-xml"
    assert result.text is not None
    assert "three reference projects" in result.text


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
