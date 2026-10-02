from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.database.silver_loader import (
    CREATE_SCHEMA_SQL,
    CREATE_TABLE_SQL,
)
from tendergraph.qualification.service import QualificationService
from tendergraph.rag.evidence import TenderEvidenceRepository

PUBLICATION_NUMBER = "QUALIFICATION-SMOKE-001"


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(
        settings,
        min_size=1,
        max_size=2,
    )
    pool.open(wait=True)

    deadline = datetime(
        2026,
        12,
        1,
        12,
        tzinfo=UTC,
    )
    description = (
        "The supplier must hold ISO 27001 certification and shall provide "
        "three reference projects from similar contracts. The bidder must "
        "submit the European Single Procurement Document (ESPD). This "
        "synthetic notice includes enough indexed text to exercise the "
        "evidence-grounded qualification path against PostgreSQL without "
        "calling any external or paid service."
    )

    try:
        with pool.connection() as connection:
            connection.execute(CREATE_SCHEMA_SQL)
            connection.execute(CREATE_TABLE_SQL)
            connection.execute(
                """
                INSERT INTO silver.tenders (
                    publication_number,
                    publication_date,
                    publication_date_raw,
                    notice_type,
                    title,
                    description,
                    lot_descriptions,
                    buyer_name,
                    buyer_countries,
                    first_buyer_country,
                    cpv_codes,
                    procedure_type,
                    contract_natures,
                    deadlines,
                    earliest_deadline,
                    latest_deadline,
                    estimated_value,
                    estimated_value_currency,
                    performance_countries,
                    performance_regions,
                    source_html_url,
                    ingestion_run_id,
                    source
                )
                VALUES (
                    %(publication_number)s,
                    %(publication_date)s,
                    %(publication_date_raw)s,
                    %(notice_type)s,
                    %(title)s,
                    %(description)s,
                    %(lot_descriptions)s,
                    %(buyer_name)s,
                    %(buyer_countries)s,
                    %(first_buyer_country)s,
                    %(cpv_codes)s,
                    %(procedure_type)s,
                    %(contract_natures)s,
                    %(deadlines)s,
                    %(earliest_deadline)s,
                    %(latest_deadline)s,
                    %(estimated_value)s,
                    %(estimated_value_currency)s,
                    %(performance_countries)s,
                    %(performance_regions)s,
                    %(source_html_url)s,
                    %(ingestion_run_id)s,
                    %(source)s
                )
                ON CONFLICT (publication_number)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    earliest_deadline = EXCLUDED.earliest_deadline,
                    latest_deadline = EXCLUDED.latest_deadline;
                """,
                {
                    "publication_number": PUBLICATION_NUMBER,
                    "publication_date": date(2026, 10, 3),
                    "publication_date_raw": "2026-10-03",
                    "notice_type": "competition",
                    "title": "Synthetic data platform procurement",
                    "description": description,
                    "lot_descriptions": [],
                    "buyer_name": "Synthetic Buyer",
                    "buyer_countries": ["BEL"],
                    "first_buyer_country": "BEL",
                    "cpv_codes": ["72000000"],
                    "procedure_type": "open",
                    "contract_natures": ["services"],
                    "deadlines": [deadline],
                    "earliest_deadline": deadline,
                    "latest_deadline": deadline,
                    "estimated_value": Decimal(500000),
                    "estimated_value_currency": "EUR",
                    "performance_countries": ["BEL"],
                    "performance_regions": [],
                    "source_html_url": (
                        "https://ted.europa.eu/en/notice/-/detail/"
                        "QUALIFICATION-SMOKE-001"
                    ),
                    "ingestion_run_id": "qualification-smoke",
                    "source": "ci",
                },
            )

        service = QualificationService(
            TenderEvidenceRepository(pool)
        )
        result = service.qualify(
            PUBLICATION_NUMBER,
            now=datetime(
                2026,
                10,
                3,
                12,
                tzinfo=UTC,
            ),
        )

        assert result.evidence_coverage == "substantive"
        assert result.review_status == "critical_attention"
        assert result.risk_level == "high"
        assert any(
            item.key == "iso_27001"
            and item.hard_gate
            for item in result.requirements
        )
        assert any(
            item.key == "espd_document"
            for item in result.document_signals
        )
    finally:
        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM silver.tenders WHERE publication_number = %(id)s",
                {"id": PUBLICATION_NUMBER},
            )
        pool.close()


if __name__ == "__main__":
    main()
