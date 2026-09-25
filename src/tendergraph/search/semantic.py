from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from sentence_transformers import (
    SentenceTransformer,
)

MODEL_NAME = (
    "intfloat/multilingual-e5-small"
)

DEFAULT_SILVER_PATH = Path(
    "data/silver/ted/tenders.parquet"
)

DEFAULT_INDEX_DIR = Path(
    "data/search/semantic"
)

EMBEDDINGS_PATH = (
    DEFAULT_INDEX_DIR / "embeddings.npz"
)

METADATA_PATH = (
    DEFAULT_INDEX_DIR / "metadata.json"
)


@dataclass(frozen=True, slots=True)
class SemanticHit:
    publication_number: str
    score: float


def _clean(
    value: object,
) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).split()
    )


def build_document_text(
    row: dict[str, object],
) -> str:
    parts = [
        (
            "Title: "
            f"{_clean(row.get('title'))}"
        ),
        (
            "Description: "
            f"{_clean(row.get('description'))}"
        ),
        (
            "Lots: "
            f"{_clean(row.get('lot_description_text'))}"
        ),
        (
            "Buyer: "
            f"{_clean(row.get('buyer_name'))}"
        ),
        (
            "Procedure: "
            f"{_clean(row.get('procedure_type'))}"
        ),
        (
            "CPV: "
            f"{_clean(row.get('cpv_codes'))}"
        ),
        (
            "Contract nature: "
            f"{_clean(row.get('contract_natures'))}"
        ),
    ]

    return "passage: " + "\n".join(
        part
        for part in parts
        if not part.endswith(": ")
    )


def build_semantic_index(
    *,
    silver_path: Path = DEFAULT_SILVER_PATH,
    index_dir: Path = DEFAULT_INDEX_DIR,
    model_name: str = MODEL_NAME,
    batch_size: int = 32,
) -> None:
    frame = pl.read_parquet(
        silver_path
    )

    publication_numbers = (
        frame["publication_number"]
        .to_list()
    )

    documents = [
        build_document_text(row)
        for row in frame.iter_rows(
            named=True
        )
    ]

    model = SentenceTransformer(
        model_name
    )

    print(
        f"Model: {model_name}"
    )

    print(
        f"Device: {model.device}"
    )

    print(
        f"Documents: {len(documents)}"
    )

    embeddings = model.encode(
        documents,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    if embeddings.ndim != 2:
        raise RuntimeError(
            "Embedding matrix must be 2D"
        )

    if embeddings.shape[0] != len(
        publication_numbers
    ):
        raise RuntimeError(
            "Embedding row count mismatch"
        )

    index_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.savez_compressed(
        index_dir / "embeddings.npz",
        publication_numbers=np.asarray(
            publication_numbers,
            dtype=str,
        ),
        embeddings=embeddings,
    )

    run_ids = (
        frame["ingestion_run_id"]
        .unique()
        .to_list()
    )

    metadata = {
        "model": model_name,
        "rows": frame.height,
        "dimensions": int(
            embeddings.shape[1]
        ),
        "ingestion_run_ids": run_ids,
        "silver_path": str(
            silver_path
        ),
        "normalized": True,
    }

    (
        index_dir / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            indent=2,
        )
        + "\n"
    )

    print(
        "Embedding dimensions:",
        embeddings.shape[1],
    )

    print(
        "Index:",
        index_dir,
    )


def load_semantic_index(
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:
    payload = np.load(
        index_dir / "embeddings.npz"
    )

    publication_numbers = payload[
        "publication_numbers"
    ]

    embeddings = payload[
        "embeddings"
    ].astype(
        np.float32,
        copy=False,
    )

    if embeddings.ndim != 2:
        raise RuntimeError(
            "Embedding matrix must be 2D"
        )

    if publication_numbers.shape[0] != (
        embeddings.shape[0]
    ):
        raise RuntimeError(
            "Semantic index length mismatch"
        )

    return (
        publication_numbers,
        embeddings,
    )


def rank_embeddings(
    publication_numbers: np.ndarray,
    embeddings: np.ndarray,
    query_embedding: np.ndarray,
    *,
    limit: int,
) -> list[SemanticHit]:
    if not 1 <= limit <= len(
        publication_numbers
    ):
        raise ValueError(
            "Invalid semantic search limit"
        )

    query_vector = np.asarray(
        query_embedding,
        dtype=np.float32,
    ).reshape(-1)

    if embeddings.shape[1] != (
        query_vector.shape[0]
    ):
        raise ValueError(
            "Embedding dimension mismatch"
        )

    scores = embeddings @ query_vector

    indices = np.argsort(
        -scores,
        kind="stable",
    )[:limit]

    return [
        SemanticHit(
            publication_number=str(
                publication_numbers[index]
            ),
            score=float(
                scores[index]
            ),
        )
        for index in indices
    ]


def search_semantic(
    query: str,
    *,
    limit: int = 10,
    index_dir: Path = DEFAULT_INDEX_DIR,
    model_name: str = MODEL_NAME,
) -> list[SemanticHit]:
    cleaned = " ".join(
        query.strip().split()
    )

    if not cleaned:
        raise ValueError(
            "Semantic query must not be empty"
        )

    publication_numbers, embeddings = (
        load_semantic_index(
            index_dir
        )
    )

    model = SentenceTransformer(
        model_name
    )

    query_embedding = model.encode(
        [
            f"query: {cleaned}",
        ],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]

    return rank_embeddings(
        publication_numbers,
        embeddings,
        query_embedding,
        limit=limit,
    )
