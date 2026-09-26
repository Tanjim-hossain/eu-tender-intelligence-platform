from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import psycopg
from psycopg_pool import ConnectionPool
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.hybrid import (
    reciprocal_rank_fusion,
)
from tendergraph.search.pooling import (
    fetch_candidate_pool_with_connection,
)
from tendergraph.search.semantic import (
    MODEL_NAME,
)
from tendergraph.search.vector import (
    search_vector_tenders_with_connection,
)

DEFAULT_RETRIEVAL_DEPTH = 20
DEFAULT_RESULT_LIMIT = 10

LEXICAL_WEIGHT = 1.0
SEMANTIC_WEIGHT = 1.25

DETAIL_SQL = """
SELECT
    publication_number,
    publication_date,
    title,
    buyer_name,
    first_buyer_country,
    procedure_type,
    estimated_value,
    estimated_value_currency,
    earliest_deadline,
    source_html_url
FROM silver.tenders
WHERE publication_number = ANY(
    %(publication_numbers)s
);
"""


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
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
    rrf_score: float
    lexical_rank: int | None
    semantic_rank: int | None
    semantic_score: float | None


class HybridSearchService:
    def __init__(
        self,
        settings: DatabaseSettings,
        *,
        model_name: str = MODEL_NAME,
        pool: ConnectionPool | None = None,
        model: SentenceTransformer | None = None,
    ) -> None:
        self._settings = settings
        self._model_name = model_name
        self._pool = pool

        self._model = (
            model
            if model is not None
            else SentenceTransformer(
                model_name
            )
        )

    def encode_query(
        self,
        query: str,
    ) -> np.ndarray:
        cleaned = " ".join(
            query.strip().split()
        )

        if not cleaned:
            raise ValueError(
                "Search query must not be empty"
            )

        embedding = self._model.encode(
            [
                f"query: {cleaned}",
            ],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]

        return np.asarray(
            embedding,
            dtype=np.float32,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_RESULT_LIMIT,
        retrieval_depth: int = (
            DEFAULT_RETRIEVAL_DEPTH
        ),
    ) -> list[HybridSearchResult]:
        cleaned = " ".join(
            query.strip().split()
        )

        if not cleaned:
            raise ValueError(
                "Search query must not be empty"
            )

        if not 1 <= limit <= 100:
            raise ValueError(
                "Search limit must be between "
                "1 and 100"
            )

        if not limit <= retrieval_depth <= 100:
            raise ValueError(
                "Retrieval depth must be "
                "between limit and 100"
            )

        query_vector = self.encode_query(
            cleaned
        )

        if self._pool is not None:
            with self._pool.connection() as connection:
                return self._search_with_connection(
                    connection,
                    query=cleaned,
                    query_vector=query_vector,
                    limit=limit,
                    retrieval_depth=retrieval_depth,
                )

        with psycopg.connect(
            self._settings.connection_uri
        ) as connection:
            return self._search_with_connection(
                connection,
                query=cleaned,
                query_vector=query_vector,
                limit=limit,
                retrieval_depth=retrieval_depth,
            )

    def _search_with_connection(
        self,
        connection: psycopg.Connection,
        *,
        query: str,
        query_vector: np.ndarray,
        limit: int,
        retrieval_depth: int,
    ) -> list[HybridSearchResult]:
        semantic_results = (
            search_vector_tenders_with_connection(
                connection,
                query_vector=query_vector,
                model_name=self._model_name,
                limit=retrieval_depth,
            )
        )

        lexical_results = (
            fetch_candidate_pool_with_connection(
                connection,
                query=query,
                limit=retrieval_depth,
            )
        )

        semantic_ids = [
            result.publication_number
            for result in semantic_results
        ]

        lexical_ids = [
            result.publication_number
            for result in lexical_results
        ]

        fused = reciprocal_rank_fusion(
            lexical_ids,
            semantic_ids,
            limit=limit,
            lexical_weight=LEXICAL_WEIGHT,
            semantic_weight=SEMANTIC_WEIGHT,
        )

        if not fused:
            return []

        semantic_scores = {
            result.publication_number:
                result.score
            for result in semantic_results
        }

        publication_numbers = [
            hit.publication_number
            for hit in fused
        ]

        details = self._fetch_details(
            connection,
            publication_numbers,
        )

        return [
            HybridSearchResult(
                publication_number=(
                    hit.publication_number
                ),
                publication_date=details[
                    hit.publication_number
                ][0],
                title=details[
                    hit.publication_number
                ][1],
                buyer_name=details[
                    hit.publication_number
                ][2],
                buyer_country=details[
                    hit.publication_number
                ][3],
                procedure_type=details[
                    hit.publication_number
                ][4],
                estimated_value=details[
                    hit.publication_number
                ][5],
                estimated_value_currency=details[
                    hit.publication_number
                ][6],
                earliest_deadline=details[
                    hit.publication_number
                ][7],
                source_html_url=details[
                    hit.publication_number
                ][8],
                rrf_score=hit.rrf_score,
                lexical_rank=hit.lexical_rank,
                semantic_rank=hit.semantic_rank,
                semantic_score=(
                    semantic_scores.get(
                        hit.publication_number
                    )
                ),
            )
            for hit in fused
        ]

    def _fetch_details(
        self,
        connection: psycopg.Connection,
        publication_numbers: list[str],
    ) -> dict[
        str,
        tuple[
            date,
            str,
            str | None,
            str,
            str | None,
            Decimal | None,
            str | None,
            datetime | None,
            str,
        ],
    ]:
        with connection.cursor() as cursor:
            cursor.execute(
                DETAIL_SQL,
                {
                    "publication_numbers":
                        publication_numbers,
                },
            )

            rows = cursor.fetchall()

        details = {
            row[0]: (
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
            )
            for row in rows
        }

        missing = (
            set(publication_numbers)
            - set(details)
        )

        if missing:
            raise RuntimeError(
                "Missing tender details for: "
                f"{sorted(missing)}"
            )

        return details
