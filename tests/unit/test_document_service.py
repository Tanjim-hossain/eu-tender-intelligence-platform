from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tendergraph.documents.fetcher import RawFetch
from tendergraph.documents.models import (
    DocumentProvenanceChunk,
    TenderDocumentPackage,
)
from tendergraph.documents.repository import (
    ExtractedDocumentText,
    NoticeDocumentSource,
)
from tendergraph.documents.service import DocumentService


class FakeRepository:
    def __init__(self) -> None:
        self.source = NoticeDocumentSource(
            publication_number="123-2026",
            title="Example tender",
            source_xml_url="https://ted.example/notice.xml",
        )
        self.references = []
        self.fetches: dict[str, dict[str, object]] = {}
        self.chunks: dict[str, list[DocumentProvenanceChunk]] = {}
        self.status = "not_ingested"

    def get_notice_source(
        self,
        publication_number: str,
    ) -> NoticeDocumentSource | None:
        if publication_number == self.source.publication_number:
            return self.source
        return None

    def get_package(
        self,
        publication_number: str,
    ) -> TenderDocumentPackage | None:
        if not self.references:
            return None
        documents = []
        for reference in self.references:
            stored = self.fetches.get(
                reference.document_id,
                {},
            )
            chunks = self.chunks.get(
                reference.document_id,
                [],
            )
            page_numbers = [
                chunk.page_number
                for chunk in chunks
                if chunk.page_number is not None
            ]
            documents.append(
                SimpleNamespace(
                    document_id=reference.document_id,
                    source_url=str(reference.source_url),
                    restricted=reference.restricted,
                    restriction_code=reference.restriction_code,
                    official_languages=reference.official_languages,
                    unofficial_languages=reference.unofficial_languages,
                    status=stored.get(
                        "status",
                        (
                            "restricted"
                            if reference.restricted
                            else "discovered"
                        ),
                    ),
                    final_url=stored.get("final_url"),
                    content_type=stored.get("content_type"),
                    byte_count=stored.get("byte_count"),
                    sha256=stored.get("sha256"),
                    cache_path=stored.get("cache_path"),
                    extraction_method=stored.get(
                        "extraction_method"
                    ),
                    extracted_characters=len(
                        str(
                            stored.get(
                                "extracted_text"
                            )
                            or ""
                        )
                    ),
                    chunk_count=len(chunks),
                    page_count=(
                        max(page_numbers)
                        if page_numbers
                        else None
                    ),
                    error=stored.get("error"),
                    updated_at=None,
                )
            )
        return TenderDocumentPackage.model_validate(
            {
                "publication_number": publication_number,
                "title": self.source.title,
                "source_xml_url": self.source.source_xml_url,
                "package_status": self.status,
                "documents": [
                    document.__dict__
                    for document in documents
                ],
                "extracted_document_count": sum(
                    document.status == "extracted"
                    for document in documents
                ),
                "restricted_document_count": sum(
                    document.restricted
                    for document in documents
                ),
                "failed_document_count": sum(
                    document.status
                    in {"failed", "access_denied"}
                    for document in documents
                ),
                "disclaimer": "verify",
            }
        )

    def replace_discovery(
        self,
        source,
        references,
        *,
        xml_sha256: str,
    ) -> None:
        assert source == self.source
        assert xml_sha256
        self.references = references
        self.status = "ingested"

    def record_fetch(
        self,
        publication_number: str,
        document_id: str,
        **kwargs: object,
    ) -> None:
        assert publication_number == self.source.publication_number
        self.fetches[document_id] = kwargs

    def replace_chunks(
        self,
        publication_number: str,
        document_id: str,
        chunks: list[DocumentProvenanceChunk],
    ) -> None:
        assert publication_number == self.source.publication_number
        self.chunks[document_id] = chunks

    def set_package_status(
        self,
        publication_number: str,
        status: str,
        *,
        error=None,
    ) -> None:
        assert publication_number == self.source.publication_number
        assert error is None
        self.status = status

    def extracted_texts(
        self,
        publication_number: str,
    ) -> list[ExtractedDocumentText]:
        assert publication_number == self.source.publication_number
        result = []
        for reference in self.references:
            stored = self.fetches.get(
                reference.document_id,
                {},
            )
            text = stored.get("extracted_text")
            if (
                stored.get("status") == "extracted"
                and isinstance(text, str)
            ):
                result.append(
                    ExtractedDocumentText(
                        reference.document_id,
                        str(reference.source_url),
                        text,
                    )
                )
        return result

    def provenance_chunks(
        self,
        publication_number: str,
    ) -> list[DocumentProvenanceChunk]:
        assert publication_number == self.source.publication_number
        return [
            chunk
            for reference in self.references
            for chunk in self.chunks.get(
                reference.document_id,
                [],
            )
        ]


