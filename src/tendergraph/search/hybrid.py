from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HybridHit:
    publication_number: str
    rrf_score: float
    lexical_rank: int | None
    semantic_rank: int | None


def reciprocal_rank_fusion(
    lexical: list[str],
    semantic: list[str],
    *,
    rrf_k: int = 60,
    limit: int = 10,
    lexical_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[HybridHit]:
    if rrf_k <= 0:
        raise ValueError(
            "rrf_k must be positive"
        )

    if limit <= 0:
        raise ValueError(
            "limit must be positive"
        )

    if lexical_weight <= 0:
        raise ValueError(
            "lexical_weight must be positive"
        )

    if semantic_weight <= 0:
        raise ValueError(
            "semantic_weight must be positive"
        )

    lexical_ranks = {
        publication_number: rank
        for rank, publication_number
        in enumerate(
            dict.fromkeys(lexical),
            start=1,
        )
    }

    semantic_ranks = {
        publication_number: rank
        for rank, publication_number
        in enumerate(
            dict.fromkeys(semantic),
            start=1,
        )
    }

    publication_numbers = (
        set(lexical_ranks)
        | set(semantic_ranks)
    )

    hits: list[HybridHit] = []

    for publication_number in (
        publication_numbers
    ):
        lexical_rank = lexical_ranks.get(
            publication_number
        )

        semantic_rank = semantic_ranks.get(
            publication_number
        )

        score = 0.0

        if lexical_rank is not None:
            score += lexical_weight / (
                rrf_k + lexical_rank
            )

        if semantic_rank is not None:
            score += semantic_weight / (
                rrf_k + semantic_rank
            )

        hits.append(
            HybridHit(
                publication_number=(
                    publication_number
                ),
                rrf_score=score,
                lexical_rank=lexical_rank,
                semantic_rank=semantic_rank,
            )
        )

    def best_rank(
        hit: HybridHit,
    ) -> int:
        ranks = [
            rank
            for rank in (
                hit.lexical_rank,
                hit.semantic_rank,
            )
            if rank is not None
        ]

        return min(ranks)

    return sorted(
        hits,
        key=lambda hit: (
            -hit.rrf_score,
            best_rank(hit),
            hit.publication_number,
        ),
    )[:limit]
