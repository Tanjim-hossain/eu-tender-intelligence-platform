from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import torch
from sentence_transformers import CrossEncoder

from tendergraph.search.semantic import (
    build_document_text,
)

RERANKER_MODEL_NAME = (
    "cross-encoder/"
    "mmarco-mMiniLMv2-L12-H384-v1"
)


@dataclass(frozen=True, slots=True)
class RerankerHit:
    publication_number: str
    score: float
    source_rank: int


class CrossEncoderLike(Protocol):
    def predict(
        self,
        sentences: Sequence[
            tuple[str, str]
        ],
        **kwargs: object,
    ) -> object: ...


def reranker_document_text(
    row: dict[str, object],
) -> str:
    """Build document text for query-document scoring."""

    text = build_document_text(row)

    return text.removeprefix(
        "passage: "
    )


def rerank_scores(
    publication_numbers: list[str],
    scores: np.ndarray,
    *,
    limit: int,
) -> list[RerankerHit]:
    if not publication_numbers:
        return []

    if not 1 <= limit <= len(
        publication_numbers
    ):
        raise ValueError(
            "Invalid reranker limit"
        )

    values = np.asarray(
        scores,
        dtype=np.float32,
    ).reshape(-1)

    if values.shape[0] != len(
        publication_numbers
    ):
        raise ValueError(
            "Reranker score count mismatch"
        )

    if not np.isfinite(values).all():
        raise ValueError(
            "Reranker scores contain "
            "non-finite values"
        )

    source_ranks = {
        publication_number: rank
        for rank, publication_number
        in enumerate(
            publication_numbers,
            start=1,
        )
    }

    if len(source_ranks) != len(
        publication_numbers
    ):
        raise ValueError(
            "Duplicate reranker candidates"
        )

    indices = sorted(
        range(len(publication_numbers)),
        key=lambda index: (
            -float(values[index]),
            source_ranks[
                publication_numbers[index]
            ],
            publication_numbers[index],
        ),
    )[:limit]

    return [
        RerankerHit(
            publication_number=(
                publication_numbers[index]
            ),
            score=float(
                values[index]
            ),
            source_rank=source_ranks[
                publication_numbers[index]
            ],
        )
        for index in indices
    ]


def preferred_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"

    if torch.cuda.is_available():
        return "cuda"

    return "cpu"


class CrossEncoderReranker:
    def __init__(
        self,
        *,
        model_name: str = (
            RERANKER_MODEL_NAME
        ),
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = (
            device
            if device is not None
            else preferred_device()
        )

        self._model = CrossEncoder(
            model_name,
            device=self.device,
        )

    def rerank(
        self,
        query: str,
        publication_numbers: list[str],
        documents: dict[str, str],
        *,
        limit: int = 10,
        batch_size: int = 16,
    ) -> list[RerankerHit]:
        cleaned_query = " ".join(
            query.strip().split()
        )

        if not cleaned_query:
            raise ValueError(
                "Reranker query must not be empty"
            )

        if not publication_numbers:
            return []

        missing = (
            set(publication_numbers)
            - set(documents)
        )

        if missing:
            raise ValueError(
                "Missing reranker documents: "
                f"{sorted(missing)}"
            )

        pairs = [
            (
                cleaned_query,
                documents[
                    publication_number
                ],
            )
            for publication_number
            in publication_numbers
        ]

        raw_scores = self._model.predict(
            pairs,
            batch_size=batch_size,
            show_progress_bar=False,
        )

        scores = np.asarray(
            raw_scores,
            dtype=np.float32,
        )

        return rerank_scores(
            publication_numbers,
            scores,
            limit=limit,
        )
