from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
import psycopg
from sentence_transformers import SentenceTransformer

from tendergraph.database.config import DatabaseSettings
from tendergraph.search.semantic import (
    MODEL_NAME,
    build_document_text,
)
from tendergraph.search.vector import (
    EMBEDDING_DIMENSIONS,
    VectorIndexMetadata,
    VectorLoadSummary,
    load_vector_index,
)


class SentenceEncoder(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class EmbeddingSource:
    publication_number: str
    ingestion_run_id: str
    title: str
    description: str | None
    lot_description_text: str | None
    buyer_name: str | None
    procedure_type: str | None
    cpv_codes: list[str]
    contract_natures: list[str]

    def document_text(self) -> str:
        return build_document_text(
            {
                "title": self.title,
                "description": self.description,
                "lot_description_text": (
                    self.lot_description_text
                ),
                "buyer_name": self.buyer_name,
                "procedure_type": self.procedure_type,
                "cpv_codes": self.cpv_codes,
                "contract_natures": (
                    self.contract_natures
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingRefreshSummary:
    requested_rows: int
    embedded_rows: int
    inserted_rows: int
    updated_rows: int
    database_rows: int | None
    ingestion_run_id: str | None


def normalize_publication_numbers(
    publication_numbers: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        str(value).strip()
        for value in publication_numbers
    )

    if any(
        not publication_number
        for publication_number in normalized
    ):
        raise ValueError(
            "Publication numbers must not be blank"
        )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            "Duplicate publication numbers "
            "in embedding refresh request"
        )

    return normalized


def fetch_embedding_sources(
    settings: DatabaseSettings,
    publication_numbers: Sequence[str],
) -> list[EmbeddingSource]:
    requested = normalize_publication_numbers(
        publication_numbers
    )

    if not requested:
        return []

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                publication_number,
                ingestion_run_id,
                title,
                description,
                lot_description_text,
                buyer_name,
                procedure_type,
                cpv_codes,
                contract_natures
            FROM silver.tenders
            WHERE publication_number = ANY(
                %(publication_numbers)s
            );
            """,
            {
                "publication_numbers": list(
                    requested
                ),
            },
        )

        rows = cursor.fetchall()

    return [
        EmbeddingSource(
            publication_number=str(row[0]),
            ingestion_run_id=str(row[1]),
            title=str(row[2]),
            description=(
                None
                if row[3] is None
                else str(row[3])
            ),
            lot_description_text=(
                None
                if row[4] is None
                else str(row[4])
            ),
            buyer_name=(
                None
                if row[5] is None
                else str(row[5])
            ),
            procedure_type=(
                None
                if row[6] is None
                else str(row[6])
            ),
            cpv_codes=list(
                row[7] or []
            ),
            contract_natures=list(
                row[8] or []
            ),
        )
        for row in rows
    ]


def prepare_embedding_documents(
    sources: Sequence[EmbeddingSource],
    publication_numbers: Sequence[str],
) -> tuple[str, list[EmbeddingSource], list[str]]:
    requested = normalize_publication_numbers(
        publication_numbers
    )

    source_by_publication = {
        source.publication_number: source
        for source in sources
    }

    if len(source_by_publication) != len(sources):
        raise RuntimeError(
            "Duplicate Silver rows returned for "
            "embedding refresh"
        )

    missing = [
        publication_number
        for publication_number in requested
        if publication_number
        not in source_by_publication
    ]

    if missing:
        raise RuntimeError(
            "Embedding refresh notices missing "
            "from Silver: "
            f"{missing[:5]}"
        )

    ordered_sources = [
        source_by_publication[
            publication_number
        ]
        for publication_number in requested
    ]

    run_ids = {
        source.ingestion_run_id
        for source in ordered_sources
    }

    if len(run_ids) != 1:
        raise RuntimeError(
            "Incremental embedding refresh must "
            "contain exactly one ingestion run"
        )

    run_id = next(
        iter(run_ids)
    )

    documents = [
        source.document_text()
        for source in ordered_sources
    ]

    return (
        run_id,
        ordered_sources,
        documents,
    )


def refresh_tender_embeddings(
    settings: DatabaseSettings,
    publication_numbers: Sequence[str],
    *,
    model_name: str = MODEL_NAME,
    batch_size: int = 32,
    encoder: SentenceEncoder | None = None,
) -> EmbeddingRefreshSummary:
    requested = normalize_publication_numbers(
        publication_numbers
    )

    if batch_size <= 0:
        raise ValueError(
            "batch_size must be positive"
        )

    if not requested:
        return EmbeddingRefreshSummary(
            requested_rows=0,
            embedded_rows=0,
            inserted_rows=0,
            updated_rows=0,
            database_rows=None,
            ingestion_run_id=None,
        )

    sources = fetch_embedding_sources(
        settings,
        requested,
    )

    (
        run_id,
        ordered_sources,
        documents,
    ) = prepare_embedding_documents(
        sources,
        requested,
    )

    active_encoder: SentenceEncoder

    if encoder is None:
        active_encoder = cast(
            SentenceEncoder,
            SentenceTransformer(
                model_name
            ),
        )
    else:
        active_encoder = encoder

    encoded = active_encoder.encode(
        documents,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    embeddings = np.asarray(
        encoded,
        dtype=np.float32,
    )

    expected_shape = (
        len(ordered_sources),
        EMBEDDING_DIMENSIONS,
    )

    if embeddings.shape != expected_shape:
        raise RuntimeError(
            "Unexpected embedding matrix shape: "
            f"{embeddings.shape} != "
            f"{expected_shape}"
        )

    publication_array = np.asarray(
        [
            source.publication_number
            for source in ordered_sources
        ],
        dtype=str,
    )

    vector_summary: VectorLoadSummary = (
        load_vector_index(
            settings,
            publication_numbers=(
                publication_array
            ),
            embeddings=embeddings,
            metadata=VectorIndexMetadata(
                model_name=model_name,
                ingestion_run_id=run_id,
                dimensions=(
                    EMBEDDING_DIMENSIONS
                ),
                normalized=True,
                rows=len(
                    ordered_sources
                ),
            ),
        )
    )

    return EmbeddingRefreshSummary(
        requested_rows=len(requested),
        embedded_rows=len(
            ordered_sources
        ),
        inserted_rows=(
            vector_summary.inserted_rows
        ),
        updated_rows=(
            vector_summary.updated_rows
        ),
        database_rows=(
            vector_summary.database_rows
        ),
        ingestion_run_id=run_id,
    )
