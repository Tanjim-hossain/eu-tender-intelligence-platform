from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import psycopg

from tendergraph.database.config import (
    DatabaseSettings,
)

EMBEDDING_DIMENSIONS = 384

VECTOR_SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE IF NOT EXISTS search.embedding_models (
    model_name TEXT PRIMARY KEY,
    dimensions INTEGER NOT NULL,
    normalized BOOLEAN NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    source_rows INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT embedding_models_dimensions_positive
        CHECK (dimensions > 0),

    CONSTRAINT embedding_models_source_rows_positive
        CHECK (source_rows > 0)
);

CREATE TABLE IF NOT EXISTS search.tender_embeddings (
    publication_number TEXT NOT NULL,
    model_name TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    embedding VECTOR({EMBEDDING_DIMENSIONS}) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        publication_number,
        model_name
    ),

    CONSTRAINT tender_embeddings_model_fk
        FOREIGN KEY (model_name)
        REFERENCES search.embedding_models (
            model_name
        )
        ON DELETE CASCADE
);
"""

VECTOR_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
    idx_tender_embeddings_hnsw_cosine
ON search.tender_embeddings
USING hnsw (
    embedding vector_cosine_ops
)
WITH (
    m = 16,
    ef_construction = 64
);
"""

VECTOR_SEARCH_SQL = """
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
    e.embedding <=> %(query_vector)s::vector
        AS distance
FROM search.tender_embeddings AS e
JOIN silver.tenders AS t
    ON t.publication_number
        = e.publication_number
WHERE
    e.model_name = %(model_name)s
ORDER BY
    e.embedding <=> %(query_vector)s::vector,
    t.publication_number
LIMIT %(limit)s;
"""


@dataclass(frozen=True, slots=True)
class VectorIndexMetadata:
    model_name: str
    ingestion_run_id: str
    dimensions: int
    normalized: bool
    rows: int


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
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
    distance: float
    score: float


def vector_literal(
    vector: np.ndarray,
    *,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> str:
    values = np.asarray(
        vector,
        dtype=np.float32,
    )

    if values.ndim != 1:
        raise ValueError(
            "Vector must be one-dimensional"
        )

    if values.shape[0] != dimensions:
        raise ValueError(
            "Vector dimension mismatch: "
            f"expected {dimensions}, "
            f"found {values.shape[0]}"
        )

    if not np.isfinite(values).all():
        raise ValueError(
            "Vector contains non-finite values"
        )

    return (
        "["
        + ",".join(
            format(
                float(value),
                ".9g",
            )
            for value in values
        )
        + "]"
    )


def validate_vector_index(
    publication_numbers: np.ndarray,
    embeddings: np.ndarray,
    metadata: VectorIndexMetadata,
) -> None:
    if embeddings.ndim != 2:
        raise ValueError(
            "Embedding matrix must be 2D"
        )

    if embeddings.shape[1] != (
        EMBEDDING_DIMENSIONS
    ):
        raise ValueError(
            "Embedding dimension mismatch"
        )

    if embeddings.shape[0] != (
        publication_numbers.shape[0]
    ):
        raise ValueError(
            "Publication number and "
            "embedding row counts differ"
        )

    if embeddings.shape[0] != metadata.rows:
        raise ValueError(
            "Embedding row count does not "
            "match metadata"
        )

    if metadata.dimensions != (
        EMBEDDING_DIMENSIONS
    ):
        raise ValueError(
            "Metadata dimension mismatch"
        )

    if not metadata.normalized:
        raise ValueError(
            "Expected normalized embeddings"
        )

    if not np.isfinite(
        embeddings
    ).all():
        raise ValueError(
            "Embedding matrix contains "
            "non-finite values"
        )

    publication_ids = [
        str(value)
        for value in publication_numbers
    ]

    if len(set(publication_ids)) != len(
        publication_ids
    ):
        raise ValueError(
            "Duplicate publication numbers "
            "in embedding index"
        )


def ensure_vector_schema(
    settings: DatabaseSettings,
) -> None:
    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            VECTOR_SCHEMA_SQL
        )


