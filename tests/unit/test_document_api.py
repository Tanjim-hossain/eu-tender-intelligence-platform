from unittest.mock import Mock

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.documents.models import (
    DocumentPackageIntelligence,
    DocumentProvenance,
    DocumentProvenanceChunk,
    TenderDocumentPackage,
)
from tendergraph.documents.service import TenderNotFoundError


def _package() -> TenderDocumentPackage:
    return TenderDocumentPackage(
        publication_number="123-2026",
        title="Example tender",
        source_xml_url="https://ted.europa.eu/example.xml",
        package_status="ingested",
        documents=[],
        extracted_document_count=0,
        restricted_document_count=0,
        failed_document_count=0,
        disclaimer="verify source",
    )


def test_document_package_endpoint_uses_injected_service() -> None:
    app = create_app(use_lifespan=False)
    service = Mock()
    service.package.return_value = _package()
    app.state.document_service = service

    response = TestClient(app).get("/documents/123-2026")

    assert response.status_code == 200
    assert response.json()["publication_number"] == "123-2026"


def test_document_ingest_endpoint() -> None:
    app = create_app(use_lifespan=False)
    service = Mock()
    service.ingest.return_value = _package()
    app.state.document_service = service

    response = TestClient(app).post(
        "/documents/123-2026/ingest",
        json={"fetch_documents": True, "force": False},
    )

    assert response.status_code == 200
    service.ingest.assert_called_once_with(
        "123-2026", fetch_documents=True, force=False
    )


def test_document_intelligence_endpoint() -> None:
    app = create_app(use_lifespan=False)
    service = Mock()
    service.intelligence.return_value = DocumentPackageIntelligence(
        publication_number="123-2026",
        package_status="ingested",
        coverage="substantive",
        documents_considered=1,
        total_extracted_characters=1200,
        requirements=[],
        risks=[],
        next_actions=["Verify originals."],
        disclaimer="verify",
    )
    app.state.document_service = service

    response = TestClient(app).get("/documents/123-2026/intelligence")

    assert response.status_code == 200
    assert response.json()["coverage"] == "substantive"


def test_missing_document_tender_returns_404() -> None:
    app = create_app(use_lifespan=False)
    service = Mock()
    service.package.side_effect = TenderNotFoundError("missing")
    app.state.document_service = service

    response = TestClient(app).get("/documents/missing")

    assert response.status_code == 404


def test_document_provenance_endpoint() -> None:
    app = create_app(use_lifespan=False)
    service = Mock()
    service.provenance.return_value = DocumentProvenance(
        publication_number="123-2026",
        chunk_count=1,
        documents_with_chunks=1,
        chunks=[
            DocumentProvenanceChunk(
                document_id="spec",
                source_url="https://buyer.example/spec.pdf",
                chunk_id="spec:0000",
                chunk_index=0,
                page_number=12,
                section_title="Eligibility",
                text="The bidder must hold ISO 27001.",
                character_count=35,
                checksum="a" * 64,
            )
        ],
        disclaimer="verify",
    )
    app.state.document_service = service

    response = TestClient(app).get(
        "/documents/123-2026/provenance"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chunk_count"] == 1
    assert payload["chunks"][0]["page_number"] == 12
    assert payload["chunks"][0]["section_title"] == "Eligibility"
