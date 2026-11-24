"""Bounded operator-only enrichment of existing TED award notices."""
from __future__ import annotations

import argparse
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from psycopg.types.json import Jsonb

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.documents.fetcher import DocumentFetchError, SafeDocumentFetcher, UnsafeDocumentUrlError
from tendergraph.history import AWARD_TYPES, ensure_history_schema, extract_award_suppliers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20, choices=range(1, 101))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    pool = create_connection_pool(DatabaseSettings())
    pool.open(wait=True)
    try:
        ensure_history_schema(pool)
        with pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT t.publication_number, t.source_xml_url, t.ingestion_run_id
                FROM silver.tenders AS t
                LEFT JOIN history.award_evidence AS e
                  ON t.publication_number = e.publication_number
                 AND t.ingestion_run_id = e.source_revision
                WHERE t.notice_type = ANY(%s) AND t.source_xml_url IS NOT NULL
                  AND (%s OR e.publication_number IS NULL)
                ORDER BY t.publication_date DESC, t.publication_number
                LIMIT %s
                """, (list(AWARD_TYPES), args.force, args.limit),
            ).fetchall()
        fetcher = SafeDocumentFetcher()
        indexed = failed = 0
        for publication, url, revision in rows:
            try:
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.hostname not in {"ted.europa.eu", "data.europa.eu"}:
                    raise UnsafeDocumentUrlError("Not an official HTTPS TED source")
                fetched = fetcher.fetch(url, max_bytes=8_000_000)
                final = urlsplit(fetched.final_url)
                if final.scheme != "https" or final.hostname not in {"ted.europa.eu", "data.europa.eu"}:
                    raise UnsafeDocumentUrlError("Not an official HTTPS TED final source")
                if ET.fromstring(fetched.content).tag.rsplit("}", 1)[-1] != "ContractAwardNotice":
                    raise ValueError("Not a supported eForms award XML")
                suppliers = extract_award_suppliers(fetched.content)
                with pool.connection() as connection:
                    saved = connection.execute(
                        """
                        INSERT INTO history.award_evidence
                          (publication_number, source_url, sha256, source_revision, winners)
                        SELECT %s, %s, %s, %s, %s
                        WHERE EXISTS (SELECT 1 FROM silver.tenders
                            WHERE publication_number = %s AND ingestion_run_id = %s)
                        ON CONFLICT (publication_number) DO UPDATE SET
                          source_url = EXCLUDED.source_url, sha256 = EXCLUDED.sha256,
                          source_revision = EXCLUDED.source_revision, winners = EXCLUDED.winners, indexed_at = CURRENT_TIMESTAMP
                        """,
                        (publication, fetched.final_url, fetched.sha256, revision,
                         Jsonb([s.model_dump(mode="json") for s in suppliers]), publication, revision),
                    )
                if saved.rowcount == 1:
                    indexed += 1
                else:
                    failed += 1
                    print(f"{publication}: source revision changed; rerun enrichment")
            except (DocumentFetchError, UnsafeDocumentUrlError, ET.ParseError, ValueError) as exc:
                print(f"{publication}: not indexed ({type(exc).__name__})")
                failed += 1
        print(f"Award XML indexed: {indexed}; not indexed: {failed}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
