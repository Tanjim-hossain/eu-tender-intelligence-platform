from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

from tendergraph.database.config import (
    DatabaseSettings,
)


@dataclass(frozen=True, slots=True)
class QueryVariants:
    strict: str
    broad: str
    phrase: str


@dataclass(frozen=True, slots=True)
class PoolCandidate:
    publication_number: str
    title: str
    description: str | None
    buyer_name: str | None
    buyer_country: str
    strict_match: bool
    phrase_match: bool
    strict_rank: float
    broad_rank: float
    phrase_rank: float
    source_html_url: str


def build_query_variants(
    query: str,
) -> QueryVariants:
    cleaned = " ".join(
        query.strip().split()
    )

    if not cleaned:
        raise ValueError(
            "Query must not be empty"
        )

    terms = re.findall(
        r"\w+(?:-\w+)*",
        cleaned,
        flags=re.UNICODE,
    )

    if not terms:
        raise ValueError(
            "Query must contain searchable terms"
        )

    broad = " OR ".join(terms)

    phrase = f'"{cleaned}"'

    return QueryVariants(
        strict=cleaned,
        broad=broad,
        phrase=phrase,
    )


POOL_SQL = """
WITH query_variants AS (
    SELECT
        websearch_to_tsquery(
            'simple',
            %(strict_query)s
        ) AS strict_query,
        websearch_to_tsquery(
            'simple',
            %(broad_query)s
        ) AS broad_query,
        websearch_to_tsquery(
            'simple',
            %(phrase_query)s
        ) AS phrase_query
),
scored AS (
    SELECT
        t.publication_number,
        t.title,
        t.description,
        t.buyer_name,
        t.first_buyer_country,
        t.source_html_url,

        t.search_vector @@ q.strict_query
            AS strict_match,

        t.search_vector @@ q.phrase_query
            AS phrase_match,

        ts_rank_cd(
            t.search_vector,
            q.strict_query,
            32
        ) AS strict_rank,

        ts_rank_cd(
            t.search_vector,
            q.broad_query,
            32
        ) AS broad_rank,

        ts_rank_cd(
            t.search_vector,
            q.phrase_query,
            32
        ) AS phrase_rank

    FROM silver.tenders AS t
    CROSS JOIN query_variants AS q

    WHERE
        t.search_vector @@ q.broad_query
)
SELECT
    publication_number,
    title,
    description,
    buyer_name,
    first_buyer_country,
    strict_match,
    phrase_match,
    strict_rank,
    broad_rank,
    phrase_rank,
    source_html_url
FROM scored
ORDER BY
    phrase_match DESC,
    strict_match DESC,
    GREATEST(
        phrase_rank,
        strict_rank,
        broad_rank
    ) DESC,
    publication_number
LIMIT %(limit)s;
"""


def fetch_candidate_pool(
    settings: DatabaseSettings,
    *,
    query: str,
    limit: int = 20,
) -> list[PoolCandidate]:
    """Fetch lexical candidates with a temporary connection."""

    with psycopg.connect(
        settings.connection_uri
    ) as connection:
        return fetch_candidate_pool_with_connection(
            connection,
            query=query,
            limit=limit,
        )


def fetch_candidate_pool_with_connection(
    connection: psycopg.Connection,
    *,
    query: str,
    limit: int = 20,
) -> list[PoolCandidate]:
    """Fetch lexical candidates using an existing connection."""

    if not 1 <= limit <= 100:
        raise ValueError(
            "Pool limit must be between 1 and 100"
        )

    variants = build_query_variants(query)

    with connection.cursor() as cursor:
        cursor.execute(
            POOL_SQL,
            {
                "strict_query": variants.strict,
                "broad_query": variants.broad,
                "phrase_query": variants.phrase,
                "limit": limit,
            },
        )

        rows = cursor.fetchall()

    return [
        PoolCandidate(
            publication_number=row[0],
            title=row[1],
            description=row[2],
            buyer_name=row[3],
            buyer_country=row[4],
            strict_match=row[5],
            phrase_match=row[6],
            strict_rank=float(row[7]),
            broad_rank=float(row[8]),
            phrase_rank=float(row[9]),
            source_html_url=row[10],
        )
        for row in rows
    ]
