from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg_pool import ConnectionPool

EVIDENCE_SQL = """
SELECT
    publication_number,
    publication_date,
    title,
    description,
    lot_description_text,
    buyer_name,
    first_buyer_country,
    cpv_codes,
    procedure_type,
    contract_natures,
    estimated_value,
    estimated_value_currency,
    earliest_deadline,
    latest_deadline,
    performance_countries,
    performance_regions,
    source_html_url
FROM silver.tenders
WHERE publication_number = ANY(
    %(publication_numbers)s
);
"""


@dataclass(frozen=True, slots=True)
class TenderEvidence:
    citation_id: str
    publication_number: str
    publication_date: date
    title: str
    description: str | None
    lot_description_text: str | None
    buyer_name: str | None
    buyer_country: str
    cpv_codes: list[str]
    procedure_type: str | None
    contract_natures: list[str]
    estimated_value: Decimal | None
    estimated_value_currency: str | None
    earliest_deadline: datetime | None
    latest_deadline: datetime | None
    performance_countries: list[str]
    performance_regions: list[str]
    source_html_url: str


def fetch_tender_evidence_with_connection(
    connection: psycopg.Connection,
    publication_numbers: list[str],
) -> list[TenderEvidence]:
    if not publication_numbers:
        return []

    if len(set(publication_numbers)) != len(
        publication_numbers
    ):
        raise ValueError(
            "Evidence publication numbers "
            "must be unique"
        )

    with connection.cursor() as cursor:
        cursor.execute(
            EVIDENCE_SQL,
            {
                "publication_numbers":
                    publication_numbers,
            },
        )

        rows = cursor.fetchall()

    by_publication = {
        row[0]: row
        for row in rows
    }

    missing = (
        set(publication_numbers)
        - set(by_publication)
    )

    if missing:
        raise RuntimeError(
            "Missing evidence for tenders: "
            f"{sorted(missing)}"
        )

    evidence: list[TenderEvidence] = []

    for index, publication_number in enumerate(
        publication_numbers,
        start=1,
    ):
        row = by_publication[
            publication_number
        ]

        evidence.append(
            TenderEvidence(
                citation_id=f"T{index}",
                publication_number=row[0],
                publication_date=row[1],
                title=row[2],
                description=row[3],
                lot_description_text=row[4],
                buyer_name=row[5],
                buyer_country=row[6],
                cpv_codes=list(
                    row[7] or []
                ),
                procedure_type=row[8],
                contract_natures=list(
                    row[9] or []
                ),
                estimated_value=row[10],
                estimated_value_currency=row[11],
                earliest_deadline=row[12],
                latest_deadline=row[13],
                performance_countries=list(
                    row[14] or []
                ),
                performance_regions=list(
                    row[15] or []
                ),
                source_html_url=row[16],
            )
        )

    return evidence


class TenderEvidenceRepository:
    def __init__(
        self,
        pool: ConnectionPool,
    ) -> None:
        self._pool = pool

    def fetch(
        self,
        publication_numbers: list[str],
    ) -> list[TenderEvidence]:
        with self._pool.connection() as connection:
            return fetch_tender_evidence_with_connection(
                connection,
                publication_numbers,
            )