class FakeFetcher:
    XML = b"""<Notice xmlns:cac='x' xmlns:cbc='y'>
      <cac:CallForTendersDocumentReference>
        <cbc:ID>spec</cbc:ID><cbc:DocumentType>non-restricted-document</cbc:DocumentType>
        <cac:Attachment><cac:ExternalReference><cbc:URI>https://buyer.example/spec.html</cbc:URI></cac:ExternalReference></cac:Attachment>
      </cac:CallForTendersDocumentReference>
      <cac:CallForTendersDocumentReference>
        <cbc:ID>restricted</cbc:ID><cbc:DocumentType>restricted-document</cbc:DocumentType>
        <cac:Attachment><cac:ExternalReference><cbc:URI>https://buyer.example/controlled</cbc:URI></cac:ExternalReference></cac:Attachment>
      </cac:CallForTendersDocumentReference>
    </Notice>"""

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
    ) -> RawFetch:
        assert max_bytes > 0
        if url.endswith("notice.xml"):
            content = self.XML
            content_type = "application/xml"
        else:
            assert url == "https://buyer.example/spec.html"
            content = (
                b"<html><body><h2>Eligibility</h2>"
                b"<p>The supplier must hold ISO 27001 certification. "
                b"The bidder shall provide similar contracts and submit ESPD. "
                b"This procurement specification contains substantive synthetic "
                b"qualification evidence for deterministic local testing.</p>"
                b"</body></html>"
            )
            content_type = "text/html"
        return RawFetch(
            source_url=url,
            final_url=url,
            content_type=content_type,
            content=content,
            sha256="a" * 64,
            byte_count=len(content),
            status_code=200,
        )


def test_ingest_discovers_fetches_extracts_and_tracks_provenance(
    tmp_path: Path,
) -> None:
    repository = FakeRepository()
    service = DocumentService(
        repository,  # type: ignore[arg-type]
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        cache_root=tmp_path,
    )

    package = service.ingest("123-2026")
    intelligence = service.intelligence("123-2026")
    provenance = service.provenance("123-2026")

    assert package.package_status == "ingested"
    assert len(package.documents) == 2
    assert package.extracted_document_count == 1
    assert package.restricted_document_count == 1
    spec = next(
        item
        for item in package.documents
        if item.document_id == "spec"
    )
    assert spec.chunk_count >= 1
    assert repository.fetches["spec"]["status"] == "extracted"
    assert not (
        tmp_path / "123-2026"
    ).joinpath("restricted").exists()

    iso = next(
        item
        for item in intelligence.requirements
        if item.key == "iso_27001"
    )
    assert iso.hard_gate is True
    assert iso.document_id == "spec"
    assert iso.chunk_id is not None
    assert iso.section_title == "Eligibility"
    assert any(
        item.key == "restricted_documents"
        for item in intelligence.risks
    )

    assert provenance.chunk_count >= 1
    assert provenance.documents_with_chunks == 1
    assert provenance.chunks[0].document_id == "spec"
    assert provenance.chunks[0].section_title == "Eligibility"
