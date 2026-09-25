from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg

from tendergraph.database.config import (
    DatabaseSettings,
)

SEARCH_MIGRATION_SQL = """
ALTER TABLE silver.tenders
    ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
    GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'simple',
                coalesce(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'simple',
                coalesce(description, '')
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'simple',
                coalesce(
                    lot_description_text,
                    ''
                )
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'simple',
                coalesce(buyer_name, '')
            ),
            'C'
        )
        ||
        setweight(
            to_tsvector(
                'simple',
                coalesce(procedure_type, '')
            ),
            'D'
        )
    ) STORED;
"""

SEARCH_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
    idx_silver_tenders_search_vector
ON silver.tenders
USING GIN (search_vector);
"""

SEARCH_SQL = """
WITH parsed_query AS (
    SELECT websearch_to_tsquery(
        'simple',
        %(query)s
    ) AS query
)
SELECT
    t.publication_number,
    t.publication_date,
    t.title,
    t.buyer_name,
    t.first_buyer_country,
    t.procedure_type,
    t.estimated_value,
    t.estimated_value_currency,
    t.earliest_deadline,
    t.source_html_url,
    ts_rank_cd(
        t.search_vector,
        q.query,
        32
    ) AS rank
FROM silver.tenders AS t
CROSS JOIN parsed_query AS q
WHERE
    t.search_vector @@ q.query
ORDER BY
    rank DESC,
    t.publication_date DESC,
    t.publication_number
LIMIT %(limit)s;
"""


@dataclass(frozen=True, slots=True)
class LexicalSearchResult:
    publication_number: str
    publication_date: date
    title: str
    buyer_name: str | None
    buyer_country: str
    procedure_type: str | None
    estimated_value: Decimal | None
    estimated_value_currency: str | None
    earliest_deadline: datetime | None
    source_html_url: str
    rank: float


def ensure_lexical_search(
    settings: DatabaseSettings,
) -> None:
    """Create the generated FTS vector and GIN index."""

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            SEARCH_MIGRATION_SQL
        )
        cursor.execute(
            SEARCH_INDEX_SQL
        )


def search_tenders(
    settings: DatabaseSettings,
    *,
    query: str,
    limit: int = 10,
) -> list[LexicalSearchResult]:
    """Rank TED notices using PostgreSQL full-text search."""

    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError(
            "Search query must not be empty"
        )

    if not 1 <= limit <= 100:
        raise ValueError(
            "Search limit must be between 1 and 100"
        )

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            SEARCH_SQL,
            {
                "query": cleaned_query,
                "limit": limit,
            },
        )

        rows = cursor.fetchall()

    return [
        LexicalSearchResult(
            publication_number=row[0],
            publication_date=row[1],
            title=row[2],
            buyer_name=row[3],
            buyer_country=row[4],
            procedure_type=row[5],
            estimated_value=row[6],
            estimated_value_currency=row[7],
            earliest_deadline=row[8],
            source_html_url=row[9],
            rank=float(row[10]),
        )
        for row in rows
    ]
