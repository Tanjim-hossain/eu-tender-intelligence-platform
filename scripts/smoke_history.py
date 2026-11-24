from __future__ import annotations

from datetime import date
from decimal import Decimal

from psycopg.types.json import Jsonb

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.database.silver_loader import CREATE_SCHEMA_SQL, CREATE_TABLE_SQL
from tendergraph.history import buyer_history, ensure_history_schema

IDS = ["HISTORY-SMOKE-ANCHOR", "HISTORY-SMOKE-RESULT", "HISTORY-SMOKE-OLDER",
       "HISTORY-SMOKE-FUTURE", "HISTORY-SMOKE-OTHER"]


def main() -> None:
    pool = create_connection_pool(DatabaseSettings())
    pool.open(wait=True)
    try:
        with pool.connection() as connection:
            connection.execute(CREATE_SCHEMA_SQL)
            connection.execute(CREATE_TABLE_SQL)
        ensure_history_schema(pool)
        fixtures = [
            (IDS[0], date(2026, 10, 1), "cn-standard", "History smoke buyer", "BEL", Decimal(50), "EUR"),
            (IDS[1], date(2026, 9, 1), "can-standard", "history smoke buyer", "BEL", Decimal(100), "EUR"),
            (IDS[2], date(2026, 8, 1), "cn-standard", "History smoke buyer", "BEL", Decimal(200), "GBP"),
            (IDS[3], date(2026, 10, 2), "can-standard", "History smoke buyer", "BEL", Decimal(300), "EUR"),
            (IDS[4], date(2026, 9, 1), "can-standard", "History smoke buyer", "DEU", Decimal(400), "EUR"),
        ]
        with pool.connection() as connection:
            for publication, day, kind, buyer, country, value, currency in fixtures:
                connection.execute(
                    """
                    INSERT INTO silver.tenders (
                      publication_number, publication_date, publication_date_raw,
                      notice_type, title, lot_descriptions, buyer_name, buyer_countries,
                      first_buyer_country, cpv_codes, contract_natures, deadlines,
                      estimated_value, estimated_value_currency, performance_countries,
                      performance_regions, source_html_url, ingestion_run_id, source
                    ) VALUES (%s, %s, %s, %s, 'Synthetic historical notice',
                      '{}', %s, ARRAY[%s], %s, '{}', '{}', '{}',
                      %s, %s, '{}', '{}', 'https://ted.europa.eu/example', 'history-smoke', 'ci')
                    ON CONFLICT (publication_number) DO NOTHING
                    """, (publication, day, day.isoformat(), kind, buyer, country, country, value, currency),
                )
            connection.execute(
                """
                INSERT INTO history.award_evidence
                  (publication_number, source_url, sha256, source_revision, winners)
                VALUES (%s, 'https://ted.europa.eu/example.xml', %s, 'history-smoke', %s)
                ON CONFLICT (publication_number) DO NOTHING
                """, (IDS[1], "a" * 64, Jsonb([{
                    "name": "Synthetic Award Company", "contract_id": "CON-1",
                    "tender_id": "TEN-1", "organization_id": "ORG-1",
                }])),
            )
        result = buyer_history(pool, IDS[0])
        assert result is not None
        assert result.notice_count == 2
        assert result.result_notice_count == 1
        assert [n.publication_number for n in result.notices] == IDS[1:3]
        assert result.notices[0].suppliers[0].name == "Synthetic Award Company"
        assert [(v.currency, v.known_values, v.median_estimated_value) for v in result.values] == [
            ("EUR", 1, Decimal(100)), ("GBP", 1, Decimal(200)),
        ]
        with pool.connection() as connection:
            connection.execute(
                "UPDATE silver.tenders SET ingestion_run_id = 'corrected' WHERE publication_number = %s",
                (IDS[1],),
            )
        corrected = buyer_history(pool, IDS[0])
        assert corrected is not None
        assert not corrected.notices[0].award_evidence_indexed
        assert not corrected.notices[0].suppliers
        assert buyer_history(pool, "HISTORY-SMOKE-MISSING") is None
        print("Historical notice and award evidence PostgreSQL smoke passed")
    finally:
        with pool.connection() as connection:
            connection.execute("DELETE FROM silver.tenders WHERE publication_number = ANY(%s)", (IDS,))
        pool.close()


if __name__ == "__main__":
    main()