def load_vector_index(
    settings: DatabaseSettings,
    *,
    publication_numbers: np.ndarray,
    embeddings: np.ndarray,
    metadata: VectorIndexMetadata,
) -> int:
    validate_vector_index(
        publication_numbers,
        embeddings,
        metadata,
    )

    publication_ids = [
        str(value)
        for value in publication_numbers
    ]

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                publication_number,
                ingestion_run_id
            FROM silver.tenders;
            """
        )

        silver_rows = cursor.fetchall()

        silver_publications = {
            row[0]
            for row in silver_rows
        }

        local_publications = set(
            publication_ids
        )

        if silver_publications != (
            local_publications
        ):
            missing_in_db = sorted(
                local_publications
                - silver_publications
            )

            missing_locally = sorted(
                silver_publications
                - local_publications
            )

            raise RuntimeError(
                "Silver/embedding publication "
                "sets differ. "
                f"Missing in DB: "
                f"{missing_in_db[:5]}; "
                f"Missing locally: "
                f"{missing_locally[:5]}"
            )

        silver_run_ids = {
            row[1]
            for row in silver_rows
        }

        if silver_run_ids != {
            metadata.ingestion_run_id
        }:
            raise RuntimeError(
                "Silver ingestion run does not "
                "match semantic index metadata"
            )

        cursor.execute(
            VECTOR_SCHEMA_SQL
        )

        cursor.execute(
            """
            INSERT INTO search.embedding_models (
                model_name,
                dimensions,
                normalized,
                ingestion_run_id,
                source_rows,
                loaded_at
            )
            VALUES (
                %(model_name)s,
                %(dimensions)s,
                %(normalized)s,
                %(ingestion_run_id)s,
                %(source_rows)s,
                NOW()
            )
            ON CONFLICT (model_name)
            DO UPDATE SET
                dimensions = EXCLUDED.dimensions,
                normalized = EXCLUDED.normalized,
                ingestion_run_id =
                    EXCLUDED.ingestion_run_id,
                source_rows =
                    EXCLUDED.source_rows,
                loaded_at = NOW();
            """,
            {
                "model_name": (
                    metadata.model_name
                ),
                "dimensions": (
                    metadata.dimensions
                ),
                "normalized": (
                    metadata.normalized
                ),
                "ingestion_run_id": (
                    metadata.ingestion_run_id
                ),
                "source_rows": (
                    metadata.rows
                ),
            },
        )

        cursor.execute(
            """
            DELETE FROM search.tender_embeddings
            WHERE model_name = %(model_name)s;
            """,
            {
                "model_name": (
                    metadata.model_name
                ),
            },
        )

        with cursor.copy(
            """
            COPY search.tender_embeddings (
                publication_number,
                model_name,
                ingestion_run_id,
                embedding
            )
            FROM STDIN
            WITH (FORMAT CSV);
            """
        ) as copy:
            buffer = io.StringIO()

            writer = csv.writer(
                buffer,
                lineterminator="\n",
            )

            for publication_number, vector in zip(
                publication_ids,
                embeddings,
                strict=True,
            ):
                buffer.seek(0)
                buffer.truncate(0)

                writer.writerow(
                    [
                        publication_number,
                        metadata.model_name,
                        metadata.ingestion_run_id,
                        vector_literal(
                            vector
                        ),
                    ]
                )

                copy.write(
                    buffer.getvalue()
                )

        cursor.execute(
            VECTOR_INDEX_SQL
        )

        cursor.execute(
            """
            ANALYZE search.tender_embeddings;
            """
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM search.tender_embeddings
            WHERE model_name =
                %(model_name)s;
            """,
            {
                "model_name": (
                    metadata.model_name
                ),
            },
        )

        loaded_count = cursor.fetchone()

        if loaded_count is None:
            raise RuntimeError(
                "Unable to verify vector load"
            )

        count = int(
            loaded_count[0]
        )

        if count != metadata.rows:
            raise RuntimeError(
                "Loaded vector count mismatch: "
                f"expected {metadata.rows}, "
                f"found {count}"
            )

    return count


def search_vector_tenders(
    settings: DatabaseSettings,
    *,
    query_vector: np.ndarray,
    model_name: str,
    limit: int = 10,
) -> list[VectorSearchResult]:
    """Run vector retrieval with a temporary connection."""

    with psycopg.connect(
        settings.connection_uri
    ) as connection:
        return search_vector_tenders_with_connection(
            connection,
            query_vector=query_vector,
            model_name=model_name,
            limit=limit,
        )


def search_vector_tenders_with_connection(
    connection: psycopg.Connection,
    *,
    query_vector: np.ndarray,
    model_name: str,
    limit: int = 10,
) -> list[VectorSearchResult]:
    """Run vector retrieval using an existing connection."""

    cleaned_model = model_name.strip()

    if not cleaned_model:
        raise ValueError(
            "Model name must not be empty"
        )

    if not 1 <= limit <= 100:
        raise ValueError(
            "Search limit must be between "
            "1 and 100"
        )

    query_literal = vector_literal(
        query_vector
    )

    with connection.cursor() as cursor:
        cursor.execute(
            VECTOR_SEARCH_SQL,
            {
                "query_vector": query_literal,
                "model_name": cleaned_model,
                "limit": limit,
            },
        )

        rows = cursor.fetchall()

    return [
        VectorSearchResult(
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
            distance=float(row[10]),
            score=1.0 - float(row[10]),
        )
        for row in rows
    ]
