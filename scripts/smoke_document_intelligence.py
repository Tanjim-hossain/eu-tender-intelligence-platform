from __future__ import annotations

from datetime import date

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.database.silver_loader import CREATE_SCHEMA_SQL, CREATE_TABLE_SQL
from tendergraph.documents.models import ProcurementDocumentReference
from tendergraph.documents.repository import DocumentRepository, NoticeDocumentSource
from tendergraph.documents.schema import ensure_documents_schema
from tendergraph.documents.service import DocumentService

PUBLICATION_NUMBER = "DOCUMENT-SMOKE-001"


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(settings, min_size=1, max_size=2)
    pool.open(wait=True)

    try:
        with pool.connection() as connection:
            connection.execute(CREATE_SCHEMA_SQL)
            connection.execute(CREATE_TABLE_SQL)
            connection.execute(
                """
                INSERT INTO silver.tenders (
                    publication_number, publication_date, publication_date_raw,
                    notice_type, title, lot_descriptions, buyer_countries,
                    first_buyer_country, cpv_codes, contract_natures, deadlines,
                    performance_countries, performance_regions, source_html_url,
                    source_xml_url, ingestion_run_id, source
                ) VALUES (
                    %(id)s, %(date)s, '2026-10-03', 'competition',
                    'Synthetic document package', '{}'::TEXT[], ARRAY['BEL'],
                    'BEL', ARRAY['72000000'], ARRAY['services'],
                    '{}'::TIMESTAMPTZ[], ARRAY['BEL'], '{}'::TEXT[],
                    'https://ted.europa.eu/example',
                    'https://ted.europa.eu/example.xml', 'document-smoke', 'ci'
                )
                ON CONFLICT (publication_number) DO UPDATE SET
                    source_xml_url = EXCLUDED.source_xml_url;
                """,
                {"id": PUBLICATION_NUMBER, "date": date(2026, 10, 3)},
            )

        ensure_documents_schema(pool)
        repository = DocumentRepository(pool)
        source = NoticeDocumentSource(
            publication_number=PUBLICATION_NUMBER,
            title="Synthetic document package",
            source_xml_url="https://ted.europa.eu/example.xml",
        )
        repository.replace_discovery(
            source,
            [
                ProcurementDocumentReference(
                    document_id="spec",
                    source_url="https://buyer.example/specification.html",
                    official_languages=["ENG"],
                ),
                ProcurementDocumentReference(
                    document_id="controlled",
                    source_url="https://buyer.example/restricted",
                    restricted=True,
                    restriction_code="ipr-iss",
                ),
            ],
            xml_sha256="0" * 64,
        )
        repository.record_fetch(
            PUBLICATION_NUMBER,
            "spec",
            status="extracted",
            final_url="https://buyer.example/specification.html",
            content_type="text/html",
            byte_count=1200,
            sha256="1" * 64,
            cache_path="data/documents/smoke/spec.html",
            extraction_method="html-parser",
            extracted_text=(
                "The contractor must hold ISO 27001 certification. "
                "The bidder shall provide similar contracts and submit ESPD. "
                * 12
            ),
            error=None,
        )
        repository.set_package_status(PUBLICATION_NUMBER, "partial")

        intelligence = DocumentService(repository).intelligence(PUBLICATION_NUMBER)

        assert intelligence.coverage == "partial"
        assert intelligence.documents_considered == 1
        assert any(item.key == "iso_27001" and item.hard_gate for item in intelligence.requirements)
        assert any(item.key == "restricted_documents" for item in intelligence.risks)
    finally:
        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM documents.packages WHERE publication_number = %(id)s",
                {"id": PUBLICATION_NUMBER},
            )
            connection.execute(
                "DELETE FROM silver.tenders WHERE publication_number = %(id)s",
                {"id": PUBLICATION_NUMBER},
            )
        pool.close()


if __name__ == "__main__":
    main()
