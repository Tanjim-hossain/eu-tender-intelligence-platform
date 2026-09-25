from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


def precision_at_k(
    retrieved: list[str],
    relevant: set[str],
    *,
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be positive"
        )

    top_k = retrieved[:k]

    if not top_k:
        return 0.0

    hits = sum(
        item in relevant
        for item in top_k
    )

    return hits / k


def recall_at_k(
    retrieved: list[str],
    relevant: set[str],
    *,
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be positive"
        )

    if not relevant:
        raise ValueError(
            "relevant set must not be empty"
        )

    hits = sum(
        item in relevant
        for item in retrieved[:k]
    )

    return hits / len(relevant)


def reciprocal_rank_at_k(
    retrieved: list[str],
    relevant: set[str],
    *,
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be positive"
        )

    for rank, item in enumerate(
        retrieved[:k],
        start=1,
    ):
        if item in relevant:
            return 1.0 / rank

    return 0.0


def ndcg_at_k(
    retrieved: list[str],
    relevance: dict[str, int],
    *,
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be positive"
        )

    gains = [
        relevance.get(item, 0)
        for item in retrieved[:k]
    ]

    dcg = sum(
        (
            (2**gain - 1)
            / math.log2(rank + 1)
        )
        for rank, gain in enumerate(
            gains,
            start=1,
        )
    )

    ideal_gains = sorted(
        relevance.values(),
        reverse=True,
    )[:k]

    idcg = sum(
        (
            (2**gain - 1)
            / math.log2(rank + 1)
        )
        for rank, gain in enumerate(
            ideal_gains,
            start=1,
        )
    )

    if idcg == 0:
        return 0.0

    return dcg / idcg


def evaluate_ranking(
    retrieved: list[str],
    relevance: dict[str, int],
    *,
    k: int = 10,
) -> RetrievalMetrics:
    relevant = {
        publication_number
        for publication_number, grade
        in relevance.items()
        if grade > 0
    }

    if not relevant:
        raise ValueError(
            "At least one relevant item is required"
        )

    return RetrievalMetrics(
        precision_at_k=precision_at_k(
            retrieved,
            relevant,
            k=k,
        ),
        recall_at_k=recall_at_k(
            retrieved,
            relevant,
            k=k,
        ),
        reciprocal_rank=reciprocal_rank_at_k(
            retrieved,
            relevant,
            k=k,
        ),
        ndcg_at_k=ndcg_at_k(
            retrieved,
            relevance,
            k=k,
        ),
    )
