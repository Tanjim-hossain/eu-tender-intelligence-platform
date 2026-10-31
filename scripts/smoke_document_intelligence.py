from __future__ import annotations

from datetime import date

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.database.silver_loader import (
    CREATE_SCHEMA_SQL,
    CREATE_TABLE_SQL,
)
from tendergraph.documents.models import (
    DocumentProvenanceChunk,
    ProcurementDocumentReference,
)
from tendergraph.documents.repository import (
    DocumentRepository,
    NoticeDocumentSource,
)
from tendergraph.documents.schema import ensure_documents_schema
from tendergraph.documents.service import DocumentService

PUBLICATION_NUMBER = "DOCUMENT-SMOKE-001"


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(
        settings,
        min_size=1,
        max_size=2,
    )
    pool.open(wait=True)

    try:
        with pool.connection() as connection:
            connection.execute(CREATE_SCHEMA_SQL)
            connection.execute(CREATE_TABLE_SQL)
            connection.execute(
                """
                INSERT INTO silver.tenders (
                    publication_number, publication_date,
                    publication_date_raw, notice_type, title,
                    lot_descriptions, buyer_countries,
                    first_buyer_country, cpv_codes, contract_natures,
                    deadlines, performance_countries,
                    performance_regions, source_html_url,
                    source_xml_url, ingestion_run_id, source
                ) VALUES (
                    %(id)s, %(date)s, '2026-10-03', 'competition',
                    'Synthetic document package', '{}'::TEXT[],
                    ARRAY['BEL'], 'BEL', ARRAY['72000000'],
                    ARRAY['services'], '{}'::TIMESTAMPTZ[],
                    ARRAY['BEL'], '{}'::TEXT[],
                    'https://ted.europa.eu/example',
                    'https://ted.europa.eu/example.xml',
                    'document-smoke', 'ci'
                )
                ON CONFLICT (publication_number) DO UPDATE SET
                    source_xml_url = EXCLUDED.source_xml_url;
                """,
                {
                    "id": PUBLICATION_NUMBER,
                    "date": date(2026, 10, 3),
                },
            )

        ensure_documents_schema(pool)
        repository = DocumentRepository(pool)
        source = NoticeDocumentSource(
            publication_number=PUBLICATION_NUMBER,
            title="Synthetic document package",
            source_xml_url=(
                "https://ted.europa.eu/example.xml"
            ),
        )
        repository.replace_discovery(
            source,
            [
                ProcurementDocumentReference(
                    document_id="spec",
                    source_url=(
                        "https://buyer.example/"
                        "specification.pdf"
                    ),
                    official_languages=["ENG"],
                ),
                ProcurementDocumentReference(
                    document_id="controlled",
                    source_url=(
                        "https://buyer.example/restricted"
                    ),
                    restricted=True,
                    restriction_code="ipr-iss",
                ),
            ],
            xml_sha256="0" * 64,
        )
        extracted_text = (
            "The contractor must hold ISO 27001 certification. "
            "The bidder shall provide similar contracts and submit ESPD. "
            * 12
        )
        repository.record_fetch(
            PUBLICATION_NUMBER,
            "spec",
            status="extracted",
            final_url=(
                "https://buyer.example/specification.pdf"
            ),
            content_type="application/pdf",
            byte_count=1200,
            sha256="1" * 64,
            cache_path="data/documents/smoke/spec.pdf",
            extraction_method="pdftotext",
            extracted_text=extracted_text,
            error=None,
        )
        repository.replace_chunks(
            PUBLICATION_NUMBER,
            "spec",
            [
                DocumentProvenanceChunk(
                    document_id="spec",
                    source_url=(
                        "https://buyer.example/"
                        "specification.pdf"
                    ),
                    chunk_id="spec:0000",
                    chunk_index=0,
                    page_number=12,
                    section_title="Eligibility",
                    text=extracted_text[:900],
                    character_count=len(
                        extracted_text[:900]
                    ),
                    checksum="2" * 64,
                )
            ],
        )
        repository.set_package_status(
            PUBLICATION_NUMBER,
            "partial",
        )

        service = DocumentService(repository)
        package = service.package(PUBLICATION_NUMBER)
        intelligence = service.intelligence(
            PUBLICATION_NUMBER
        )
        provenance = service.provenance(
            PUBLICATION_NUMBER
        )

        assert intelligence.coverage == "partial"
        assert intelligence.documents_considered == 1
        iso = next(
            item
            for item in intelligence.requirements
            if item.key == "iso_27001"
        )
        assert iso.hard_gate is True
        assert iso.page_number == 12
        assert iso.section_title == "Eligibility"
        assert iso.chunk_id == "spec:0000"
        assert any(
            item.key == "restricted_documents"
            for item in intelligence.risks
        )

        spec = next(
            item
            for item in package.documents
            if item.document_id == "spec"
        )
        assert spec.chunk_count == 1
        assert spec.page_count == 12
        assert provenance.chunk_count == 1
        assert provenance.documents_with_chunks == 1
        assert provenance.chunks[0].checksum == "2" * 64
    finally:
        with pool.connection() as connection:
            connection.execute(
                """
                DELETE FROM documents.packages
                WHERE publication_number = %(id)s
                """,
                {"id": PUBLICATION_NUMBER},
            )
            connection.execute(
                """
                DELETE FROM silver.tenders
                WHERE publication_number = %(id)s
                """,
                {"id": PUBLICATION_NUMBER},
            )
        pool.close()


if __name__ == "__main__":
    main()
